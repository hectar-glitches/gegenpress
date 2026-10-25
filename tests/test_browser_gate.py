"""The gate in the browser must be the gate in Python.

The console lets a viewer type a sentence and watches it get refused.
That is the most persuasive thing this project does, and it is also the
easiest place to quietly cheat: a check that lives in JavaScript, drifts
from the Python one, and makes the demo look better than the system is.

So it is tested the same way the KQL is -- by running both and insisting
they agree. The browser is handed no rule of its own: the numbers a claim
may contain ship with the moment, straight from the Brief the Python Gate
reads, and the tolerance ships with the feed. All the page does is find
digits and compare. These tests pin that it finds the same digits and
reaches the same verdict.

The alternative, two implementations of one threshold, is exactly the bug
that `MetricSignal` and the percentile ranking both turned out to be.
"""

from __future__ import annotations

import json
import pathlib
import re
import shutil
import subprocess

import pytest

from gegenpress.agents import TOLERANCE, Brief, Gate

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "docs" / "index.html"
FEED = ROOT / "docs" / "feed.json"

SENTENCES = [
    "Noor Kowalski's pass range is 21.4 tonight, the best of his season.",
    "Kowalski's pass range is 13.77 tonight against a season norm of 17.07.",
    "He is at 13.8, down from 17.1 over 18 matches.",
    "He beat 37% of the league but hit 99.9 at his peak.",
    "He was quietly excellent.",
    "-3.85 SD, and 0 goals, and 1000 passes.",
    "30' 13.77 14.64 37.4 17.07 -3.85 18",
    "His xG was 0.004 and his top speed 8.",
]


def _feed() -> dict:
    if not FEED.exists():  # pragma: no cover - feed is committed
        pytest.skip("docs/feed.json not built")
    return json.loads(FEED.read_text())


def _brief_from(moment: dict) -> Brief:
    return Brief(
        minute=moment["minute"], player_name=moment["player"],
        club_name=moment["club"], opponent_name="-",
        metric_label=moment["metric"], value=moment["value"],
        expected=moment["expected"], beats_pct=moment["league_pct"],
        season_mean=moment.get("season_mean"), z=moment.get("z"),
        appearances=moment.get("appearances"),
    )


def test_the_feed_publishes_the_allowed_numbers_the_gate_uses():
    """The browser is given the answer key, not a copy of the rule."""
    for moment in _feed()["moments"]:
        expected = [round(v, 4) for v in _brief_from(moment).allowed_numbers()]
        assert moment["allowed"] == expected, moment["minute"]


def test_the_tolerance_is_published_not_duplicated():
    assert _feed()["gate"]["tolerance"] == TOLERANCE


def test_the_page_does_not_hardcode_a_second_tolerance():
    """A literal 0.051 in the page would be a second source of truth. The
    fallback after `||` is allowed to exist, but it must agree."""
    src = CONSOLE.read_text()
    literals = {float(x) for x in re.findall(r"0\.0\d{2}\b", src)}
    assert literals <= {TOLERANCE}, (
        f"page carries tolerance literals {literals} besides {TOLERANCE}"
    )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_the_browser_gate_agrees_with_the_python_gate(tmp_path):
    """Run the page's own function. Not a reimplementation of it."""
    src = CONSOLE.read_text()
    match = re.search(r"function gateMarks\(.*?\n\}", src, re.S)
    assert match, "gateMarks() not found in the console"

    feed = _feed()
    moment = feed["moments"][0]
    brief = _brief_from(moment)

    script = tmp_path / "gate.mjs"
    script.write_text(
        match.group(0)
        + "\nconst [text, allowed, tol] = JSON.parse(process.argv[2]);"
          "\nconst marks = gateMarks(text, allowed, tol);"
          "\nconsole.log(JSON.stringify("
          "marks.filter(m => !m.ok).map(m => parseFloat(m.tok))));"
    )

    for sentence in SENTENCES:
        payload = json.dumps([sentence, moment["allowed"], feed["gate"]["tolerance"]])
        out = subprocess.run(
            ["node", str(script), payload],
            capture_output=True, text=True, check=True,
        ).stdout
        from_browser = json.loads(out)
        from_python = Gate.unsupported(sentence, brief)
        assert from_browser == from_python, (
            f"{sentence!r}\n  browser rejected {from_browser}\n"
            f"  python  rejected {from_python}"
        )


@pytest.mark.skipif(shutil.which("node") is None, reason="node not installed")
def test_they_agree_on_every_moment_not_just_the_first(tmp_path):
    """One moment agreeing could be luck. Every moment agreeing is the
    claim the console makes when a viewer clicks through the rail."""
    src = CONSOLE.read_text()
    match = re.search(r"function gateMarks\(.*?\n\}", src, re.S)
    script = tmp_path / "gate.mjs"
    script.write_text(
        match.group(0)
        + "\nconst cases = JSON.parse(process.argv[2]);"
          "\nconsole.log(JSON.stringify(cases.map(([t, a, tol]) =>"
          " gateMarks(t, a, tol).filter(m => !m.ok).map(m => parseFloat(m.tok)))));"
    )

    feed = _feed()
    tol = feed["gate"]["tolerance"]
    cases, expected = [], []
    for moment in feed["moments"]:
        brief = _brief_from(moment)
        for sentence in SENTENCES:
            cases.append([sentence, moment["allowed"], tol])
            expected.append(Gate.unsupported(sentence, brief))

    out = subprocess.run(
        ["node", str(script), json.dumps(cases)],
        capture_output=True, text=True, check=True,
    ).stdout
    assert json.loads(out) == expected
