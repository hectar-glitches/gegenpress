"""A positional model: where all 22 players are, over the match.

This is a MODEL, not tracking data, and the distinction matters. The
event engine decides what happens; this decides where everyone stands
while it happens. Each player holds a formation anchor, the whole team
shifts with the ball, and individuals are pulled toward it by a weight
that depends on their role and distance.

Everything is computed from the seeded RNG, so positions are
deterministic and reproducible like the rest of the season.

Coordinates here are ABSOLUTE: the home team always attacks +x. Event
coordinates are relative to whoever has the ball, so they are converted
on the way in.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass

from .models import PITCH_LENGTH as L
from .models import PITCH_WIDTH as W
from .models import Match, Player
from .season import League

# Formation anchors as fractions of the pitch, for a team attacking +x.
# 4-3-3: keeper, back four, midfield three, front three.
FORMATION_XY: list[tuple[float, float]] = [
    (0.05, 0.50),                                      # GK
    (0.22, 0.14), (0.20, 0.38), (0.20, 0.62), (0.22, 0.86),   # DF
    (0.40, 0.26), (0.38, 0.50), (0.40, 0.74),                 # MF
    (0.62, 0.18), (0.66, 0.50), (0.62, 0.82),                 # FW
]

# How strongly each role chases the ball, and how far it ranges.
BALL_PULL = {"GK": 0.04, "DF": 0.22, "MF": 0.34, "FW": 0.26}
# How far the whole team slides up or back with the ball, by role.
SHIFT = {"GK": 0.25, "DF": 0.80, "MF": 0.70, "FW": 0.55}


@dataclass(slots=True)
class Frame:
    """One sampled instant: the ball and all 22 players, absolute frame."""

    t: float
    ball: tuple[float, float]
    home: list[tuple[float, float]]
    away: list[tuple[float, float]]


def _anchor(index: int, attacking_right: bool) -> tuple[float, float]:
    fx, fy = FORMATION_XY[index]
    return ((fx if attacking_right else 1.0 - fx) * L, fy * W)


class PositionModel:
    """Steps 22 players through a match, sampling at each event."""

    def __init__(self, league: League, match: Match, seed: int = 2026) -> None:
        self.rng = random.Random(f"pos:{seed}:{match.match_id}")
        self.match = match
        self.home_id = match.home_club_id
        self.away_id = match.away_club_id
        self.home_xi = [p for p in league.squad(self.home_id) if p.shirt <= 11]
        self.away_xi = [p for p in league.squad(self.away_id) if p.shirt <= 11]
        # Start everyone on their anchor.
        self.pos = {
            self.home_id: [_anchor(i, True) for i in range(11)],
            self.away_id: [_anchor(i, False) for i in range(11)],
        }

    def _to_absolute(self, x: float, y: float, team_id: str) -> tuple[float, float]:
        """Event coords are from the possessing team's frame."""
        if team_id == self.home_id:
            return x, y
        return L - x, W - y

    def _target(self, player: Player, index: int, attacking_right: bool,
                ball: tuple[float, float], has_ball: bool) -> tuple[float, float]:
        if has_ball:
            return ball
        ax, ay = _anchor(index, attacking_right)
        bx, by = ball

        # The block slides along the pitch with the ball.
        shift = SHIFT.get(player.position, 0.6)
        centre = L / 2
        ax += (bx - centre) * shift * 0.55

        # Individual pull toward the ball, stronger when it is near.
        pull = BALL_PULL.get(player.position, 0.25)
        dist = math.hypot(bx - ax, by - ay)
        near = max(0.0, 1.0 - dist / 45.0)
        w = pull * (0.35 + near)
        tx = ax + (bx - ax) * w
        ty = ay + (by - ay) * w

        # A little individual noise so the shape is not a lattice.
        tx += self.rng.gauss(0, 1.3)
        ty += self.rng.gauss(0, 1.3)
        return (min(L - 1, max(1.0, tx)), min(W - 1, max(1.0, ty)))

    def run(self, lo: float = 0.0, hi: float | None = None,
            dt: float = 0.4) -> list[Frame]:
        """Step on a fixed clock, not at events.

        Sampling only at events gives one frame every few seconds, which
        no amount of interpolation makes look like football. A fixed
        timestep with the ball interpolated between events, and players
        moving at bounded speed toward their targets, does.
        """
        marks = [
            ((e.period - 1) * 2700 + e.clock,
             self._to_absolute(e.x, e.y, e.team_id),
             e.player_id, e.team_id)
            for e in self.match.events
        ]
        if not marks:
            return []
        hi = marks[-1][0] if hi is None else hi

        # Warm the shape up before the window so it does not start as a
        # lattice snapping into place on the first visible frame.
        frames: list[Frame] = []
        t = max(0.0, lo - 20.0)
        k = 0
        while t <= hi:
            while k + 1 < len(marks) and marks[k + 1][0] <= t:
                k += 1
            t0, b0, carrier, team = marks[k]
            if k + 1 < len(marks):
                t1, b1, _, _ = marks[k + 1]
                f = 0.0 if t1 <= t0 else max(0.0, min(1.0, (t - t0) / (t1 - t0)))
                # Ease the ball between events rather than sliding linearly.
                e = f * f * (3 - 2 * f)
                ball = (b0[0] + (b1[0] - b0[0]) * e, b0[1] + (b1[1] - b0[1]) * e)
            else:
                ball = b0

            for team_id, xi, right in (
                (self.home_id, self.home_xi, True),
                (self.away_id, self.away_xi, False),
            ):
                current = self.pos[team_id]
                updated: list[tuple[float, float]] = []
                for i, player in enumerate(xi):
                    has_ball = (player.player_id == carrier)
                    tx, ty = self._target(player, i, right, ball, has_ball)
                    cx, cy = current[i]
                    reach = (8.5 if has_ball else 6.5) * dt
                    dx, dy = tx - cx, ty - cy
                    d = math.hypot(dx, dy)
                    if d > reach and d > 0:
                        dx, dy = dx / d * reach, dy / d * reach
                    updated.append((cx + dx, cy + dy))
                self.pos[team_id] = updated

            if t >= lo:
                frames.append(Frame(
                    t=round(t, 1), ball=(round(ball[0], 1), round(ball[1], 1)),
                    home=[(round(x, 1), round(y, 1)) for x, y in self.pos[self.home_id]],
                    away=[(round(x, 1), round(y, 1)) for x, y in self.pos[self.away_id]],
                ))
            t += dt
        return frames


