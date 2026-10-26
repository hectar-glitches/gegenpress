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
BALL_PULL = {"GK": 0.05, "DF": 0.28, "MF": 0.42, "FW": 0.33}
# How far the whole team slides up or back with the ball, by role.
SHIFT = {"GK": 0.25, "DF": 0.80, "MF": 0.70, "FW": 0.55}

# Movement physics, in metres and seconds.
SPRINT = 8.6     # with the ball
RUN = 7.4        # off the ball, top end
ACCEL = 3.1      # m/s^2 -- a footballer, not a car
ACCEL_RUN = 4.6  # m/s^2 -- a man who has seen the pass coming and goes
DAMP = 0.86      # per second; bleeds speed so players settle

# How far ahead a player sees his own next touch. The log knows the whole
# match; a footballer reads a pass a few seconds before it is played. At
# 3 s the named man could reach the ball 43% of the time; at 8 s, 91%.
LOOKAHEAD = 8.0
# The keeper's touches far from his goal are a simulator artefact -- the
# engine hands the ball to any of the eleven -- and a keeper sprinting to
# the opposition box to honour one is worse than leaving it unhonoured.
GK_RANGE = 30.0


# Ball flight speeds, m/s. A ball has two speeds -- it zips along a pass
# and dwells at someone's feet -- and that rhythm is what makes a match
# read as football rather than as drifting markers.
BALL_V = {"pass": 17.0, "shot": 24.0, "carry": 5.5}   # m/s; carry is a dribble, not a sprint


@dataclass(slots=True)
class BallSeg:
    """One event's worth of ball: a flight, then a settle."""

    t0: float
    t1: float
    ax: float
    ay: float
    bx: float
    by: float
    cx: float            # where the next event begins; the settle glides here
    cy: float
    ft: float            # flight duration
    loft: float          # peak height, metres
    carry: bool


def build_ball_track(match: Match) -> list[BallSeg]:
    """The ball's path, in absolute coordinates.

    THE single source of truth: the position model steers players at this,
    the feed ships it, and the console draws it. When this was computed
    twice -- once here for the players and once in the browser for the
    drawing -- the two paths diverged by up to 53 metres and the players
    visibly chased a ball that was not on screen.

    Pressure events are excluded: a presser is NEAR the ball, not the
    ball, and steering at him makes the track wobble.
    """
    def absolute(x: float, y: float, team_id: str, home_id: str):
        return (x, y) if team_id == home_id else (L - x, W - y)

    home_id = match.home_club_id
    evs = [e for e in match.events if e.type != "pressure"]
    segs: list[BallSeg] = []
    # The event log stamps a pass and its receipt a twentieth of a second
    # apart, so a flight squeezed into that gap crosses 26 metres at 500
    # m/s -- which the console, correctly, refuses to draw and cuts
    # instead. The ball vanished at one foot and appeared at another.
    #
    # The ball's time is physical and the log's is not, so the ball wins:
    # no event may start before the previous ball has landed and settled.
    # A flight that needs longer than the log allows pushes the next event
    # later, and the timeline catches up at the next real gap.
    t_floor = 0.0
    for i, e in enumerate(evs):
        t0 = max((e.period - 1) * 2700 + e.clock, t_floor)
        ax, ay = absolute(e.x, e.y, e.team_id, home_id)
        if e.end_x is not None:
            bx, by = absolute(e.end_x, e.end_y, e.team_id, home_id)
        else:
            bx, by = ax, ay
        nxt = evs[i + 1] if i + 1 < len(evs) else None
        if nxt:
            cx, cy = absolute(nxt.x, nxt.y, nxt.team_id, home_id)
        else:
            cx, cy = bx, by

        dist = math.hypot(bx - ax, by - ay)
        carry = e.type == "carry"
        if carry:
            v = BALL_V.get("carry", 5.0)
            ft = max(0.3, dist / v)
            need = ft / 0.9
        else:
            v = BALL_V.get(e.type)
            ft = max(0.25, min(2.2, dist / v)) if v else 0.0
            # The flight never fills the window: the settle keeps a share
            # of it, so the glide to the next event is a movement.
            need = ft / 0.74 if ft else 0.05
        stamped_next = (nxt.period - 1) * 2700 + nxt.clock if nxt else t0 + 4.0
        t1 = max(stamped_next, t0 + need, t0 + 0.05)
        if carry:
            ft = t1 - t0
        ft = max(0.01, ft)   # a dead ball still needs a non-zero flight to divide by
        t_floor = t1
        loft = min(7.0, dist * 0.18) if (e.type == "pass" and dist > 20) else (
            0.9 if e.type == "shot" else 0.0)
        # A long gap to the next event is a RESTART -- a goal, then a
        # kickoff fifty metres away -- not a journey the ball makes.
        if math.hypot(cx - bx, cy - by) > 12:
            cx, cy = bx, by
        segs.append(BallSeg(t0, t1, ax, ay, bx, by, cx, cy, ft, loft, carry))
    return segs


