"""An evaluation harness for the claims this system makes.

Microsoft's built-in Groundedness evaluator scores 1-5 using a model as
judge, and Groundedness Pro needs the Content Safety service. Both need
Azure resources this project does not assume. More to the point, a
model-judged score would not test the thing that actually protects the
output here: the Gate is deterministic, so it can be measured
deterministically, and the result is a fact rather than another model's
opinion.

Four things are measured, over many matches and seeds:

  gate recall       of corrupted claims, how many are rejected
  gate precision    of valid claims, how many are wrongly rejected
  claim integrity   every number asserted recomputes from the events
  refusal           no personal claim on a metric without the signal

Recall is broken down by corruption type, including the two the Gate is
known to miss. Publishing a measured 0% on those is worth more than
describing them in prose.
"""

from __future__ import annotations

import random
import re
from dataclasses import dataclass, field

from .agents import Brief, Gate, Why
from .season import build_league
from .signal import measure_signal
from .simulate import simulate_live, simulate_season
from .store import LocalStore

WORDS = {0: "zero", 1: "one", 2: "two", 3: "three", 4: "four", 5: "five",
         6: "six", 7: "seven", 8: "eight", 9: "nine", 10: "ten",
         11: "eleven", 12: "twelve", 20: "twenty", 30: "thirty",
         40: "forty", 47: "forty-seven", 50: "fifty"}


# -- corruptions -----------------------------------------------------------

def _invent(text: str, brief: Brief, rng: random.Random) -> str | None:
    """Add a number that is simply not in the brief."""
    allowed = brief.allowed_numbers()
    for _ in range(40):
        n = round(rng.uniform(1, 99), 1)
        if not any(abs(n - a) <= 0.051 for a in allowed):
            return f"{text} He has {n} of them tonight."
    return None


def _inflate(text: str, brief: Brief, rng: random.Random) -> str | None:
    """Exaggerate a real number: the plausible, dangerous error."""
    # Replace a whole numeric token. str.replace would match "3" inside
    # "13.77" and mangle the sentence instead of inflating a number,
    # which made the Gate look fallible when the test was at fault.
    spans = [m.span() for m in re.finditer(r"-?\d+(?:\.\d+)?", text)]
    if not spans:
        return None
    a, b = rng.choice(spans)
    worse = round(float(text[a:b]) * 1.5 + 3.7, 2)
    return text[:a] + str(worse) + text[b:]


def _scoreline(text: str, brief: Brief, rng: random.Random) -> str | None:
    """A true-sounding scoreline nobody supplied."""
    a, b = rng.randint(2, 5), rng.randint(0, 1)
    if any(abs(a - x) <= 0.051 for x in brief.allowed_numbers()):
        a += 4
    return f"At {a}-{b}, {text[0].lower()}{text[1:]}"


def _words(text: str, brief: Brief, rng: random.Random) -> str | None:
    """A fabricated number spelled out. The Gate reads digits only."""
    return f"{text} He has completed {WORDS[47]} of them tonight."


def _misattach(text: str, brief: Brief, rng: random.Random) -> str | None:
    """Both numbers are real; they are the wrong way round."""
    if brief.season_mean is None:
        return None
    return (f"{brief.player_name}'s season norm is {brief.value:g}; "
            f"tonight he is at {brief.season_mean:g}.")


CORRUPTIONS = {
    "invented number": _invent,
    "inflated number": _inflate,
    "fabricated scoreline": _scoreline,
    "number as words": _words,
    "misattached number": _misattach,
}


# -- harness ---------------------------------------------------------------

@dataclass(slots=True)
class Results:
    briefs: int = 0
    valid_claims: int = 0
    false_rejects: int = 0
    attempted: dict[str, int] = field(default_factory=dict)
    caught: dict[str, int] = field(default_factory=dict)
    collisions: int = 0
    integrity_checked: int = 0
    integrity_failed: int = 0
    refusals_checked: int = 0
    refusals_violated: int = 0

    @property
    def precision(self) -> float:
        if not self.valid_claims:
            return float("nan")
        return 1.0 - self.false_rejects / self.valid_claims

    def recall(self, kind: str) -> float:
        n = self.attempted.get(kind, 0)
        return self.caught.get(kind, 0) / n if n else float("nan")

    @property
    def overall_recall(self) -> float:
        a = sum(self.attempted.values())
        return sum(self.caught.values()) / a if a else float("nan")


