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

from .agents import TOLERANCE, Gate, Segment, run_desk
from .form import CHECKPOINTS, METRIC_LABELS, NOTABLE_Z
from .i18n import (DIRECTION, LANGUAGES, LANGUAGE_CODES, form_claim,
                   metric_label, moment_text)
from .i18n import ui as ui_strings
from .models import Match
from .season import League
from .positions import (build_ball_track, build_frames, pack,
                        pack_ball, pick_window)
from .signal import measure_signal
from .store import Store

# How long a graphic stays on screen, by kind.
OVERLAY_SECONDS = {"form": 6.0, "moment": 4.5}

# One gate instance for the translation check. Stateless, so sharing it
# costs nothing and makes the intent clear: translations are held to the
# same control as the English the model wrote.
_GATE = Gate()


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


def _unit(metric_key: str) -> str:
    return "s" if metric_key.endswith("_s") else ""


def _translate_moment(seg, gate: Gate) -> dict[str, str]:
    """The same grounded claim in every language, each one gated.

    The English string is whatever Desk actually produced -- a model, when
    one is configured. The rest are rendered from the same brief. Every
    one of them goes through the Gate before it ships, so a translation
    cannot smuggle in a number the brief does not contain. That check is
    free precisely because the Gate reads digits rather than prose.
    """
    b = seg.brief
    key = seg.form_metric or ""
    norm = f"{b.season_mean:g}" if b.season_mean is not None else None
    out = {"en": seg.verdict.text}
    for code in LANGUAGE_CODES:
        if code == "en":
            continue
        out[code] = moment_text(
            code, minute=b.minute, player=b.player_name,
            metric_key=key, value=f"{b.value:g}", norm=norm,
        )
    for code, text in out.items():
        bad = gate.unsupported(text, b)
        if bad:  # pragma: no cover - a template cannot invent a number
            raise ValueError(f"{code} translation failed the gate: {bad}")
    return out


def _follow_entry(league, live, pid, score, form_by_player, as_of: int = 90):
    p = league.player(pid)
    best = form_by_player.get(pid)
    row = {"player_id": pid, "player": p.name,
           "club": league.club(p.club_id).short_name,
           "position": p.position, "shirt": p.shirt, "score": score}
    if best is not None:
        row.update({
            "metric": METRIC_LABELS.get(best.metric, best.metric),
            "metric_key": best.metric,
            "value": round(best.match_mean, 2),
            "season_mean": round(best.season_mean, 2),
            "z": round(best.z, 2),
            "appearances": best.appearances,
            "league_pct": round(best.league_percentile * 100, 1),
            "league_mean": round(best.league_mean, 2),
            "above": best.z > 0,
            "diverges": best.diverges,
            "claim": best.claim(),
            "metric_i18n": {c: metric_label(best.metric, c) for c in LANGUAGE_CODES},
            "claim_i18n": {
                c: form_claim(
                    c, player=p.name, metric_key=best.metric,
                    value=f"{best.match_mean:.1f}", norm=f"{best.season_mean:.1f}",
                    z=f"{best.z:+.1f}", appearances=best.appearances,
                    unit=_unit(best.metric),
                    direction=("above" if best.z >= NOTABLE_Z
                               else "below" if best.z <= -NOTABLE_Z else "level"),
                )
                for c in LANGUAGE_CODES
            },
            "events": contributing_events(live, pid, best.metric, as_of),
        })
    return row


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
    # Who to follow is a question with a different answer at 30' than at
    # 90'. One list computed at full time and shown from kickoff is the
    # final table on the opening frame -- the scoreboard fault, again.
    # So it is computed at every Form Line checkpoint, and the console
    # switches lists as the clock passes each one.
    def follow_as_of(minute: int) -> list[dict[str, Any]]:
        ranked = store.follow_target(live, as_of_minute=minute)[:6]
        best: dict[str, Any] = {}
        for line in store.form_lines(live, notable_only=False, as_of_minute=minute):
            cur = best.get(line.player_id)
            if cur is None or abs(line.z) > abs(cur.z):
                best[line.player_id] = line
        return [_follow_entry(league, live, pid, score, best, minute)
                for pid, score in ranked]

    follow_at = {str(m): follow_as_of(m) for m in CHECKPOINTS}
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
            "text_i18n": _translate_moment(seg, _GATE),
            # Every number this claim is allowed to contain, straight from
            # the brief the Gate checks against. Shipped so the console can
            # run the same check in front of a viewer without a server and
            # without a second definition of the rule.
            "allowed": [round(v, 4) for v in b.allowed_numbers()],
            # Why this metric may carry a personal claim at all. The
            # measured value is table stakes -- nobody disputes that
            # 13.77 is 13.77. Whether "below his level" is a sentence
            # anyone is entitled to say is the part that needs showing.
            "icc": (round(signals[seg.form_metric].icc, 4)
                    if seg.form_metric in signals else None),
            "personal": (signals[seg.form_metric].personal_claim_allowed
                         if seg.form_metric in signals else None),
            "metric_i18n": {
                c: metric_label(seg.form_metric or "", c) for c in LANGUAGE_CODES
            } if seg.form_metric else None,
            "value": b.value,
            "expected": b.expected,
            # Full precision rather than one decimal: the console rounds
            # for display anyway, and `allowed` below is derived from this
            # number, so truncating here would make the published answer
            # key disagree with the gate that produced it.
            "league_pct": round(b.beats_pct, 4),
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
        # Everything the console needs to re-render in another language
        # without another request. The claims themselves travel with each
        # moment; this is the chrome around them.
        # The Gate's one tuning constant, published rather than duplicated.
        # The browser compares with this; so does Python. A test pins them
        # together, because two copies of a threshold is one too many.
        "gate": {"tolerance": TOLERANCE},
        "i18n": {
            "default": "en",
            "languages": [
                {"code": c, "name": n, "dir": d} for c, n, d in LANGUAGES
            ],
            "dir": dict(DIRECTION),
            "ui": {c: ui_strings(c) for c in LANGUAGE_CODES},
        },
        "overlay": [asdict(_cue(i, s)) for i, s in enumerate(segments, 1)],
        "state": {
            league.club(team).short_name: values for team, values in state.items()
        },
        # Follow targets, each carrying the form line that earned the
        # ranking and the touches behind it. Personalisation here means
        # watching a player measured against HIMSELF, so the payload has
        # to be the Form Line -- a name and a score would make this the
        # same dropdown every other entry has.
        "follow": follow_at[str(CHECKPOINTS[-1])],
        "follow_at": follow_at,
        "signal": [
            {"metric": METRIC_LABELS.get(m, m),
             "metric_i18n": {c: metric_label(m, c) for c in LANGUAGE_CODES},
             "icc": s.icc,
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
