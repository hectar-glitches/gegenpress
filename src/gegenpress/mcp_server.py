"""The Form Line as a service: gegenpress over MCP.

Every tool here answers from the same Store interface the console uses,
and the pitch is the same one the project makes everywhere else -- not
"here is the data" but "here is whether the sentence is sayable". The
distinctive tool is `verify_claim`: hand it any sentence about a player's
night and it runs the deterministic Gate against the measured brief,
telling the calling model which of its numbers are unsupportable, and
whether a personal claim is even permitted for that metric at all.

Transport is stdio, so it plugs into anything that speaks MCP -- Claude
Desktop, VS Code, Copilot Studio, Foundry agents:

    {"command": "python", "args": ["-m", "gegenpress", "mcp"],
     "env": {"PYTHONPATH": "src"}}

The world is simulated once at startup from GEGENPRESS_SEED (default
2026): the same persistent league, season and live match the rest of the
project uses, so numbers given here agree with the console to the digit.

The MCP SDK is only needed to SERVE. The tool logic below is plain
functions, tested without it.
"""

from __future__ import annotations

import os
from typing import Any

from .agents import Gate, Why
from .baselines import METRICS
from .form import METRIC_LABELS, form_lines as compute_form_lines
from .season import build_league
from .signal import PERSONAL_CLAIM_ICC, measure_signal
from .simulate import simulate_live, simulate_season
from .store import LocalStore


class World:
    """Everything the tools answer from, built once."""

    def __init__(self, seed: int | None = None) -> None:
        self.seed = seed or int(os.environ.get("GEGENPRESS_SEED", "2026"))
        self.league = build_league(seed=self.seed)
        self.season = simulate_season(self.league, seed=self.seed)
        self.live = simulate_live(self.league, self.league.fixtures[0], seed=self.seed)
        self.store = LocalStore()
        self.store.load_season(self.league, self.season)
        self.signals = measure_signal(self.season)
        self.why = Why(self.league)
        self.gate = Gate()
        self.names = {p.player_id: p.name for p in self.league.players}

    # -- resolution ------------------------------------------------------

    def player_id(self, name: str) -> str | None:
        q = name.strip().lower()
        exact = [pid for pid, n in self.names.items() if n.lower() == q]
        if exact:
            return exact[0]
        part = [pid for pid, n in self.names.items() if q in n.lower()]
        return part[0] if len(part) == 1 else None

    def metric_key(self, name: str) -> str | None:
        q = name.strip().lower().replace("_", " ")
        for key in METRICS:
            if q == key.lower().replace("_", " "):
                return key
        for key, label in METRIC_LABELS.items():
            if q == label.lower():
                return key
        part = [k for k in METRICS
                if q in k.lower().replace("_", " ")
                or q in METRIC_LABELS.get(k, "").lower()]
        return part[0] if len(part) == 1 else None

    def form_line_for(self, player_id: str, metric: str, as_of_minute: int):
        lines = compute_form_lines(self.store._form, self.live, self.signals,
                                   self.names, as_of_minute=as_of_minute)
        for line in lines:
            if line.player_id == player_id and line.metric == metric:
                return line
        return None


_WORLD: World | None = None


def world() -> World:
    global _WORLD
    if _WORLD is None:
        _WORLD = World()
    return _WORLD


# -- tool logic (plain functions; the SDK only wraps these) ---------------

def match_info() -> dict[str, Any]:
    w = world()
    home = w.league.club(w.live.home_club_id)
    away = w.league.club(w.live.away_club_id)
    return {
        "match_id": w.live.match_id,
        "home": {"name": home.name, "short": home.short_name, "goals": w.live.home_goals},
        "away": {"name": away.name, "short": away.short_name, "goals": w.live.away_goals},
        "events": len(w.live.events),
        "season": {"matches": len(w.season),
                   "events": sum(len(m.events) for m in w.season)},
        "seed": w.seed,
        "note": "All clubs, players and matches are synthetic.",
    }


def list_players(query: str = "") -> list[dict[str, Any]]:
    w = world()
    q = query.strip().lower()
    out = []
    for p in w.league.players:
        if q and q not in p.name.lower():
            continue
        out.append({"name": p.name, "club": w.league.club(p.club_id).short_name,
                    "position": p.position, "shirt": p.shirt})
        if len(out) >= 30:
            break
    return out


def metric_signal_table() -> dict[str, Any]:
    w = world()
    rows = [{
        "metric": METRIC_LABELS.get(m, m),
        "key": m,
        "icc": s.icc,
        "reliability_of_50_match_mean": round(s.mean_reliability, 3),
        "koo_li_band": s.band,
        "personal_claim_allowed": s.personal_claim_allowed,
    } for m, s in sorted(w.signals.items(), key=lambda kv: -kv[1].icc)]
    return {
        "threshold_icc": PERSONAL_CLAIM_ICC,
        "rows": rows,
        "meaning": (
            "ICC is between-player variance over total variance. Near zero, a "
            "player's distribution is the league's wearing his name, so 'his "
            "season norm' is noise and the system refuses the personal claim. "
            "The threshold derives from Koo & Li (2016): 0.0566 puts a "
            "50-observation mean on their 'good reliability' boundary; 0.08 "
            "is stricter because touches cluster within matches."
        ),
    }


