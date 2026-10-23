"""Where match state lives.

Two implementations behind one interface:

  LocalStore  -- pure Python, no Azure, no network. Always works.
  AdxStore    -- Azure Data Explorer / Fabric Eventhouse, running the KQL
                 in kql/02_functions.kql.

The agent layer talks to this interface and does not care which is behind
it. That is deliberate: it means the pipeline is never blocked on a cloud
resource, and the demo has a working fallback if a quota bites on the day.

The two are meant to agree. `tests/test_parity.py` checks that they do,
and is skipped when no cluster is configured.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any, Protocol

from .baselines import METRICS, Baselines, build_baselines, ground
from .form import FormBaselines, FormLine, build_form_baselines, form_lines
from .signal import MetricSignal, measure_signal
from .models import Match
from .season import League


@dataclass(slots=True)
class GroundedMoment:
    """One live measurement, scored against both reference classes.

    This is the only thing the narrative layer may assert. If a number is
    not on this object, the model is not allowed to say it.
    """

    event_id: str
    minute: int
    player_id: str
    player_name: str
    team_id: str
    metric: str
    value: float
    direction: str
    expected: float
    beats: float            # share of the league this beats, 0-1
    population_n: int
    personal_mean: float | None
    personal_best: float | None
    personal_n: int
    is_personal_best: bool
    personal_claim_allowed: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "event_id": self.event_id, "minute": self.minute,
            "player_id": self.player_id, "player_name": self.player_name,
            "team_id": self.team_id, "metric": self.metric,
            "value": round(self.value, 3), "expected": round(self.expected, 3),
            "beats": round(self.beats, 4), "population_n": self.population_n,
            "personal_mean": None if self.personal_mean is None else round(self.personal_mean, 3),
            "personal_best": None if self.personal_best is None else round(self.personal_best, 3),
            "personal_n": self.personal_n,
            "is_personal_best": self.is_personal_best,
            "personal_claim_allowed": self.personal_claim_allowed,
        }


class Store(Protocol):
    def load_season(self, league: League, matches: list[Match]) -> None: ...
    def top_moments(self, live: Match, min_beats: float = 0.97, limit: int = 20
                    ) -> list[GroundedMoment]: ...
    def match_state(self, live: Match, as_of_minute: int = 120,
                    window_minutes: int = 15) -> dict[str, dict[str, float]]: ...
    def follow_target(self, live: Match, as_of_minute: int = 120
                      ) -> list[tuple[str, float]]: ...


class LocalStore:
    """Python implementation. Mirrors kql/02_functions.kql."""

    def __init__(self) -> None:
        self._baselines: Baselines | None = None
        self._league: League | None = None
        self._signal: dict[str, MetricSignal] = {}
        self._form: FormBaselines | None = None

    def load_season(self, league: League, matches: list[Match]) -> None:
        self._league = league
        self._baselines = build_baselines(matches)
        self._signal = measure_signal(matches)
        self._form = build_form_baselines(matches)

    def _require(self) -> tuple[League, Baselines]:
        if self._league is None or self._baselines is None:
            raise RuntimeError("call load_season() first")
        return self._league, self._baselines

    def _grounded(self, live: Match):
        league, baselines = self._require()
        for e in live.events:
            for metric, (etype, key, _direction) in METRICS.items():
                if e.type != etype:
                    continue
                raw = e.detail.get(key)
                if raw is None:
                    continue
                sig = self._signal.get(metric)
                allowed = sig.personal_claim_allowed if sig else False
                g = ground(baselines, metric, e.player_id, float(raw), allowed)
                yield GroundedMoment(
                    event_id=e.event_id, minute=e.minute, player_id=e.player_id,
                    player_name=league.player(e.player_id).name, team_id=e.team_id,
                    metric=metric, value=float(raw), direction=g.direction,
                    expected=g.expected, beats=g.remarkable,
                    population_n=g.population_n, personal_mean=g.personal_mean,
                    personal_best=g.personal_best, personal_n=g.personal_n,
                    is_personal_best=g.is_personal_best,
                    personal_claim_allowed=g.personal_claim_allowed,
                )

    def top_moments(self, live: Match, min_beats: float = 0.97, limit: int = 20):
        found = [m for m in self._grounded(live) if m.beats >= min_beats]
        found.sort(key=lambda m: -m.beats)
        return found[:limit]

    def form_lines(self, live: Match, notable_only: bool = True) -> list[FormLine]:
        """How each player's match compares to his own season."""
        league, _baselines = self._require()
        if self._form is None:
            raise RuntimeError("call load_season() first")
        names = {p.player_id: p.name for p in league.players}
        lines = form_lines(self._form, live, self._signal, names)
        return [f for f in lines if f.notable] if notable_only else lines

    def match_state(self, live: Match, as_of_minute: int = 120, window_minutes: int = 15):
        lo = as_of_minute - window_minutes
        teams: dict[str, dict[str, float]] = {}
        for e in live.events:
            if not (lo < e.minute <= as_of_minute):
                continue
            s = teams.setdefault(e.team_id, {
                "passes": 0, "passes_completed": 0, "progressive": 0, "shots": 0,
                "xg": 0.0, "recoveries": 0, "high_recoveries": 0,
                "pressure_events": 0, "_rec_sum": 0.0, "_rec_n": 0,
                "final_third": 0, "touches": 0,
            })
            if e.type == "pass":
                s["passes"] += 1
                s["passes_completed"] += 1 if e.outcome else 0
                s["progressive"] += 1 if e.detail.get("progressive") else 0
            elif e.type == "shot":
                s["shots"] += 1
                s["xg"] += float(e.detail.get("xg", 0.0))
            elif e.type == "recovery":
                s["recoveries"] += 1
                s["high_recoveries"] += 1 if e.detail.get("in_final_third") else 0
                rt = e.detail.get("recovery_time_s")
                if rt is not None:
                    s["_rec_sum"] += float(rt)
                    s["_rec_n"] += 1
            elif e.type == "pressure":
                s["pressure_events"] += 1
            if e.type in ("pass", "carry"):
                s["touches"] += 1
                if e.x > 70.0:
                    s["final_third"] += 1

        out: dict[str, dict[str, float]] = {}
        total_final_third = sum(s["final_third"] for s in teams.values())
        for team_id, s in teams.items():
            mean_recovery = s["_rec_sum"] / s["_rec_n"] if s["_rec_n"] else float("nan")
            gp = (
                (s["high_recoveries"] / (1 + s["recoveries"])) * 0.6
                + (1.0 / (1.0 + (mean_recovery if mean_recovery == mean_recovery else 0.0))) * 12.0 * 0.4
            )
            out[team_id] = {
                "passes": s["passes"],
                "pass_accuracy": round(s["passes_completed"] / s["passes"], 3) if s["passes"] else 0.0,
                "progressive": s["progressive"],
                "shots": s["shots"],
                "xg": round(s["xg"], 3),
                "recoveries": s["recoveries"],
                "high_recoveries": s["high_recoveries"],
                "pressure_events": s["pressure_events"],
                "mean_recovery_s": round(mean_recovery, 1) if s["_rec_n"] else None,
                # Share of all final-third touches in the window. Unlike a
                # mean x, this is comparable between the two teams.
                "field_tilt": (round(s["final_third"] / total_final_third, 3)
                               if total_final_third else None),
                "final_third_touches": s["final_third"],
                "gegenpress_idx": round(gp, 3),
            }
        return out

    def follow_target(self, live: Match, as_of_minute: int = 120):
        agg: dict[tuple[str, str], dict[str, float]] = {}
        for m in self._grounded(live):
            if (m.minute > as_of_minute or m.personal_mean is None
                    or m.personal_n < 50 or not m.personal_claim_allowed):
                continue
            lift = ((m.personal_mean - m.value) / m.personal_mean
                    if m.direction == "low_is_good"
                    else (m.value - m.personal_mean) / m.personal_mean)
            a = agg.setdefault((m.player_id, m.team_id),
                               {"moments": 0, "lift": 0.0, "best": 0.0, "pbs": 0})
            a["moments"] += 1
            a["lift"] += lift
            a["best"] = max(a["best"], m.beats)
            a["pbs"] += 1 if m.is_personal_best else 0

        ranked = []
        for (player_id, _team), a in agg.items():
            if a["moments"] < 5:
                continue
            score = (a["lift"] / a["moments"]) * 0.5 + a["best"] * 0.3 + a["pbs"] * 0.2
            ranked.append((player_id, round(score, 4)))
        ranked.sort(key=lambda r: -r[1])
        return ranked


def get_store(prefer_adx: bool | None = None) -> Store:
    """Pick a store.

    Uses ADX when a cluster is configured and the SDK is importable;
    otherwise falls back to local and says so. Never raises just because
    Azure is missing -- that is the whole point of the fallback.
    """
    if prefer_adx is None:
        prefer_adx = bool(os.environ.get("ADX_CLUSTER"))
    if prefer_adx:
        try:
            from .adx import AdxStore  # noqa: PLC0415
            return AdxStore.from_env()
        except Exception as exc:  # pragma: no cover - depends on local env
            print(f"[store] ADX unavailable ({exc}); using local store")
    return LocalStore()