def ball_at(track: list[BallSeg], t: float) -> tuple[float, float, float, bool]:
    """-> (x, y, height, dwell). Mirrors ballAt() in the console exactly."""
    if not track:
        return L / 2, W / 2, 0.0, True
    lo, hi = 0, len(track) - 1
    while lo < hi:
        mid = (lo + hi + 1) // 2
        if track[mid].t0 <= t:
            lo = mid
        else:
            hi = mid - 1
    g = track[lo]
    if t <= g.t0:
        return g.ax, g.ay, 0.0, True
    u = min(1.0, (t - g.t0) / g.ft)
    if u < 1.0:
        # A ground pass decelerates into the receiver; only a ball in the
        # air travels at a roughly even pace.
        ue = u if (g.carry or g.loft > 0) else 1 - (1 - u) ** 1.7
        return (g.ax + (g.bx - g.ax) * ue, g.ay + (g.by - g.ay) * ue,
                g.loft * 4 * u * (1 - u), g.carry)
    rest = max(0.01, g.t1 - g.t0 - g.ft)
    v = max(0.0, min(1.0, (t - g.t0 - g.ft) / rest))
    e2 = v * v * (3 - 2 * v)
    return g.bx + (g.cx - g.bx) * e2, g.by + (g.cy - g.by) * e2, 0.0, True


