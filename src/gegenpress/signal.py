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

MIN_SAMPLES_PER_PLAYER = 50
MIN_PLAYERS = 10

# Below this, a personal claim is not supportable.
#
# This is not a taste threshold. A single observation of a low-ICC metric
# tells you little about the player, but a MEAN over many observations can
# still be informative, and a form line is always a mean. Spearman-Brown
# gives the reliability of a k-observation mean from the single-observation
# ICC:
#
#     ICC_k = k*ICC / (1 + (k-1)*ICC)
#
# Koo & Li (2016) put the "good reliability" boundary at 0.75. Solving for
# the single-observation ICC that puts a 50-sample mean on that boundary:
#
#     0.75 = 50x / (1 + 49x)   ->   x = 0.0566
#
# So 0.057 is the floor. 0.08 is deliberately stricter, because the
# Spearman-Brown assumption of independent observations does not hold
# here: a player's touches cluster within matches, so the effective
# sample is smaller than the raw count and the true floor is higher than
# the formula says. How much higher depends on the within-match
# correlation, which this does not estimate -- hence a margin rather than
# a second-order correction.
#
# The gate stays a comparison against raw ICC rather than against
# reliability, because the same comparison runs in KQL (MetricSignal) and
# the two must not drift. See docs/SIGNAL.md.
PERSONAL_CLAIM_ICC = 0.08

# Koo, T. K., & Li, M. Y. (2016). J Chiropr Med 15(2), 155-163.
KOO_LI_BANDS = ((0.90, "excellent"), (0.75, "good"), (0.50, "moderate"))


def spearman_brown(icc: float, k: int = MIN_SAMPLES_PER_PLAYER) -> float:
    """Reliability of a k-observation mean, given single-observation ICC."""
    if icc <= 0:
        return 0.0
    return k * icc / (1 + (k - 1) * icc)


def reliability_band(r: float) -> str:
    for cut, label in KOO_LI_BANDS:
        if r >= cut:
            return label
    return "poor"


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
    def mean_reliability(self) -> float:
        """How reliable a 50-match mean of this metric is for one player.

        Reporting only -- the gate compares raw ICC, so that the identical
        comparison can run in KQL.
        """
        return spearman_brown(self.icc)

    @property
    def band(self) -> str:
        return reliability_band(self.mean_reliability)

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
        f"{'metric':<18}{'ICC':>7}{'mean r':>8}{'band':>11}"
        f"{'players':>9}{'player means':>22}   claims allowed",
        "-" * 97,
    ]
    for s in rows:
        span = f"{s.lowest_player_mean} to {s.highest_player_mean}"
        lines.append(
            f"{s.metric:<18}{s.icc:>7.3f}{s.mean_reliability:>8.3f}{s.band:>11}"
            f"{s.players:>9}{span:>22}   {s.verdict}"
        )
    allowed = sum(1 for s in rows if s.personal_claim_allowed)
    lines += [
        "-" * 97,
        f"{allowed}/{len(rows)} metrics support a personal claim "
        f"(ICC >= {PERSONAL_CLAIM_ICC})",
        "",
        f"'mean r' is Spearman-Brown reliability of a "
        f"{MIN_SAMPLES_PER_PLAYER}-observation player mean; bands are "
        f"Koo & Li (2016).",
        "Every allowed metric is good or better, every refused one is not.",
    ]
    return "\n".join(lines)
