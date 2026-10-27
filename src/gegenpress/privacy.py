"""A player's own data, handed to him.

FIFPRO's Charter of Player Data Rights treats a player's performance data
as personal data and asks for access and portability -- the same two
rights GDPR and UK GDPR give him in Articles 15 and 20. This is that, for
the data Gegenpress holds:

    python -m gegenpress export --player "Noor Kowalski" --out kowalski.json

or the `export_player_data` MCP tool. One JSON document, in a published
shape (`gegenpress-player-data/1`), holding:

  * every event the system holds that names him, season and live, with
    the measurements taken from it;
  * his season norm for every metric, and whether that metric is allowed
    to carry a personal claim about him at all (the ICC gate), so he can
    see not only what was said but what the system refuses to say;
  * every claim made about him on air, verbatim, with who wrote it and
    whether the gate passed it.

What is deliberately NOT in it is listed in the document itself:
the simulator's hidden player attributes are engine parameters, not data a
broadcaster would hold, and other players' data is not his to receive.
"""

from __future__ import annotations

import datetime as dt
import json
import os
import pathlib
import statistics as st
from typing import Any

from .agents import TemplateModel, run_desk
from .baselines import METRICS
from .form import METRIC_LABELS, build_form_baselines
from .models import Match
from .season import League
from .signal import PERSONAL_CLAIM_ICC, measure_signal
from .store import LocalStore

SCHEMA = "gegenpress-player-data/1"
OPTOUT = pathlib.Path(os.environ.get("GEGENPRESS_OPTOUT", "data/optout.json"))


def objections(path: pathlib.Path | str = OPTOUT) -> set[str]:
    """Players who have objected to personal claims (GDPR Art. 21).

    A JSON list of player ids, kept by the deployer's data protection
    contact. Missing file: nobody has objected. A file that cannot be read
    is an error, not an empty list -- failing open here would put an
    objecting player back on air.
    """
    p = pathlib.Path(path)
    if not p.exists():
        return set()
    ids = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids):
        raise ValueError(f"{p} must be a JSON list of player ids")
    return set(ids)

NOT_INCLUDED = [
    "Simulator attributes (pace, passing, pressing...). They are the engine's "
    "inputs, not data a deployer collects or holds about a real player.",
    "Other players' data, including the league distributions his figures are "
    "compared against. Only the summary statistics used in a claim about him "
    "appear, inside that claim.",
    "Anything about viewers. The console holds no viewer data to export.",
]

RIGHTS = (
    "This is the data Gegenpress holds that identifies you, in a structured, "
    "machine-readable format you may take elsewhere (GDPR / UK GDPR Art. 15 "
    "access and Art. 20 portability; FIFPRO Charter of Player Data Rights). "
    "Corrections and objections go to the deployer's data protection contact. "
    "All data in this build is synthetic."
)


def _measurements(e) -> dict[str, float]:
    keys = {key for etype, key, _ in METRICS.values() if etype == e.type}
    return {k: round(float(v), 3) for k, v in e.detail.items()
            if k in keys and v is not None}


def _event_row(e, m: Match, live: bool) -> dict[str, Any]:
    return {
        "match_id": m.match_id, "matchday": m.matchday, "live": live,
        "event_id": e.event_id, "minute": e.minute, "type": e.type,
        "x": e.x, "y": e.y, "end_x": e.end_x, "end_y": e.end_y,
        "outcome": e.outcome, "measurements": _measurements(e),
    }


def export_player(league: League, season: list[Match], live: Match,
                  player_id: str, claims: list[dict[str, Any]] | None = None,
                  now: dt.datetime | None = None) -> dict[str, Any]:
    """Everything held about one player, as one document."""
    p = league.player(player_id)
    club = league.club(p.club_id)

    events = [_event_row(e, m, False) for m in season for e in m.events if e.player_id == player_id]
    events += [_event_row(e, live, True) for e in live.events if e.player_id == player_id]

    form = build_form_baselines(season)
    signals = measure_signal(season)
    norms = []
    for metric in METRICS:
        means = form.player_match_means.get((player_id, metric), [])
        sig = signals.get(metric)
        norms.append({
            "metric": metric, "label": METRIC_LABELS.get(metric, metric),
            "matches": len(means),
            "season_mean": round(st.fmean(means), 3) if means else None,
            "season_sd": round(st.stdev(means), 3) if len(means) > 1 else None,
            "icc": round(sig.icc, 4) if sig else None,
            "personal_claims_allowed": bool(sig and sig.personal_claim_allowed),
            "why": (f"ICC {sig.icc:.3f} >= {PERSONAL_CLAIM_ICC}: this metric differs between "
                    "players, so your own history is a fair comparison."
                    if sig and sig.personal_claim_allowed else
                    "Too little difference between players: this metric describes the "
                    "match more than the player, so no claim compares you to your own "
                    "norm on it." if sig else "Not enough data to measure."),
        })

    if claims is None:
        store = LocalStore()
        store.load_season(league, season)
        claims = [s.as_dict() for s in run_desk(store, league, live, model=TemplateModel(), limit=8)]
    mine = [{
        "match_id": live.match_id, "minute": c.get("minute"), "metric": c.get("metric"),
        "text": c.get("text"), "writer": c.get("model"),
        "gate_passed": c.get("grounded"), "fell_back": c.get("fell_back"),
        "review": c.get("review"),
    } for c in claims if c.get("player") == p.name]

    return {
        "schema": SCHEMA,
        "generated_at": (now or dt.datetime.now(dt.timezone.utc)).isoformat(timespec="seconds"),
        "subject": {"player_id": p.player_id, "name": p.name, "club": club.name,
                    "shirt": p.shirt, "position": p.position},
        "rights": RIGHTS,
        "events": {"count": len(events), "rows": events},
        "season_norms": norms,
        "claims": mine,
        "not_included": NOT_INCLUDED,
        "synthetic": True,
    }