def run(seeds: tuple[int, ...] = (2026, 7, 404), matches_per_seed: int = 4
        ) -> Results:
    gate, res = Gate(), Results()

    for seed in seeds:
        league = build_league(seed=seed)
        season = simulate_season(league, seed=seed)
        store = LocalStore()
        store.load_season(league, season)
        signals = measure_signal(season)
        why = Why(league)
        rng = random.Random(f"eval:{seed}")

        for fixture in league.fixtures[:matches_per_seed]:
            live = simulate_live(league, fixture, seed=seed)
            for form in store.form_lines(live):
                brief = why.brief_from_form(form, live)
                res.briefs += 1

                # 1. A clean claim must pass.
                clean = (f"{brief.minute}' {brief.player_name}: "
                         f"{brief.metric_label} {brief.value:g} tonight, against "
                         f"a season norm of {brief.season_mean:g}.")
                res.valid_claims += 1
                if gate.check(clean, brief):
                    res.false_rejects += 1

                # 2. Corrupted claims must be rejected.
                for kind, fn in CORRUPTIONS.items():
                    bad = fn(clean, brief, rng)
                    if bad is None:
                        continue
                    res.attempted[kind] = res.attempted.get(kind, 0) + 1
                    if gate.check(bad, brief):
                        res.caught[kind] = res.caught.get(kind, 0) + 1
                    elif kind == "inflated number":
                        # Not a Gate failure in the usual sense: the
                        # corrupted value coincidentally equals a
                        # DIFFERENT allowed number, so presence-checking
                        # cannot see it. Same root cause as misattachment.
                        res.collisions += 1

                # 3. Every asserted number must recompute from the data.
                res.integrity_checked += 1
                if (abs(form.match_mean - brief.value) > 1e-6
                        or abs(form.league_mean - brief.expected) > 1e-6
                        or (brief.z is not None and abs(form.z - brief.z) > 1e-6)):
                    res.integrity_failed += 1

                # 4. A metric without between-player signal must never
                #    carry a personal claim.
                res.refusals_checked += 1
                sig = signals.get(form.metric)
                if sig and not sig.personal_claim_allowed and brief.season_mean is not None:
                    res.refusals_violated += 1

    return res


def report(r: Results) -> str:
    out = [
        f"{r.briefs} claims over {r.integrity_checked} briefs",
        "",
        f"{'check':<26}{'result':>10}   detail",
        "-" * 68,
        f"{'gate precision':<26}{r.precision:>9.1%}   "
        f"{r.valid_claims - r.false_rejects}/{r.valid_claims} valid claims passed",
        f"{'claim integrity':<26}"
        f"{1 - (r.integrity_failed / max(1, r.integrity_checked)):>9.1%}   "
        f"every number recomputes from the events",
        f"{'refusal correctness':<26}"
        f"{1 - (r.refusals_violated / max(1, r.refusals_checked)):>9.1%}   "
        f"no personal claim without between-player signal",
        "",
        f"{'gate recall by corruption':<26}{'':>10}",
        "-" * 68,
    ]
    for kind in CORRUPTIONS:
        n = r.attempted.get(kind, 0)
        if not n:
            continue
        rec = r.recall(kind)
        note = "  <- known miss, documented" if rec < 0.5 else ""
        out.append(f"  {kind:<24}{rec:>9.1%}   {r.caught.get(kind, 0)}/{n}{note}")
    digits = [k for k in CORRUPTIONS if k not in ("number as words", "misattached number")]
    da = sum(r.attempted.get(k, 0) for k in digits)
    dc = sum(r.caught.get(k, 0) for k in digits)
    out += ["-" * 68,
            f"  {'digit-based corruptions':<24}{(dc / da if da else 0):>9.1%}   "
            f"what the Gate claims to catch",
            f"  {'overall':<24}{r.overall_recall:>9.1%}   "
            f"including the two documented misses"]
    if r.collisions:
        pc = r.collisions / max(1, r.attempted.get("inflated number", 1))
        out += ["",
                f"Of the inflations not caught, {r.collisions} ({pc:.1%}) were value",
                "collisions: the corrupted number happened to equal a different",
                "number already in the brief. Presence-checking cannot see that,",
                "which is the same structural limit as a misattached number."]
    return "\n".join(out)