def form_line(player: str, metric: str, as_of_minute: int = 90) -> dict[str, Any]:
    w = world()
    pid = w.player_id(player)
    if pid is None:
        return {"error": f"no unique player matches {player!r}; try list_players"}
    key = w.metric_key(metric)
    if key is None:
        keys = ", ".join(sorted(METRIC_LABELS.values()))
        return {"error": f"no unique metric matches {metric!r}; one of: {keys}"}

    sig = w.signals.get(key)
    if sig is None or not sig.personal_claim_allowed:
        return {
            "refused": True,
            "player": w.names[pid], "metric": METRIC_LABELS.get(key, key),
            "icc": sig.icc if sig else None,
            "reason": (
                "This metric has no usable between-player signal, so a "
                "personal reference class does not exist: 'his norm' would be "
                "the league's norm wearing his name. League-level claims only."
            ),
        }

    line = w.form_line_for(pid, key, as_of_minute)
    if line is None:
        return {"error": f"{w.names[pid]} has no {METRIC_LABELS.get(key, key)} "
                         f"events by minute {as_of_minute} of this match"}
    return {
        "player": line.player_name,
        "metric": METRIC_LABELS.get(key, key),
        "as_of_minute": line.as_of_minute,
        "tonight_mean": round(line.match_mean, 2),
        "season_mean": round(line.season_mean, 2),
        "z": round(line.z, 2),
        "appearances": line.appearances,
        "events_tonight": line.events_this_match,
        "league_percentile": round(line.league_percentile, 3),
        "league_mean": round(line.league_mean, 2),
        "effect_vs_league_sd": round(line.effect_vs_league_sd, 2),
        "above_own_level": line.above_own_level,
        "notable": line.notable,
        "diverges_from_league_view": line.diverges,
        "sayable_claim": line.claim(),
    }


def top_moments(min_beats: float = 0.98, limit: int = 8) -> list[dict[str, Any]]:
    w = world()
    return [{
        "minute": m.minute, "player": m.player_name,
        "metric": METRIC_LABELS.get(m.metric, m.metric), "value": m.value,
        "league_expected": round(m.expected, 2), "beats_share_of_league": round(m.beats, 4),
        "personal_claim_allowed": m.personal_claim_allowed,
        "is_personal_best": m.is_personal_best,
    } for m in w.store.top_moments(w.live, min_beats=min_beats, limit=limit)]


def match_state(as_of_minute: int = 90, window_minutes: int = 15) -> dict[str, Any]:
    w = world()
    state = w.store.match_state(w.live, as_of_minute=as_of_minute,
                                window_minutes=window_minutes)
    return {w.league.club(team).short_name: vals for team, vals in state.items()}


def follow_targets(as_of_minute: int = 90, limit: int = 6) -> list[dict[str, Any]]:
    w = world()
    ranked = w.store.follow_target(w.live, as_of_minute=as_of_minute)[:limit]
    return [{
        "player": w.names[pid],
        "club": w.league.club(w.league.player(pid).club_id).short_name,
        "lift_over_own_norm": round(score, 3),
    } for pid, score in ranked]


def verify_claim(text: str, player: str, metric: str,
                 as_of_minute: int = 90) -> dict[str, Any]:
    w = world()
    pid = w.player_id(player)
    if pid is None:
        return {"error": f"no unique player matches {player!r}; try list_players"}
    key = w.metric_key(metric)
    if key is None:
        return {"error": f"no unique metric matches {metric!r}"}

    sig = w.signals.get(key)
    if sig is None or not sig.personal_claim_allowed:
        return {
            "verdict": "refused",
            "reason": (
                f"{METRIC_LABELS.get(key, key)} has no between-player signal "
                f"(ICC {sig.icc if sig else 'n/a'}), so no sentence comparing "
                "this player to his own norm is sayable, whatever its numbers."
            ),
        }
    line = w.form_line_for(pid, key, as_of_minute)
    if line is None:
        return {"error": f"{w.names[pid]} has no {METRIC_LABELS.get(key, key)} "
                         f"events by minute {as_of_minute}; nothing to verify against"}
    brief = w.why.brief_from_form(line, w.live)
    bad = w.gate.check(text, brief)
    return {
        "verdict": "passed" if not bad else "rejected",
        "unsupportable_numbers": bad,
        "allowed_numbers": sorted(set(brief.allowed_numbers())),
        "grounding": {
            "player": line.player_name, "metric": METRIC_LABELS.get(key, key),
            "tonight_mean": round(line.match_mean, 2),
            "season_mean": round(line.season_mean, 2),
            "z": round(line.z, 2), "as_of_minute": line.as_of_minute,
        },
        "honesty": (
            "The Gate reads digits and checks presence against the brief. It "
            "removes invented numbers; it does not make the sentence true. A "
            "number spelled out in words, or a real number attached to the "
            "wrong thing, passes -- both are documented, measured misses."
        ),
    }


# -- serving ---------------------------------------------------------------

def serve() -> int:
    try:                                             # mcp >= 2
        from mcp.server.mcpserver import MCPServer as Server
    except ImportError:                              # mcp 1.x
        from mcp.server.fastmcp import FastMCP as Server

    mcp = Server(
        "gegenpress",
        instructions=(
            "Form-aware football match intelligence over a synthetic season. "
            "The one thing this server does that a stats feed does not: it "
            "knows which metrics can support a personal claim at all, and it "
            "will verify any sentence you write against the measured brief. "
            "Call metric_signal first to learn which claims are sayable."
        ),
    )
    mcp.tool()(match_info)
    mcp.tool()(list_players)
    mcp.tool()(metric_signal_table)
    mcp.tool()(form_line)
    mcp.tool()(top_moments)
    mcp.tool()(match_state)
    mcp.tool()(follow_targets)
    mcp.tool()(verify_claim)
    mcp.run()
    return 0
