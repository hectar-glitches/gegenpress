"""The man the data names is the man the viewer sees on the ball.

The console raises a figure off a player the moment he passes, ticks his
pass count, names a goal's scorer. All of that is only as true as the
picture's agreement with the event log about WHO had the ball. Before this
was measured, the player the log named for a pass was the nearest man to
the ball in the picture 13% of the time, a median 20 metres away: the
engine hands the ball to any of the eleven, and the position model sent
him toward it with less than a second's notice.

Now each player sees his own next touch a few seconds out and is there
when the ball is. These pin that, read off the shipped feed exactly as the
console interpolates it -- and pin that it was not bought by men running
at impossible speeds or the shape collapsing onto the ball.
"""

from __future__ import annotations

import json
import math
import pathlib
import statistics

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEED = ROOT / "docs" / "feed.json"
L, W = 105.0, 68.0


@pytest.fixture(scope="module")
def feed() -> dict:
    if not FEED.exists():  # pragma: no cover
        pytest.skip("docs/feed.json not built")
    return json.loads(FEED.read_text())


def _cr(p0, p1, p2, p3, u):
    """Catmull-Rom, as `cr()` in the console."""
    return 0.5 * ((2 * p1) + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u
                  + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3)


def _at(F, side, q, t):
    """The console's `at()`: where figure q of a side is drawn at t."""
    arr = F["h" if side == "home" else "a"]
    k = (t - F["t0"]) / F["dt"]
    i = max(0, min(F["n"] - 1, int(math.floor(k))))
    u = max(0.0, min(1.0, k - i))
    a, b, c = max(0, i - 1), min(F["n"] - 1, i + 1), min(F["n"] - 1, i + 2)
    return tuple(_cr(arr[a * 22 + q * 2 + j], arr[i * 22 + q * 2 + j],
                     arr[b * 22 + q * 2 + j], arr[c * 22 + q * 2 + j], u) for j in (0, 1))


def _touches(feed):
    """(kind, side, index, gap to ball spot, nearest-of-his-side?) per touch."""
    F, home = feed["frames"], feed["match"]["home"]["id"]
    pidx = {m["id"]: (s, i) for s in ("home", "away") for i, m in enumerate(feed["lineups"][s])}
    pos = {m["id"]: m["pos"] for s in ("home", "away") for m in feed["lineups"][s]}
    out = []
    for e in feed["stream"]:
        if e["k"] not in ("pa", "re", "ca", "sh"):
            continue
        side, q = pidx[e["p"]]
        away = e["m"] != home
        ex, ey = (L - e["x"], W - e["y"]) if away else (e["x"], e["y"])
        t = e["tb"]
        gaps = [math.dist(_at(F, side, j, t), (ex, ey)) for j in range(11)]
        out.append((e["k"], pos[e["p"]], gaps[q], min(range(11), key=gaps.__getitem__) == q))
    return out


def test_every_touch_carries_its_ball_time(feed):
    for e in feed["stream"]:
        if e["k"] != "pr":
            assert "tb" in e and e["tb"] >= e["t"] - 1e-6, e


@pytest.mark.parametrize("kind,floor", [("pa", 0.80), ("re", 0.90), ("ca", 0.80)])
def test_the_named_man_is_on_the_ball(feed, kind, floor):
    """Within 3 m of the spot, at the second the ball is there. Was 17%."""
    rows = [r for r in _touches(feed) if r[0] == kind and r[1] != "GK"]
    share = sum(r[2] <= 3.0 for r in rows) / len(rows)
    assert share >= floor, f"{kind}: named player within 3 m on {share:.0%} of {len(rows)} touches"


def test_he_is_the_nearest_man_of_his_side(feed):
    """What a viewer reads as 'who has it'. Was 13%."""
    rows = _touches(feed)
    share = sum(r[3] for r in rows) / len(rows)
    assert share >= 0.85, f"named player nearest on {share:.0%}"


def test_a_keeper_is_not_sent_upfield_to_honour_the_engine(feed):
    """The engine credits keepers with passes in the far third. Honouring
    those would put the goalkeeper in the opposition box; the model
    declines, and the console declines to raise a figure off anyone else."""
    F = feed["frames"]
    for side in ("home", "away"):
        far = 0
        for i in range(F["n"]):
            x = F["h" if side == "home" else "a"][i * 22]
            own = x if side == "home" else L - x
            far += own > 30
        assert far / F["n"] < 0.01, f"{side} keeper beyond 30 m for {far / F['n']:.1%} of the match"


def test_nobody_runs_faster_than_a_footballer(feed):
    """Being on time for every ball must not mean teleporting to it."""
    F = feed["frames"]
    worst = 0.0
    for key in ("h", "a"):
        arr = F[key]
        for q in range(11):
            for i in range(1, F["n"]):
                d = math.hypot(arr[i * 22 + q * 2] - arr[(i - 1) * 22 + q * 2],
                               arr[i * 22 + q * 2 + 1] - arr[(i - 1) * 22 + q * 2 + 1])
                worst = max(worst, d / F["dt"])
    # Frames are rounded to whole metres, so allow a metre of rounding per step.
    assert worst <= 9.0 + 1.0 / F["dt"], f"a player covers {worst:.1f} m/s between frames"


def test_distance_covered_is_a_footballers(feed):
    """The figure on every tag that moves when he does. Outfield players in
    the top flight run roughly 9-13 km; keepers far less."""
    F = feed["frames"]
    for side, key in (("home", "h"), ("away", "a")):
        arr = F[key]
        for q, man in enumerate(feed["lineups"][side]):
            km = sum(math.hypot(arr[i * 22 + q * 2] - arr[(i - 1) * 22 + q * 2],
                                arr[i * 22 + q * 2 + 1] - arr[(i - 1) * 22 + q * 2 + 1])
                     for i in range(1, F["n"])) / 1000
            lo, hi = (2.5, 7.0) if man["pos"] == "GK" else (8.0, 13.5)
            assert lo <= km <= hi, (man["name"], man["pos"], round(km, 2))


def test_the_shape_holds(feed):
    """Sending men to their touches must not turn eleven into a swarm."""
    F = feed["frames"]
    for key in ("h", "a"):
        arr = F[key]
        spread = statistics.mean(
            statistics.pstdev([arr[i * 22 + q * 2] for q in range(1, 11)]) for i in range(0, F["n"], 4))
        assert spread > 12.0, f"outfield x-spread {spread:.1f} m: the block has collapsed"
