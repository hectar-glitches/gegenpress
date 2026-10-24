"""The broadcast feed: everything the console and the overlay render.

One JSON document per match. The console is a static page over this file,
which means it deploys anywhere, films well offline, and cannot silently
depend on a service being up during the demo.

Overlay cues carry a timestamp and a duration so a rendering partner can
drop them onto a live feed without re-deriving anything.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from typing import Any

from .agents import Segment, run_desk
from .form import METRIC_LABELS
from .models import Match
from .season import League
from .positions import (build_ball_track, build_frames, pack,
                        pack_ball, pick_window)
from .signal import measure_signal
from .store import Store

# How long a graphic stays on screen, by kind.
OVERLAY_SECONDS = {"form": 6.0, "moment": 4.5}


@dataclass(slots=True)
class OverlayCue:
    """Timed, machine-readable, renderable without further computation."""

    cue_id: str
    at_second: float
    duration: float
    kind: str
    headline: str
    primary: str        # the big number
    secondary: str      # the comparison
    footnote: str
    player: str
    club: str
    diverges: bool


def _cue(index: int, seg: Segment) -> OverlayCue:
    b = seg.brief
    primary = f"{b.value:g}"
    if b.season_mean is not None:
        secondary = f"his season norm {b.season_mean:g}"
        footnote = f"{b.z:+.1f} SD over {b.appearances} matches"
    else:
        secondary = f"league expected {b.expected:g}"
        footnote = f"beats {b.beats_pct:.0f}% of the league"
    return OverlayCue(
        cue_id=f"cue-{index:03d}",
        at_second=float(b.minute * 60),
        duration=OVERLAY_SECONDS["form" if b.season_mean is not None else "moment"],
        kind="form" if b.season_mean is not None else "moment",
        headline=seg.verdict.text,
        primary=primary,
        secondary=secondary,
        footnote=footnote,
        player=b.player_name,
        club=b.club_name,
        diverges=b.diverges,
    )


def contributing_events(live: Match, player_id: str, metric: str,
                        as_of_minute: int, cap: int = 80) -> list[dict[str, Any]]:
    """The events behind one form line, for the pitch view.

    A form line is a mean. These are the touches it is a mean OF, so the
    console can show where the player actually played rather than
    illustrating the claim with a stock graphic.
    """
    from .baselines import METRICS

    etype, key, _direction = METRICS[metric]
    out: list[dict[str, Any]] = []
    for e in live.events:
        if e.type != etype or e.player_id != player_id or e.minute > as_of_minute:
            continue
        value = e.detail.get(key)
        if value is None:
            continue
        out.append({
            "minute": e.minute,
            "x": e.x, "y": e.y,
            "end_x": e.end_x, "end_y": e.end_y,
            "value": round(float(value), 2),
            "outcome": e.outcome,
        })
    return out[:cap]


def event_stream(live: Match) -> list[dict[str, Any]]:
    """The whole match, time-indexed, for the pitch to play.

    Without this the console has nothing to show between moments, which
    is why it read as a dashboard: the match itself was invisible.
    Compact keys -- this is the largest thing in the feed.
    """
    # Explicit codes: first letters collide (pass/pressure, tackle/turnover)
    # and a silent collision here would mis-draw the whole match.
    CODE = {"pass": "pa", "carry": "ca", "shot": "sh", "tackle": "ta",
            "pressure": "pr", "recovery": "re", "duel": "du", "turnover": "to"}
    out: list[dict[str, Any]] = []
    for e in live.events:
        row = {
            "t": round((e.period - 1) * 2700 + e.clock, 1),
            "k": CODE[e.type],
            "m": e.team_id,
            "x": e.x, "y": e.y,
        }
        if e.end_x is not None:
            row["X"] = e.end_x
            row["Y"] = e.end_y
        if e.outcome is False:
            row["f"] = 1                    # failed
        if e.type == "shot":
            row["g"] = 1 if e.outcome else 0
        out.append(row)
    return out


def build_feed(
    store: Store,
    league: League,
    live: Match,
    season: list[Match],
    model: Any = None,
    limit: int = 8,
    span: int = 240,
) -> dict[str, Any]:
    home, away = league.club(live.home_club_id), league.club(live.away_club_id)
    segments = run_desk(store, league, live, model=model, limit=limit)

    signals = measure_signal(season)
    follow = store.follow_target(live, as_of_minute=90)[:6]
    state = store.match_state(live, as_of_minute=90, window_minutes=90)

    moments = []
    for seg in segments:
        b = seg.brief
        moments.append({
            "minute": b.minute,
            "player": b.player_name,
            "club": b.club_name,
            "metric": b.metric_label,
            "text": seg.verdict.text,
            "value": b.value,
            "expected": b.expected,
            "league_pct": round(b.beats_pct, 1),
            "season_mean": b.season_mean,
            "z": b.z,
            "appearances": b.appearances,
            "diverges": b.diverges,
            "above": (b.z or 0) > 0,
            "events": contributing_events(
                live, seg.form_player_id, seg.form_metric, b.minute)
            if seg.form_player_id else [],
            "grounded": seg.verdict.passed,
            "model": seg.verdict.model,
            "attempts": seg.verdict.attempts,
            "fell_back": seg.verdict.fell_back,
        })

    # Showcase window: a real passage of the real match, SELECTED not
    # fabricated. Centred on the strongest diverging moment, because that
    # is the one the whole project exists to show.
    diverging = [m for m in moments if m["diverges"]] or moments
    centre = max(diverging, key=lambda m: abs(m.get("z") or 0))["minute"]
    lo, hi = pick_window(live, centre, span)
    frames = build_frames(league, live, seed=2026, dt=1.5)

    return {
        "window": {"from": lo, "to": hi, "centre_minute": centre},
        # Shirt numbers and names, in the same order as the position
        # frames. A numbered shirt is what makes a dot read as a player.
        "lineups": {
            side: [
                {"n": p.shirt, "name": p.name, "pos": p.position,
                 "last": p.name.split()[-1]}
                for p in sorted(
                    (q for q in league.squad(club) if q.shirt <= 11),
                    key=lambda q: q.shirt)
            ]
            for side, club in (("home", live.home_club_id), ("away", live.away_club_id))
        },
        # The ball, as segments: one source of truth for the position
        # model, this feed and the console. Finer than the 1.5s frame
        # sampling, which low-pass filtered every pass into a drift.
        "ball": pack_ball(build_ball_track(live)),
        "frames": pack(frames),
        "match": {
            "id": live.match_id,
            "home": {"id": home.club_id, "name": home.name, "short": home.short_name,
                     "goals": live.home_goals},
            "away": {"id": away.club_id, "name": away.name, "short": away.short_name,
                     "goals": live.away_goals},
            "events": len(live.events),
        },
        "moments": moments,
        "overlay": [asdict(_cue(i, s)) for i, s in enumerate(segments, 1)],
        "state": {
            league.club(team).short_name: values for team, values in state.items()
        },
        "follow": [
            {"player": league.player(pid).name,
             "club": league.club(league.player(pid).club_id).short_name,
             "position": league.player(pid).position,
             "score": score}
            for pid, score in follow
        ],
        "signal": [
            {"metric": METRIC_LABELS.get(m, m), "icc": s.icc,
             "personal": s.personal_claim_allowed}
            for m, s in sorted(signals.items(), key=lambda kv: -kv[1].icc)
        ],
        "stream": event_stream(live),
        "meta": {
            "season_matches": len(season),
            "season_events": sum(len(m.events) for m in season),
        },
    }


def write_feed(path: str, feed: dict[str, Any]) -> None:
    with open(path, "w") as fh:
        json.dump(feed, fh, indent=2)
