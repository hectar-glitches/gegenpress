"""The ball's path obeys physics, whatever the event log says.

The log stamps a pass and its receipt a twentieth of a second apart. A
track built naively from those stamps had 178 segments in which the ball
crossed up to 26 metres at 500 m/s. The console, correctly, treats a jump
that size as a restart and cuts -- so the ball vanished at one player's
feet and appeared at another's, in the one sequence the demo shows.

These pin the two properties that stop it: no segment is faster than a
hard shot, and the timeline that honours the flights stays within a few
seconds of the log, because a real gap lets it catch up.
"""

from __future__ import annotations

import math

import pytest

from gegenpress.positions import BALL_V, build_ball_track
from gegenpress.season import build_league
from gegenpress.simulate import simulate_live

# A hard shot is about 30 m/s; nothing on a football pitch is faster.
MAX_BALL_SPEED = 32.0


@pytest.fixture(scope="module")
def track():
    league = build_league(seed=2026)
    live = simulate_live(league, league.fixtures[0], seed=2026)
    return build_ball_track(live), live


def test_no_segment_is_faster_than_a_shot(track):
    segs, _ = track
    too_fast = []
    for s in segs:
        dist = math.hypot(s.bx - s.ax, s.by - s.ay)
        if dist > 5 and s.ft > 0 and dist / s.ft > MAX_BALL_SPEED:
            too_fast.append((round(s.t0, 1), round(dist, 1), round(dist / s.ft)))
    assert not too_fast, f"{len(too_fast)} segments exceed {MAX_BALL_SPEED} m/s: {too_fast[:5]}"


def test_passes_fly_at_pass_speed(track):
    """Not just 'not absurd': a 26 metre pass takes 26/17 seconds."""
    segs, _ = track
    checked = 0
    for s in segs:
        dist = math.hypot(s.bx - s.ax, s.by - s.ay)
        if s.carry or s.loft < 1 or dist < 20:   # lofted passes only; a shot lofts 0.9 and flies at 24
            continue
        assert abs(dist / s.ft - BALL_V["pass"]) < 0.5, (s.t0, dist, s.ft)
        checked += 1
    assert checked > 20, "the match had fewer long passes than expected"


def test_segments_are_contiguous_and_ordered(track):
    """The console looks up the ball by time; a gap or an overlap is a
    frame with no ball, or two."""
    segs, _ = track
    for a, b in zip(segs, segs[1:]):
        assert a.t1 <= b.t0 + 1e-6, (a.t0, a.t1, b.t0)
        assert abs(a.t1 - b.t0) < 1e-6, f"gap between {a.t1} and {b.t0}"


def test_the_timeline_stays_close_to_the_log(track):
    """Honouring flights pushes events later. Real gaps pull them back.
    Net drift over a match must stay small, or the ball lags the clock."""
    segs, live = track
    evs = [e for e in live.events if e.type != "pressure"]
    worst = 0.0
    for s, e in zip(segs, evs):
        stamped = (e.period - 1) * 2700 + e.clock
        worst = max(worst, s.t0 - stamped)
    assert worst < 12.0, f"ball track runs {worst:.1f}s ahead of the event log"


def test_every_segment_has_a_flight_to_divide_by(track):
    segs, _ = track
    assert all(s.ft > 0 for s in segs)
