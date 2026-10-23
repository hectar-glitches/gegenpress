"""The Form Line: how this match compares to this player's own season.

A single event is the wrong unit. A player's personal best fires about
eight times a match and is almost always league-exceptional too, so the
personal number adds nothing at the extremes.

The unit commentators actually use is the match -- "he's been everywhere
tonight". That is a claim about an aggregate, and it is where the personal
reference class stops agreeing with the league one.

So form is measured as a z-score of this match's mean against the
distribution of that player's own match means across the season. A raw
percentage would not do: a player makes ~90 passes a match but only ~10
carries, so the same percentage swing is routine in one and extraordinary
in the other. The z-score puts every metric on one calibrated scale.
"""

from __future__ import annotations

import statistics as st
from bisect import bisect_left
from collections import defaultdict
from dataclasses import dataclass, field

from .baselines import METRICS
from .models import Match
from .signal import MetricSignal

# A claim needs enough matches to have a norm, and enough events tonight
# for the match mean to mean anything.
MIN_APPEARANCES = 6
MIN_EVENTS_THIS_MATCH = 5
# |z| at which form is statistically worth saying out loud.
NOTABLE_Z = 1.5
# ...and the shift must also be MATERIAL. A player who makes ~90 passes a
# match has a very tight distribution of match means, so a 0.4 m/s drop
# can clear 2 SD while being a difference no viewer would notice.
# Statistical significance is not narrative significance: require the
# shift to be at least this fraction of the league's spread as well.
MIN_EFFECT_VS_LEAGUE_SD = 0.25

# Readable names. Built by hand because chained str.replace on the metric
# keys silently produced "ballpeed" from "ball_speed_ms".
METRIC_LABELS: dict[str, str] = {
    "recovery_time_s": "recovery time",
    "pass_difficulty": "pass difficulty",
    "pass_distance_m": "pass range",
    "ball_speed_ms": "ball speed",
    "top_speed_ms": "top speed",
    "carry_distance_m": "carry range",
    "shot_speed_ms": "shot speed",
    "xg": "shot quality",
}


@dataclass(slots=True)
class FormBaselines:
    """Per-player distributions of match means, plus the league's."""

    # (player_id, metric) -> list of that player's per-match means
    player_match_means: dict[tuple[str, str], list[float]] = field(default_factory=dict)
    # metric -> sorted list of every player-match mean in the league
    league_match_means: dict[str, list[float]] = field(default_factory=dict)


def build_form_baselines(matches: list[Match]) -> FormBaselines:
    per_match: dict[tuple[str, str, str], list[float]] = defaultdict(list)
    for match in matches:
        for e in match.events:
            for metric, (etype, key, _direction) in METRICS.items():
                if e.type != etype:
                    continue
                raw = e.detail.get(key)
                if raw is not None:
                    per_match[(e.player_id, metric, match.match_id)].append(float(raw))

    player_means: dict[tuple[str, str], list[float]] = defaultdict(list)
    league_means: dict[str, list[float]] = defaultdict(list)
    for (player_id, metric, _match_id), values in per_match.items():
        if len(values) < MIN_EVENTS_THIS_MATCH:
            continue
        mean = st.fmean(values)
        player_means[(player_id, metric)].append(mean)
        league_means[metric].append(mean)

    for values in league_means.values():
        values.sort()
    return FormBaselines(dict(player_means), dict(league_means))


@dataclass(slots=True)
class FormLine:
    player_id: str
    player_name: str
    metric: str
    direction: str
    match_mean: float
    season_mean: float
    season_sd: float
    z: float                  # direction-aware: positive always means better
    appearances: int
    events_this_match: int
    as_of_minute: int
    league_percentile: float  # where tonight's mean sits among all player-matches
    effect_vs_league_sd: float  # |shift| as a fraction of league spread
    league_mean: float          # the league's own norm for this metric

    @property
    def above_own_level(self) -> bool:
        return self.z > 0

    @property
    def notable(self) -> bool:
        """Statistically clear AND big enough for anyone to care."""
        return (abs(self.z) >= NOTABLE_Z
                and self.effect_vs_league_sd >= MIN_EFFECT_VS_LEAGUE_SD)

    @property
    def diverges(self) -> bool:
        """Strong for him, ordinary league-wide -- or the reverse.

        This is the property that justifies showing two numbers instead of
        one. If no measurement ever diverges, the Form Line is decoration.
        """
        return (self.z >= NOTABLE_Z and self.league_percentile < 0.80) or (
            self.z <= -NOTABLE_Z and self.league_percentile > 0.20
        )

    def claim(self) -> str:
        unit = "s" if self.metric.endswith("_s") else ""
        pretty = METRIC_LABELS.get(self.metric, self.metric)
        if self.z >= NOTABLE_Z:
            return (f"{self.player_name}: {pretty} {self.match_mean:.1f}{unit} tonight "
                    f"against a season norm of {self.season_mean:.1f}{unit} "
                    f"({self.z:+.1f} SD over {self.appearances} matches).")
        if self.z <= -NOTABLE_Z:
            return (f"{self.player_name}: {pretty} down to {self.match_mean:.1f}{unit} "
                    f"from a season norm of {self.season_mean:.1f}{unit} "
                    f"({self.z:+.1f} SD over {self.appearances} matches).")
        return (f"{self.player_name}: {pretty} {self.match_mean:.1f}{unit}, "
                f"in line with his season norm.")


