"""The live scoreboard is the Python state block, arriving one second at a
time.

The console tallies passes, shots, goals, recoveries and possession in
the page from the event stream as the clock runs. That is a second
implementation of numbers the Python already computes at 90', and two
implementations drift -- so this runs the page's own `tallyStream()` in
Node over the shipped stream and holds it to the Python block, the same
way the KQL is held to the Python and the browser gate to the server's.

It also pins the thing a viewer would notice first: the score at kickoff
is 0-0, and each goal arrives at the minute the stream says it does.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "docs" / "index.html"
FEED = ROOT / "docs" / "feed.json"

pytestmark = pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")


def _feed() -> dict:
    if not FEED.exists():  # pragma: no cover
        pytest.skip("docs/feed.json not built")
    return json.loads(FEED.read_text())


def _tally(tmp_path, feed: dict, t: float) -> dict:
    src = CONSOLE.read_text()
    match = re.search(r"function tallyStream\(.*?\n\}", src, re.S)
    assert match, "tallyStream() not found in the console"
    script = tmp_path / "tally.cjs"
    script.write_text(
        match.group(0)
        + "\nconst [stream, homeId, t] = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));"
          "\nconsole.log(JSON.stringify(tallyStream(stream, homeId, t)));"
    )
    payload = tmp_path / "payload.json"
    payload.write_text(json.dumps([feed["stream"], feed["match"]["home"]["id"], t]))
    out = subprocess.run(["node", str(script), str(payload)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_score_is_nil_nil_at_kickoff(tmp_path):
    r = _tally(tmp_path, _feed(), 0.0)
    assert (r["home"]["goals"], r["away"]["goals"]) == (0, 0)


def test_each_goal_arrives_when_the_stream_says(tmp_path):
    feed = _feed()
    goals = [e for e in feed["stream"] if e["k"] == "sh" and e.get("g")]
    assert goals, "this match has no goals; pick another seed for the demo"
    for i, g in enumerate(goals, start=1):
        before = _tally(tmp_path, feed, g["t"] - 0.01)
        after = _tally(tmp_path, feed, g["t"])
        assert before["home"]["goals"] + before["away"]["goals"] == i - 1
        assert after["home"]["goals"] + after["away"]["goals"] == i


def test_full_time_tally_matches_the_python_state_block(tmp_path):
    feed = _feed()
    r = _tally(tmp_path, feed, 10_000.0)
    final = {feed["match"]["home"]["short"]: r["home"], feed["match"]["away"]["short"]: r["away"]}
    for short, s in feed["state"].items():
        live = final[short]
        assert live["shots"] == s["shots"], (short, "shots")
        # Passes and recoveries: the state block closes its window at 90'
        # and the stream runs into stoppage time, so allow the tail.
        assert abs(live["passes"] - s["passes"]) <= 0.03 * s["passes"], (short, "passes", live["passes"], s["passes"])
        assert abs(live["recoveries"] - s["recoveries"]) <= 0.05 * s["recoveries"] + 1, (short, "recoveries")


def test_final_score_matches_the_match(tmp_path):
    feed = _feed()
    r = _tally(tmp_path, feed, 10_000.0)
    assert r["home"]["goals"] == feed["match"]["home"]["goals"]
    assert r["away"]["goals"] == feed["match"]["away"]["goals"]


def test_possession_sums_to_one_hundred(tmp_path):
    feed = _feed()
    for t in (600.0, 1800.0, 5400.0):
        r = _tally(tmp_path, feed, t)
        assert r["home"]["possPct"] + r["away"]["possPct"] == 100


# --------------------------------------------------------------------------
# Who to follow is a question with a different answer at 30' than at 90'
# --------------------------------------------------------------------------

def test_follow_is_ranked_at_every_checkpoint():
    from gegenpress.form import CHECKPOINTS
    feed = _feed()
    assert set(feed["follow_at"]) == {str(m) for m in CHECKPOINTS}
    assert feed["follow"] == feed["follow_at"][str(CHECKPOINTS[-1])]


def test_the_ranking_actually_changes_during_the_match():
    """If every checkpoint produced the same six in the same order, the
    per-checkpoint lists would be theatre."""
    feed = _feed()
    orders = {m: [f["player_id"] for f in lst] for m, lst in feed["follow_at"].items()}
    assert len({tuple(o) for o in orders.values()}) > 1


def test_no_checkpoint_sees_the_future():
    """An entry ranked as of 30' may carry only touches up to 30'."""
    feed = _feed()
    for m, lst in feed["follow_at"].items():
        for f in lst:
            for e in f.get("events", []):
                assert e["minute"] <= int(m), (m, f["player"], e["minute"])