def pack_ball(track: list[BallSeg]) -> list[list[float]]:
    """Wire form: one compact row per segment, rounded."""
    r2 = lambda v: round(v, 2)
    return [[r2(s.t0), r2(s.t1), r2(s.ax), r2(s.ay), r2(s.bx), r2(s.by),
             r2(s.cx), r2(s.cy), r2(s.ft), r2(s.loft), 1 if s.carry else 0]
            for s in track]


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
        # Start everyone on their anchor, at rest.
        self.pos = {
            self.home_id: [_anchor(i, True) for i in range(11)],
            self.away_id: [_anchor(i, False) for i in range(11)],
        }
        self.vel = {self.home_id: [(0.0, 0.0)] * 11,
                    self.away_id: [(0.0, 0.0)] * 11}
        # Each player drifts around his anchor on his own slow cycle.
        # Deterministic and smooth: per-step random jitter made targets
        # teleport metres every frame, which is what made the motion
        # look random rather than purposeful.
        self.drift = {
            tid: [(self.rng.uniform(0, math.tau), self.rng.uniform(17, 41),
                   self.rng.uniform(1.2, 3.4)) for _ in range(11)]
            for tid in (self.home_id, self.away_id)
        }
        # The one ball everything agrees on.
        self.track = build_ball_track(match)
        self._gk_ids = {p.player_id for p in self.home_xi + self.away_xi
                        if p.position == "GK"}

    def _is_gk(self, player_id: str) -> bool:
        return player_id in self._gk_ids

    def _near_own_goal(self, team_id: str, abs_x: float) -> bool:
        own = abs_x if team_id == self.home_id else L - abs_x
        return own <= GK_RANGE

    def _to_absolute(self, x: float, y: float, team_id: str) -> tuple[float, float]:
        """Event coords are from the possessing team's frame."""
        if team_id == self.home_id:
            return x, y
        return L - x, W - y

    def _target(self, player: Player, index: int, attacking_right: bool,
                ball: tuple[float, float], has_ball: bool,
                team_id: str = "", t: float = 0.0,
                rank: int = 99, in_possession: bool = False,
                lead: tuple[float, float] = (0.0, 0.0)) -> tuple[float, float]:
        if has_ball:
            return ball
        ax, ay = _anchor(index, attacking_right)
        bx, by = ball

        # Football is a CONTEST. A formation that merely slides along with
        # the ball is a lattice drifting under the camera -- which is what
        # this looked like: the ball flying across a field of men holding
        # station, barely one of them within five metres of it.
        #
        # So the players nearest the ball stop holding shape and go to it:
        # the closest defender presses the spot the ball is arriving at,
        # his partner covers behind, and the nearest attackers come short
        # to offer the pass. Everyone else keeps the block.
        if player.position != "GK" and rank <= 1 and in_possession:
            # His own side has it, and the man on it is whoever the log
            # names. A teammate who also runs onto the ball is a second
            # player on it, and the viewer cannot tell which one passed.
            # So he shows for it instead: a short angle off the ball,
            # toward his own position in the shape.
            dx, dy = ax - bx, ay - by
            d = math.hypot(dx, dy) or 1.0
            off = 7.0 if rank == 0 else 11.0
            return (min(L - 1, max(1.0, bx + dx / d * off)),
                    min(W - 1, max(1.0, by + dy / d * off)))
        if player.position != "GK" and rank <= 1:
            # Press the intercept point, not where the ball already was.
            lx, ly = bx + lead[0], by + lead[1]
            if rank == 0:
                # Tight, but goal-side of the ball rather than on it: two
                # men on one spot read as one man with two numbers.
                gs = -1.8 if attacking_right else 1.8
                return (min(L - 1, max(1.0, lx + gs)), min(W - 1, max(1.0, ly)))
            # Second man: support a stride off the ball, goal-side.
            side = -1.0 if attacking_right else 1.0
            return (min(L - 1, max(1.0, lx + side * 3.2)),
                    min(W - 1, max(1.0, ly + (3.0 if index % 2 else -3.0))))

        # The block slides along the pitch with the ball.
        shift = SHIFT.get(player.position, 0.6)
        centre = L / 2
        ax += (bx - centre) * shift * 0.55

        # Individual pull toward the ball, stronger when it is near, and
        # stronger again for the team that has it -- they are the ones
        # making angles for the next pass.
        pull = BALL_PULL.get(player.position, 0.25) * (1.25 if in_possession else 1.0)
        dist = math.hypot(bx - ax, by - ay)
        near = max(0.0, 1.0 - dist / 45.0)
        w = pull * (0.55 + 1.15 * near)
        tx = ax + (bx - ax) * w
        ty = ay + (by - ay) * w

        # A little individual noise so the shape is not a lattice.
        tx += self.rng.gauss(0, 2.6)
        ty += self.rng.gauss(0, 2.6)
        return (min(L - 1, max(1.0, tx)), min(W - 1, max(1.0, ty)))

    def run(self, lo: float = 0.0, hi: float | None = None,
            dt: float = 1.5, sub: float = 0.1) -> list[Frame]:
        """Step on a fixed clock, not at events.

        Sampling only at events gives one frame every few seconds, which
        no amount of interpolation makes look like football. A fixed
        timestep with the ball interpolated between events, and players
        moving at bounded speed toward their targets, does.
        """
        # Who is on the ball, and when, comes from the ball track -- the
        # physical timeline the console draws -- not from the log's stamps,
        # which run up to a few seconds early where a flight was pushed.
        # Pressure events have no segment: a presser is near the ball, not
        # on it.
        evs = [e for e in self.match.events if e.type != "pressure"]
        if not evs:
            return []
        segs = self.track
        hi = segs[-1].t1 if hi is None else hi

        # Every player's touches, in ball time: the spot and the second the
        # ball is at his feet. He goes there ahead of time, so the man the
        # log names is the man the viewer sees on it -- which a stat that
        # rises off the passer depends on entirely.
        touches: dict[str, list[tuple[float, float, float]]] = {}
        for s, e in zip(segs, evs):
            if self._is_gk(e.player_id) and not self._near_own_goal(e.team_id, s.ax):
                continue
            touches.setdefault(e.player_id, []).append((s.t0, s.ax, s.ay))
        nxt_i: dict[str, int] = {pid: 0 for pid in touches}

        # Warm the shape up before the window so it does not start as a
        # lattice snapping into place on the first visible frame.
        frames: list[Frame] = []
        t = max(0.0, lo - 25.0)
        k = 0
        next_sample = lo
        while t <= hi:
            while k + 1 < len(segs) and segs[k + 1].t0 <= t:
                k += 1
            seg, ev = segs[k], evs[k]
            team = ev.team_id
            # On the ball: the man whose event this is, until a pass or a
            # shot leaves his foot. A carry is his for its whole length.
            hold = seg.ft if seg.carry else seg.ft * 0.15
            carrier = ev.player_id if t < seg.t0 + hold else None
            bx, by, _bz, _dwell = ball_at(self.track, t)
            ball = (bx, by)
            for pid, lst in touches.items():
                j = nxt_i[pid]
                while j < len(lst) and lst[j][0] < t - 0.05:
                    j += 1
                nxt_i[pid] = j

            # Where the ball will be in half a second: chasers run at the
            # intercept, not at the spot it has already left.
            fx, fy, _fz, _fd = ball_at(self.track, t + 0.5)
            lead = (max(-9.0, min(9.0, fx - ball[0])),
                    max(-9.0, min(9.0, fy - ball[1])))

            for team_id, xi, right in (
                (self.home_id, self.home_xi, True),
                (self.away_id, self.away_xi, False),
            ):
                current = self.pos[team_id]
                vels = self.vel[team_id]
                # Who on this team is nearest the ball right now.
                order = sorted(
                    (i for i, p in enumerate(xi) if p.position != "GK"),
                    key=lambda i: math.hypot(current[i][0] - ball[0],
                                             current[i][1] - ball[1]))
                rank_of = {i: r for r, i in enumerate(order)}
                mine = (team_id == team)
                nxt: list[tuple[float, float]] = []
                nvel: list[tuple[float, float]] = []
                for i, player in enumerate(xi):
                    pid = player.player_id
                    has_ball = (pid == carrier)
                    rank = rank_of.get(i, 99)
                    cx, cy = current[i]
                    vx, vy = vels[i]
                    lst = touches.get(pid)
                    j = nxt_i.get(pid, 0)
                    going = None
                    if not has_ball and lst and j < len(lst) and lst[j][0] - t <= LOOKAHEAD:
                        going = lst[j]
                    if going:
                        # His next touch: be there when the ball is.
                        tx, ty = going[1], going[2]
                        left = max(0.15, going[0] - t)
                        gap0 = math.hypot(tx - cx, ty - cy)
                        need = gap0 / left
                    else:
                        tx, ty = self._target(player, i, right, ball, has_ball,
                                              team_id, t, rank, mine, lead)

                    # Steer the VELOCITY toward the target and integrate.
                    # Snapping position each step gave motion with no
                    # inertia, which no amount of interpolation smooths.
                    gx, gy = tx - cx, ty - cy
                    gap = math.hypot(gx, gy)
                    if going:
                        # Only as fast as arriving on time needs -- a man
                        # with six seconds jogs, a man with one sprints --
                        # and no easing off near the spot, or he arrives
                        # late to every ball.
                        top = min(SPRINT, max(2.5, need * 1.25))
                        want = min(top, gap * 3.0)
                        acc = ACCEL_RUN
                    else:
                        # A man going to the ball is sprinting; a man
                        # holding shape is not. One top speed for everyone
                        # is most of why the shape read as a lattice adrift.
                        top = SPRINT if (has_ball or rank == 0) else (
                            RUN if rank <= 2 else RUN * 0.82)
                        want = min(top, gap * 0.9)
                        acc = ACCEL
                    if gap > 1e-6:
                        wx, wy = gx / gap * want, gy / gap * want
                    else:
                        wx = wy = 0.0
                    ax, ay = wx - vx, wy - vy
                    amag = math.hypot(ax, ay)
                    lim = acc * sub
                    if amag > lim and amag > 0:
                        ax, ay = ax / amag * lim, ay / amag * lim
                    # Damping is per second, so scale it to the sub-step.
                    d2 = DAMP ** sub
                    vx, vy = (vx + ax) * d2, (vy + ay) * d2

                    nx = min(L - 0.5, max(0.5, cx + vx * sub))
                    ny = min(W - 0.5, max(0.5, cy + vy * sub))
                    nxt.append((nx, ny))
                    nvel.append((vx, vy))
                self.pos[team_id] = nxt
                self.vel[team_id] = nvel

            if t >= next_sample:
                next_sample += dt
                frames.append(Frame(
                    t=round(t, 1), ball=(round(ball[0], 1), round(ball[1], 1)),
                    home=[(round(x, 1), round(y, 1)) for x, y in self.pos[self.home_id]],
                    away=[(round(x, 1), round(y, 1)) for x, y in self.pos[self.away_id]],
                ))
            t += sub
        return frames


def build_frames(league: League, match: Match, seed: int = 2026,
                 lo: float = 0.0, hi: float | None = None,
                 dt: float = 1.5, sub: float = 0.1) -> list[Frame]:
    return PositionModel(league, match, seed).run(lo=lo, hi=hi, dt=dt, sub=sub)


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