# Checkpoints at which form is recomputed. Form is an aggregate, so it
# only exists as of some point in the match -- reporting every claim at
# 90' makes a live broadcast look like a post-match report.
CHECKPOINTS = (30, 45, 60, 75, 90)


def form_lines(
    baselines: FormBaselines,
    live: Match,
    signals: dict[str, MetricSignal],
    names: dict[str, str] | None = None,
    as_of_minute: int = 90,
) -> list[FormLine]:
    """Every supportable form claim as of a point in the match."""
    live_values: dict[tuple[str, str], list[float]] = defaultdict(list)
    for e in live.events:
        if e.minute > as_of_minute:
            continue
        for metric, (etype, key, _direction) in METRICS.items():
            if e.type != etype:
                continue
            raw = e.detail.get(key)
            if raw is not None:
                live_values[(e.player_id, metric)].append(float(raw))

    out: list[FormLine] = []
    for (player_id, metric), values in live_values.items():
        signal = signals.get(metric)
        # No between-player signal means "his norm" is the league's norm
        # wearing his name. Refuse the claim rather than dress it up.
        if signal is None or not signal.personal_claim_allowed:
            continue
        if len(values) < MIN_EVENTS_THIS_MATCH:
            continue
        history = baselines.player_match_means.get((player_id, metric), [])
        if len(history) < MIN_APPEARANCES:
            continue

        match_mean = st.fmean(values)
        season_mean = st.fmean(history)
        season_sd = st.pstdev(history)
        if season_sd <= 0:
            continue

        direction = METRICS[metric][2]
        raw_z = (match_mean - season_mean) / season_sd
        z = -raw_z if direction == "low_is_good" else raw_z

        league = baselines.league_match_means.get(metric, [])
        pct = bisect_left(league, match_mean) / len(league) if league else float("nan")
        if direction == "low_is_good":
            pct = 1.0 - pct

        league_mean = st.fmean(league) if league else float("nan")
        league_sd = st.pstdev(league) if len(league) > 1 else 0.0
        effect = abs(match_mean - season_mean) / league_sd if league_sd > 0 else 0.0

        out.append(FormLine(
            player_id=player_id,
            player_name=(names or {}).get(player_id, player_id),
            metric=metric, direction=direction,
            match_mean=round(match_mean, 2),
            season_mean=round(season_mean, 2),
            season_sd=round(season_sd, 3),
            z=round(z, 2),
            appearances=len(history),
            events_this_match=len(values),
            as_of_minute=as_of_minute,
            league_percentile=round(pct, 4),
            effect_vs_league_sd=round(effect, 3),
            league_mean=round(league_mean, 2),
        ))

    out.sort(key=lambda f: -abs(f.z))
    return out


def form_timeline(
    baselines: FormBaselines,
    live: Match,
    signals: dict[str, MetricSignal],
    names: dict[str, str] | None = None,
) -> list[FormLine]:
    """Each claim at the checkpoint where it first becomes notable.

    A player who is two SD above his norm by the hour is a story at the
    hour, not at full time. Walking the checkpoints gives every claim a
    real minute and stops the timeline reading 90' all the way down.
    """
    seen: set[tuple[str, str]] = set()
    timeline: list[FormLine] = []
    for minute in CHECKPOINTS:
        for line in form_lines(baselines, live, signals, names, as_of_minute=minute):
            key = (line.player_id, line.metric)
            if key in seen or not line.notable:
                continue
            seen.add(key)
            timeline.append(line)
    timeline.sort(key=lambda f: f.as_of_minute)
    return timeline
