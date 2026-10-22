"""Realism check for the synthetic season.

The hackathon scores "creativity and optimized synthetic data creation".
A generator nobody has checked is a liability; one with a published
calibration table is evidence. Reference values are widely reported
Premier League per-match averages, used here only as plausibility targets
for synthetic output -- no real match data is ingested or redistributed.
"""

from __future__ import annotations

from dataclasses import dataclass

from .models import Match

# metric -> (target, tolerance, unit)
TARGETS: dict[str, tuple[float, float, str]] = {
    "goals_per_match": (2.80, 0.60, ""),
    "shots_per_match": (25.0, 7.0, ""),
    "passes_per_match": (900.0, 180.0, ""),
    "pass_accuracy": (0.82, 0.06, ""),
    "mean_shot_xg": (0.10, 0.04, ""),
    "recoveries_per_match": (210.0, 70.0, ""),
    "events_per_match": (2000.0, 900.0, ""),
}


@dataclass(slots=True)
class Check:
    metric: str
    observed: float
    target: float
    tolerance: float

    @property
    def passed(self) -> bool:
        return abs(self.observed - self.target) <= self.tolerance

    @property
    def delta(self) -> float:
        return self.observed - self.target


def measure(matches: list[Match]) -> dict[str, float]:
    n = len(matches)
    if not n:
        raise ValueError("no matches")

    goals = sum(m.home_goals + m.away_goals for m in matches)
    shots = passes = passes_ok = recoveries = events = 0
    xg_total = 0.0

    for m in matches:
        events += len(m.events)
        for e in m.events:
            if e.type == "shot":
                shots += 1
                xg_total += float(e.detail.get("xg", 0.0))
            elif e.type == "pass":
                passes += 1
                passes_ok += 1 if e.outcome else 0
            elif e.type == "recovery":
                recoveries += 1

    return {
        "goals_per_match": goals / n,
        "shots_per_match": shots / n,
        "passes_per_match": passes / n,
        "pass_accuracy": passes_ok / passes if passes else 0.0,
        "mean_shot_xg": xg_total / shots if shots else 0.0,
        "recoveries_per_match": recoveries / n,
        "events_per_match": events / n,
    }


def run_checks(matches: list[Match]) -> list[Check]:
    observed = measure(matches)
    return [
        Check(metric=k, observed=observed[k], target=t, tolerance=tol)
        for k, (t, tol, _unit) in TARGETS.items()
    ]


def report(checks: list[Check]) -> str:
    lines = [
        f"{'metric':<24}{'observed':>10}{'target':>10}{'tol':>8}  result",
        "-" * 62,
    ]
    for c in checks:
        mark = "pass" if c.passed else "FAIL"
        lines.append(
            f"{c.metric:<24}{c.observed:>10.2f}{c.target:>10.2f}{c.tolerance:>8.2f}  {mark}"
        )
    passed = sum(1 for c in checks if c.passed)
    lines.append("-" * 62)
    lines.append(f"{passed}/{len(checks)} checks passed")
    return "\n".join(lines)
