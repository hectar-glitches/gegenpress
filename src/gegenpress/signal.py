"""Which metrics can carry a personal claim, and which cannot.

"His best press in six games" is only a meaningful sentence if that
player's distribution for that metric is actually distinguishable from the
league's. For some metrics it is not -- recovery time measures how long a
possession lasted, which is a property of the match, not of whoever
happened to win the ball back. Counter-pressing is a team behaviour.

So the system measures the signal and refuses the claim when it is absent,
rather than asserting "his season best" about a number that is league
noise with his name on it.

The measure is the intraclass correlation:

    ICC = between-player variance / (between-player + within-player)

ICC near 0 means every player's distribution is the league's. ICC near 1
means players are cleanly separable.
"""

from __future__ import annotations

import statistics as st
from collections import defaultdict
from dataclasses import dataclass

from .baselines import METRICS
from .models import Match

# Below this, a personal claim is not supportable. Chosen so that metrics
# driven by player attributes clear it and metrics that are match-level
# properties do not. See docs: the gap in the measured values is wide
# (0.02 and below vs 0.09 and above), so the threshold is not delicate.
PERSONAL_CLAIM_ICC = 0.08

MIN_SAMPLES_PER_PLAYER = 50
MIN_PLAYERS = 10


@dataclass(frozen=True, slots=True)
class MetricSignal:
    metric: str
    icc: float
    players: int
    lowest_player_mean: float
    highest_player_mean: float

    @property
    def personal_claim_allowed(self) -> bool:
        return self.icc >= PERSONAL_CLAIM_ICC

    @property
    def verdict(self) -> str:
        return "personal + league" if self.personal_claim_allowed else "league only"


def measure_signal(matches: list[Match]) -> dict[str, MetricSignal]:
    """Compute per-metric ICC across a season."""
    samples: dict[str, dict[str, list[float]]] = defaultdict(lambda: defaultdict(list))
    for match in matches:
        for e in match.events:
            for metric, (etype, key, _direction) in METRICS.items():
                if e.type != etype:
                    continue
                raw = e.detail.get(key)
                if raw is not None:
                    samples[metric][e.player_id].append(float(raw))

    out: dict[str, MetricSignal] = {}
    for metric, players in samples.items():
        groups = [v for v in players.values() if len(v) >= MIN_SAMPLES_PER_PLAYER]
        if len(groups) < MIN_PLAYERS:
            continue
        means = [st.fmean(g) for g in groups]
        between = st.pvariance(means)
        within = st.fmean([st.pvariance(g) for g in groups if len(g) > 1])
        icc = between / (between + within) if (between + within) else 0.0
        out[metric] = MetricSignal(
            metric=metric, icc=round(icc, 4), players=len(groups),
            lowest_player_mean=round(min(means), 2),
            highest_player_mean=round(max(means), 2),
        )
    return out


def report(signals: dict[str, MetricSignal]) -> str:
    rows = sorted(signals.values(), key=lambda s: -s.icc)
    lines = [
        f"{'metric':<18}{'ICC':>7}{'players':>9}{'player means':>22}   claims allowed",
        "-" * 82,
    ]
    for s in rows:
        span = f"{s.lowest_player_mean} to {s.highest_player_mean}"
        lines.append(f"{s.metric:<18}{s.icc:>7.3f}{s.players:>9}{span:>22}   {s.verdict}")
    allowed = sum(1 for s in rows if s.personal_claim_allowed)
    lines.append("-" * 82)
    lines.append(
        f"{allowed}/{len(rows)} metrics support a personal claim "
        f"(ICC >= {PERSONAL_CLAIM_ICC})"
    )
    return "\n".join(lines)
