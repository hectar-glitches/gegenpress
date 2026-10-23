"""The agent layer: Scout, Why, Desk, Gate.

The division of labour is the point. Selection and reasoning are
deterministic; the model only phrases a fact it was handed. That is the
field-wide consensus for good reason -- a model asked to decide what
matters will confidently decide wrongly, and no amount of fact-checking
catches a true sentence about an unimportant event.

    Scout   picks the moment            deterministic
    Why     chooses the reference class  deterministic
    Desk    writes it                    the model
    Gate    verifies every number        deterministic

Gate is not a second model. It extracts every number from what Desk wrote
and checks each one against the brief. A number that is not in the brief
cannot be in the output, whatever the model's confidence.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Any, Protocol

from .form import METRIC_LABELS, FormLine
from .models import Match
from .season import League
from .store import GroundedMoment, Store

# Numbers written as digits, including decimals and percentages.
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
# Tolerance when matching a number in prose to a number in the brief.
# Prose rounds; "17.1" must match 17.08.
TOLERANCE = 0.051


# --------------------------------------------------------------------------
# What the model is allowed to know
# --------------------------------------------------------------------------

@dataclass(slots=True)
class Brief:
    """The complete, closed set of facts for one moment.

    Desk sees this and nothing else. Gate checks against this and nothing
    else. If a number is not here, it may not appear in the output.
    """

    minute: int
    player_name: str
    club_name: str
    opponent_name: str
    metric_label: str
    value: float
    expected: float
    beats_pct: float                 # share of the league beaten, 0-100
    # The Form Line, present only when the metric supports a personal claim.
    season_mean: float | None = None
    z: float | None = None
    appearances: int | None = None
    diverges: bool = False
    notes: list[str] = field(default_factory=list)

    def allowed_numbers(self) -> list[float]:
        """Every number the output may contain."""
        out = [float(self.minute), self.value, self.expected, self.beats_pct]
        for extra in (self.season_mean, self.z, self.appearances):
            if extra is not None:
                out.append(float(extra))
        # Prose often rounds a percentage to a whole number.
        out.append(round(self.beats_pct))
        return out

    def as_prompt(self) -> str:
        lines = [
            f"minute: {self.minute}",
            f"player: {self.player_name} ({self.club_name}, against {self.opponent_name})",
            f"metric: {self.metric_label}",
            f"value tonight: {self.value:g}",
            f"league expected: {self.expected:g}",
            f"beats {self.beats_pct:.0f}% of the league",
        ]
        if self.season_mean is not None:
            lines += [
                f"his season norm: {self.season_mean:g}",
                f"standard deviations from his own norm: {self.z:+g}",
                f"matches in his season history: {self.appearances}",
            ]
        if self.diverges:
            lines.append(
                "NOTE: this is strong for him but ordinary league-wide. "
                "That contrast is the story."
            )
        lines += self.notes
        return "\n".join(lines)


# --------------------------------------------------------------------------
# Models
# --------------------------------------------------------------------------

class LanguageModel(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str: ...


class TemplateModel:
    """No model at all. Deterministic prose from the brief.

    This is the fallback when Foundry is unreachable and the floor the
    Gate falls back to. It is never wrong, and never interesting.
    """

    name = "template"

    def complete(self, system: str, user: str) -> str:
        fields = dict(
            line.split(": ", 1) for line in user.splitlines() if ": " in line
        )
        player = fields.get("player", "the player").split(" (")[0]
        metric = fields.get("metric", "that")
        value = fields.get("value tonight", "")
        norm = fields.get("his season norm")
        minute = fields.get("minute", "")
        if norm:
            return (f"{minute}' {player}: {metric} {value} tonight, "
                    f"against a season norm of {norm}.")
        return f"{minute}' {player}: {metric} {value}."


class FoundryModel:
    """Microsoft Foundry via the Agent Framework.

    Configuration:
        FOUNDRY_PROJECT_ENDPOINT  https://<name>.services.ai.azure.com/api/projects/<project>
        FOUNDRY_MODEL             deployment name

    Auth is DefaultAzureCredential, so `az login` locally and a managed
    identity in Container Apps both work unchanged.
    """

    name = "foundry"

    def __init__(self, endpoint: str, model: str) -> None:
        from agent_framework import Agent
        from agent_framework.foundry import FoundryChatClient
        from azure.identity import AzureCliCredential

        self.endpoint = endpoint
        self.model = model
        self._client = FoundryChatClient(
            project_endpoint=endpoint, model=model, credential=AzureCliCredential()
        )
        self._Agent = Agent

    @classmethod
    def from_env(cls) -> "FoundryModel":
        endpoint = os.environ.get("FOUNDRY_PROJECT_ENDPOINT")
        model = os.environ.get("FOUNDRY_MODEL")
        if not endpoint or not model:
            raise RuntimeError(
                "FOUNDRY_PROJECT_ENDPOINT and FOUNDRY_MODEL are not set"
            )
        return cls(endpoint, model)

    def complete(self, system: str, user: str) -> str:
        import asyncio

        agent = self._Agent(client=self._client, name="desk", instructions=system)
        result = asyncio.run(agent.run(user))
        return str(result).strip()


def get_model(prefer_foundry: bool | None = None) -> LanguageModel:
    """Foundry when configured and importable, otherwise templates."""
    if prefer_foundry is None:
        prefer_foundry = bool(os.environ.get("FOUNDRY_PROJECT_ENDPOINT"))
    if prefer_foundry:
        try:
            return FoundryModel.from_env()
        except Exception as exc:  # pragma: no cover - depends on local env
            print(f"[agents] Foundry unavailable ({exc}); using templates")
    return TemplateModel()


# --------------------------------------------------------------------------
# The agents
# --------------------------------------------------------------------------

DESK_SYSTEM = """You write one sentence of football broadcast commentary.