def build_frames(league: League, match: Match, seed: int = 2026,
                 lo: float = 0.0, hi: float | None = None,
                 dt: float = 0.4) -> list[Frame]:
    return PositionModel(league, match, seed).run(lo=lo, hi=hi, dt=dt)


def pick_window(match: Match, centre_minute: int, span: int = 240
                ) -> tuple[float, float]:
    """A showcase window in match seconds, centred on a minute.

    Ninety minutes compressed into twenty seconds cannot look like
    football -- the motion is a blur at any plausible frame rate. A short
    passage near real time can. The window is SELECTED from the real
    match, never fabricated: every event in it is engine output.
    """
    centre = centre_minute * 60.0
    half = span / 2.0
    lo = max(0.0, centre - half)
    return lo, lo + span


def pack(frames: list[Frame]) -> dict:
    """Compact wire form: flat integer arrays, one row per frame."""
    # Flat integer arrays on a fixed step. Nested per-frame arrays cost
    # more in brackets than in data, and at this step one metre of
    # rounding is invisible. The client reads 22 values at frame*22 and
    # interpolates between frames.
    flat_h: list[int] = []
    flat_a: list[int] = []
    flat_b: list[int] = []
    for f in frames:
        flat_b += [round(f.ball[0]), round(f.ball[1])]
        for x, y in f.home:
            flat_h += [round(x), round(y)]
        for x, y in f.away:
            flat_a += [round(x), round(y)]
    return {
        "dt": round(frames[1].t - frames[0].t, 2) if len(frames) > 1 else 1.0,
        "t0": frames[0].t if frames else 0.0,
        "n": len(frames),
        "b": flat_b, "h": flat_h, "a": flat_a,
    }
