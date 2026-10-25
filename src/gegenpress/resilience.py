"""What happens when a dependency dies mid-match.

A broadcast does not get to stop because a cluster did. Three things can
fail here and all three have somewhere to go:

    Azure Data Explorer   ->  the local store, per call
    Microsoft Foundry     ->  deterministic templates
    the model's sentence  ->  rejected by the Gate, replaced by a template

The first of those was only half true before this module. `get_store()`
falls back when ADX cannot be reached *at startup*, which is the easy
case and not the one that matters: a cluster that answers at kickoff and
times out at 60' would previously have taken the pipeline down with it.
`ResilientStore` moves the fallback from selection time to call time.

The rest of this file exists so the claim can be *shown* rather than
asserted. Fault injection makes each dependency fail on demand, and
`chaos_report()` runs the pipeline under each fault and checks the thing
an operator actually cares about: did the claims survive, and are the
numbers in them still the same numbers.

That last check is the point. Degrading is easy. Degrading without
changing what you told the audience is the property worth having, and it
is only available because every stage here is deterministic -- there is
a correct answer to fall back *to*.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .store import LocalStore, Store


# --------------------------------------------------------------------------
# Injection
# --------------------------------------------------------------------------

@dataclass
class Faults:
    """Which dependencies are pretending to be down.

    Process-global on purpose: it stands in for the world being broken,
    and the world is not a parameter anyone threads through a call stack.
    """

    adx: bool = False
    foundry: bool = False
    model: bool = False      # the model emits a number the brief does not have

    def any(self) -> bool:
        return self.adx or self.foundry or self.model

    def names(self) -> list[str]:
        return [n for n in ("adx", "foundry", "model") if getattr(self, n)]


FAULTS = Faults()


class InjectedFailure(RuntimeError):
    """Raised in place of a real outage. Distinct type so a test cannot
    pass by catching a genuine bug and calling it resilience."""


# --------------------------------------------------------------------------
# The store that survives its primary
# --------------------------------------------------------------------------

# Every Store call that reads. load_season is handled separately because
# the standby needs the data too, or there is nothing to fall back to.
_READS = ("top_moments", "match_state", "follow_target", "form_lines",
          "signal_table", "ground", "doctor")


class ResilientStore:
    """A primary store with a local standby, failing over per call.

    Not a cache and not a replica: the standby is a second implementation
    of the same interface, held to the same answers by the parity test in
    `tests/test_store.py`. That test is what makes this honest -- failing
    over is only safe because the two backends agree.
    """

    def __init__(self, primary: Store, standby: Store | None = None) -> None:
        self.primary = primary
        self.standby: Store = standby or LocalStore()
        self.failovers = 0
        self.log: list[str] = []

    def load_season(self, league: Any, matches: Any) -> None:
        # The standby first and unconditionally. A standby that has not
        # loaded the season is not a standby.
        self.standby.load_season(league, matches)
        try:
            if FAULTS.adx:
                raise InjectedFailure("ADX unreachable (injected)")
            self.primary.load_season(league, matches)
        except Exception as exc:
            self._note("load_season", exc)

    def _note(self, call: str, exc: Exception) -> None:
        self.failovers += 1
        self.log.append(f"{call}: {type(exc).__name__}: {exc}")

    def __getattr__(self, name: str) -> Any:
        if name not in _READS:
            raise AttributeError(name)

        def call(*args: Any, **kwargs: Any) -> Any:
            try:
                if FAULTS.adx:
                    raise InjectedFailure("ADX unreachable (injected)")
                return getattr(self.primary, name)(*args, **kwargs)
            except Exception as exc:
                self._note(name, exc)
                return getattr(self.standby, name)(*args, **kwargs)

        return call


# --------------------------------------------------------------------------
# A model that cannot be trusted
# --------------------------------------------------------------------------

class UngroundedModel:
    """Writes a plausible sentence containing a number nobody measured.

    This is the failure the Gate exists for, made reproducible. 21.4 is
    the same invented figure the MCP demo uses, so the two
    demonstrations tell one story.
    """

    name = "ungrounded"

    def complete(self, system: str, user: str) -> str:
        fields = dict(
            line.split(": ", 1) for line in user.splitlines() if ": " in line
        )
        player = fields.get("player", "the player").split(" (")[0]
        minute = fields.get("minute", "0")
        return (f"{minute}' {player} is up to 21.4 tonight, "
                f"comfortably his best of the season.")


# --------------------------------------------------------------------------
# The exercise
# --------------------------------------------------------------------------

@dataclass
class ChaosRow:
    fault: str
    degraded_to: str
    claims: int
    survived: bool
    numbers_identical: bool
    failovers: int
    detail: str = ""


@dataclass
class ChaosResult:
    rows: list[ChaosRow] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return all(r.survived and r.numbers_identical for r in self.rows)


class GroundedModel:
    """Stands in for a healthy Foundry: a model that behaves.

    It phrases the brief differently from the template fallback on
    purpose. If the two read the same, a fallback is invisible and the
    exercise below proves nothing.
    """

    name = "grounded-stub"

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
            return (f"At {minute}', {player} shows {metric} of {value}, "
                    f"set against {norm} across his season.")
        return f"At {minute}', {player} shows {metric} of {value}."


def _numbers(text: str) -> list[str]:
    import re
    return sorted(re.findall(r"-?\d+(?:\.\d+)?", text))


def chaos_run(seed: int = 2026, limit: int = 6) -> ChaosResult:
    """Break one thing at a time and see what reaches the viewer.

    The comparison is against a healthy baseline, claim by claim. A row
    passes only if every claim still arrives AND carries the same set of
    numbers. Different words are fine -- that is what degrading means.
    Different numbers would mean the fallback is editing the broadcast,
    which is the failure this is here to rule out.

    Note what the ADX row does and does not prove: it exercises the
    failover path, not Azure. The parity test is what establishes that
    the standby answers the same as the cluster.
    """
    from .agents import TemplateModel, run_desk
    from .season import build_league
    from .simulate import simulate_live, simulate_season

    league = build_league(seed=seed)
    season = simulate_season(league, seed=seed)
    live = simulate_live(league, league.fixtures[0], seed=seed)

    def once(model: Any) -> tuple[list[Any], ResilientStore]:
        store = ResilientStore(LocalStore())
        store.load_season(league, season)
        return run_desk(store, league, live, model=model, limit=limit), store

    previous = Faults(**vars(FAULTS))
    try:
        for attr in ("adx", "foundry", "model"):
            setattr(FAULTS, attr, False)
        base_segs, _ = once(GroundedModel())
        base = [_numbers(s.verdict.text) for s in base_segs]
        base_texts = [s.verdict.text for s in base_segs]

        result = ChaosResult()
        result.rows.append(ChaosRow(
            fault="none (baseline)", degraded_to="—", claims=len(base_segs),
            survived=bool(base_segs), numbers_identical=True, failovers=0,
            detail=base_texts[0][:72] if base_texts else "",
        ))

        plans = (
            ("adx", "local store", lambda: GroundedModel()),
            ("foundry", "deterministic templates", lambda: TemplateModel()),
            ("model", "gate rejects, template replaces", lambda: UngroundedModel()),
        )
        for name, degraded, make in plans:
            for attr in ("adx", "foundry", "model"):
                setattr(FAULTS, attr, attr == name)
            segs, store = once(make())
            nums = [_numbers(s.verdict.text) for s in segs]
            result.rows.append(ChaosRow(
                fault=name, degraded_to=degraded, claims=len(segs),
                survived=len(segs) == len(base_segs) and bool(segs),
                numbers_identical=(nums == base),
                failovers=store.failovers,
                detail=(segs[0].verdict.text[:72] if segs else "no output"),
            ))
        return result
    finally:
        for attr in ("adx", "foundry", "model"):
            setattr(FAULTS, attr, getattr(previous, attr))


def chaos_report(r: ChaosResult) -> str:
    head = (f"{'broken':<18}{'degrades to':<34}{'claims':>7}"
            f"{'same numbers':>14}{'failovers':>11}")
    lines = [head, "-" * len(head)]
    for row in r.rows:
        lines.append(
            f"{row.fault:<18}{row.degraded_to:<34}{row.claims:>7}"
            f"{('yes' if row.numbers_identical else 'NO'):>14}"
            f"{row.failovers:>11}")
        if row.detail:
            lines.append(f"    {row.detail}")
    lines.append("-" * len(head))
    lines.append(
        "every single-dependency failure degrades the wording and leaves the\n"
        "numbers alone" if r.ok else "A FALLBACK CHANGED THE NUMBERS")
    return "\n".join(lines)