Rules, all absolute:
- Use ONLY the numbers given to you. Never introduce a number of your own.
- Never state a score, a result, or anything not in the brief.
- One sentence. Under 30 words. Present tense.
- Write for broadcast, not for a report. No preamble, no hedging.
- If the brief says the contrast is the story, lead with the contrast.

Return only the sentence."""


class Scout:
    """Picks what is worth talking about. Deterministic, by design."""

    def __init__(self, store: Store) -> None:
        self.store = store

    def find(self, live: Match, limit: int = 5) -> list[GroundedMoment]:
        return self.store.top_moments(live, min_beats=0.97, limit=limit)

    def form(self, live: Match) -> list[FormLine]:
        lines = self.store.form_lines(live)
        # Diverging lines first: those are the ones a league percentile
        # alone cannot tell you about.
        return sorted(lines, key=lambda f: (not f.diverges, -abs(f.z)))


class Why:
    """Chooses the reference class and assembles the brief.

    The judgement here -- league, personal, or the contrast between them --
    is the project's actual thesis, so it is code, not a prompt.
    """

    def __init__(self, league: League) -> None:
        self.league = league

    def brief_from_form(self, form: FormLine, live: Match) -> Brief:
        player = self.league.player(form.player_id)
        club = self.league.club(player.club_id)
        other = (live.away_club_id if player.club_id == live.home_club_id
                 else live.home_club_id)
        notes = []
        if form.diverges and form.above_own_level:
            notes.append(
                "angle: unremarkable by league standards, well above his own level"
            )
        elif form.diverges:
            notes.append(
                "angle: ordinary by league standards, but well below his own level"
            )
        elif form.above_own_level:
            notes.append("angle: above his own level and the league's")
        else:
            notes.append("angle: below his own level")
        return Brief(
            minute=90,
            player_name=player.name,
            club_name=club.name,
            opponent_name=self.league.club(other).name,
            metric_label=METRIC_LABELS.get(form.metric, form.metric),
            value=form.match_mean,
            expected=form.league_mean,
            beats_pct=form.league_percentile * 100.0,
            season_mean=form.season_mean,
            z=form.z,
            appearances=form.appearances,
            diverges=form.diverges,
            notes=notes,
        )

    def brief_from_moment(self, moment: GroundedMoment, live: Match) -> Brief:
        player = self.league.player(moment.player_id)
        club = self.league.club(player.club_id)
        other = (live.away_club_id if player.club_id == live.home_club_id
                 else live.home_club_id)
        return Brief(
            minute=moment.minute,
            player_name=moment.player_name,
            club_name=club.name,
            opponent_name=self.league.club(other).name,
            metric_label=METRIC_LABELS.get(moment.metric, moment.metric),
            value=round(moment.value, 2),
            expected=round(moment.expected, 2),
            beats_pct=moment.beats * 100.0,
            # No personal claim unless the metric earns one.
            season_mean=(round(moment.personal_mean, 2)
                         if moment.personal_claim_allowed and moment.personal_mean
                         else None),
        )


@dataclass(slots=True)
class Verdict:
    passed: bool
    text: str
    rejected: list[float] = field(default_factory=list)
    attempts: int = 1
    model: str = "template"
    fell_back: bool = False


class Gate:
    """Checks every number in the prose against the brief.

    Not a second model. A number the brief does not contain cannot appear
    in the output, however plausible it reads.

    Two holes, both real and both documented rather than hidden:

    1. It reads digits, not words. "forty-seven passes" passes the gate.
       Mitigated by instructing Desk to write numerals, not by detection.
    2. It checks that a number is PRESENT in the brief, not that it is
       attached to the right thing. "his season norm is 15.2" passes when
       15.2 is tonight's value and 13.9 is the norm, because both numbers
       are in the brief. Catching that needs a semantic check this does
       not attempt.

    So the gate removes invented numbers. It does not guarantee the
    sentence is true. Those are different claims and only the first is
    made here.
    """

    @staticmethod
    def unsupported(text: str, brief: Brief) -> list[float]:
        allowed = brief.allowed_numbers()
        bad: list[float] = []
        for token in NUMBER.findall(text):
            value = float(token)
            if not any(abs(value - ok) <= TOLERANCE for ok in allowed):
                bad.append(value)
        return bad

    def check(self, text: str, brief: Brief) -> list[float]:
        return self.unsupported(text, brief)


class Desk:
    """Writes it. The only place a model is allowed to act."""

    def __init__(self, model: LanguageModel, gate: Gate | None = None) -> None:
        self.model = model
        self.gate = gate or Gate()

    def write(self, brief: Brief, retries: int = 1) -> Verdict:
        prompt = brief.as_prompt()
        last_bad: list[float] = []
        for attempt in range(1, retries + 2):
            text = self.model.complete(DESK_SYSTEM, prompt).strip().strip('"')
            bad = self.gate.check(text, brief)
            if not bad:
                return Verdict(True, text, [], attempt, self.model.name, False)
            last_bad = bad
            prompt = (
                f"{brief.as_prompt()}\n\n"
                f"Your previous attempt used numbers that are not in this brief: "
                f"{', '.join(str(b) for b in bad)}. "
                f"Rewrite using only the numbers above."
            )
        fallback = TemplateModel().complete(DESK_SYSTEM, brief.as_prompt())
        return Verdict(False, fallback, last_bad, retries + 1,
                       self.model.name, True)


# --------------------------------------------------------------------------
# The pipeline
# --------------------------------------------------------------------------

@dataclass(slots=True)
class Segment:
    brief: Brief
    verdict: Verdict

    def as_dict(self) -> dict[str, Any]:
        return {
            "minute": self.brief.minute,
            "player": self.brief.player_name,
            "metric": self.brief.metric_label,
            "text": self.verdict.text,
            "diverges": self.brief.diverges,
            "grounded": self.verdict.passed,
            "model": self.verdict.model,
            "attempts": self.verdict.attempts,
            "fell_back": self.verdict.fell_back,
            "rejected_numbers": self.verdict.rejected,
        }


def run_desk(
    store: Store,
    league: League,
    live: Match,
    model: LanguageModel | None = None,
    limit: int = 6,
) -> list[Segment]:
    """Scout -> Why -> Desk -> Gate over one match."""
    model = model or get_model()
    scout, why, desk = Scout(store), Why(league), Desk(model)

    segments: list[Segment] = []
    for form in scout.form(live)[:limit]:
        brief = why.brief_from_form(form, live)
        segments.append(Segment(brief, desk.write(brief)))
    return segments
