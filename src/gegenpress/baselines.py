"""Turn a simulated season into the two reference classes.

This is the heart of Gegenpress. Every live measurement is scored twice:

  population  -- how does this compare to everyone in the league?
  personal    -- how does this compare to this player's own season?

The second one is what commentators actually do ("his best press in six
games"), and it is only meaningful because players carry permanent
attributes across the season.
"""

from __future__ import annotations

import statistics
from bisect import bisect_left
from dataclasses import dataclass, field
from typing import Iterable

from .models import Event, Match

# metric name -> (event type, detail key, direction)
# direction = "low_is_good" or "high_is_good"; it decides which tail counts
# as remarkable.
METRICS: dict[str, tuple[str, str, str]] = {
    "recovery_time_s": ("recovery", "recovery_time_s", "low_is_good"),
    "pass_difficulty": ("pass", "pass_difficulty", "high_is_good"),
    "pass_distance_m": ("pass", "pass_distance_m", "high_is_good"),
    "ball_speed_ms": ("pass", "ball_speed_ms", "high_is_good"),
    "top_speed_ms": ("carry", "top_speed_ms", "high_is_good"),
    "carry_distance_m": ("carry", "carry_distance_m", "high_is_good"),
    "shot_speed_ms": ("shot", "shot_speed_ms", "high_is_good"),
    "xg": ("shot", "xg", "high_is_good"),
}


@dataclass(slots=True)
class Distribution:
    """A sorted sample, which is all we need for percentiles and expectation."""

    values: list[float] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.values.append(value)

    def seal(self) -> None:
        self.values.sort()

    @property
    def n(self) -> int:
        return len(self.values)

    @property
    def mean(self) -> float:
        return statistics.fmean(self.values) if self.values else float("nan")

    @property
    def median(self) -> float:
        return statistics.median(self.values) if self.values else float("nan")

    def best(self, direction: str) -> float:
        if not self.values:
            return float("nan")
        return self.values[0] if direction == "low_is_good" else self.values[-1]

    def percentile_of(self, value: float) -> float:
        """Share of the sample at or below `value`, 0.0-1.0."""
        if not self.values:
            return float("nan")
        return bisect_left(self.values, value) / len(self.values)


@dataclass(slots=True)
class Baselines:
    population: dict[str, Distribution] = field(default_factory=dict)
    # (player_id, metric) -> Distribution
    personal: dict[tuple[str, str], Distribution] = field(default_factory=dict)
    # (player_id, metric, match_id) -> Distribution, for per-match bests
    per_match: dict[tuple[str, str, str], Distribution] = field(default_factory=dict)

    def seal(self) -> None:
        for d in self.population.values():
            d.seal()
        for d in self.personal.values():
            d.seal()
        for d in self.per_match.values():
            d.seal()


def _iter_values(events: Iterable[Event]) -> Iterable[tuple[str, str, float]]:
    """Yield (metric, player_id, value) for every measurable event."""
    for e in events:
        for metric, (etype, key, _direction) in METRICS.items():
            if e.type != etype:
                continue
            value = e.detail.get(key)
            if value is None:
                continue
            yield metric, e.player_id, float(value)


def build_baselines(matches: list[Match]) -> Baselines:
    b = Baselines()
    for match in matches:
        for metric, player_id, value in _iter_values(match.events):
            b.population.setdefault(metric, Distribution()).add(value)
            b.personal.setdefault((player_id, metric), Distribution()).add(value)
            b.per_match.setdefault((player_id, metric, match.match_id), Distribution()).add(value)
    b.seal()
    return b


@dataclass(slots=True)
class Grounding:
    """Everything the narrative layer is allowed to assert about one value.

    The Why agent picks which reference class to lead on; it never invents
    a number that isn't in here.
    """

    metric: str
    value: float
    direction: str
    expected: float
    population_percentile: float
    population_n: int
    personal_mean: float | None
    personal_percentile: float | None
    personal_best: float | None
    personal_n: int
    is_personal_best: bool
    # Set from signal.measure_signal(); when False the metric has no
    # between-player signal and only league claims are permitted.
    personal_claim_allowed: bool = True

    @property
    def remarkable(self) -> float:
        """0.0-1.0: the share of the league this value beats.

        For a high-is-good metric that is the percentile itself. For a
        low-is-good metric (recovery time) a low value is strong, so the
        share beaten is the complement.
        """
        p = self.population_percentile
        return p if self.direction == "high_is_good" else 1.0 - p

    def headline(self, player_name: str) -> str:
        unit = "s" if self.metric.endswith("_s") else ""
        lead = f"{self.value:g}{unit} (expected {self.expected:.1f}{unit})"
        if self.is_personal_best and self.personal_n >= 5:
            return f"{player_name}: {lead} — his season best."
        if self.personal_mean is not None:
            return f"{player_name}: {lead}; his average is {self.personal_mean:.1f}{unit}."
        return f"{player_name}: {lead}"


def ground(baselines: Baselines, metric: str, player_id: str, value: float,
           personal_claim_allowed: bool = True) -> Grounding:
    """Score one live measurement against both reference classes."""
    _etype, _key, direction = METRICS[metric]
    pop = baselines.population.get(metric, Distribution())
    personal = baselines.personal.get((player_id, metric))

    pop_pct = pop.percentile_of(value)
    personal_best = personal.best(direction) if personal and personal.n else None
    is_best = False
    if personal_best is not None:
        is_best = value <= personal_best if direction == "low_is_good" else value >= personal_best

    return Grounding(
        metric=metric,
        value=value,
        direction=direction,
        expected=pop.median,
        population_percentile=round(pop_pct, 4),
        population_n=pop.n,
        personal_mean=personal.mean if personal and personal.n else None,
        personal_percentile=round(personal.percentile_of(value), 4) if personal and personal.n else None,
        personal_best=personal_best,
        personal_n=personal.n if personal else 0,
        is_personal_best=is_best,
        personal_claim_allowed=personal_claim_allowed,
    )


def rarity(baselines: Baselines, metric: str, value: float) -> float:
    """Share of the league this value beats, 0.0-1.0. Used to rank moments."""
    _etype, _key, direction = METRICS[metric]
    pop = baselines.population.get(metric, Distribution())
    pct = pop.percentile_of(value)
    return pct if direction == "high_is_good" else 1.0 - pct
