"""The TV output: the strap alone, transparent, at 1920x1080, inside
title-safe, driven by take and clear -- and by the four functions CasparCG
calls on an HTML template. Run in a real browser where one is available
(CI's accessibility job has one); the static checks run everywhere."""

from __future__ import annotations

import json
import os
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
PAGE = (ROOT / "docs" / "index.html").read_text()


def test_the_mode_is_there_and_documented():
    assert "OUT.get('output') === 'overlay'" in PAGE
    for word in ("play: take", "stop: clear", "next:", "update:"):
        assert word in PAGE, word
    readme = (ROOT / "README.md").read_text()
    assert "?output=overlay" in readme


def test_title_safe_is_the_broadcast_one():
    """5% of 1920 is 96 px, 5% of 1080 is 54 px."""
    css = re.search(r"body\.overlay \.lower\{([^}]*)\}", PAGE).group(1)
    assert "calc(96px / 1.3)" in css and "calc(54px / 1.3)" in css and "zoom:1.3" in css
    assert "calc((1920px - 192px) / 1.3)" in css


def test_nothing_on_a_programme_feed_asks_or_speaks():
    init = PAGE[PAGE.index("function initOverlay"):PAGE.index("fetch('feed.json')")]
    assert "ACC.callit = false" in init and "ACC.ad = 'off'" in init


def _browser() -> bool:
    if shutil.which("node") is None:
        return False
    return subprocess.run(["node", "-e", "require('playwright')"], capture_output=True).returncode == 0


@pytest.mark.skipif(not _browser() and not os.environ.get("GEGENPRESS_REQUIRE_AXE"),
                    reason="playwright not installed")
def test_in_a_browser_it_keys_takes_and_clears():
    r = subprocess.run(["node", str(ROOT / "scripts" / "tv_check.cjs")],
                       capture_output=True, text=True, timeout=120)
    out = json.loads(r.stdout)
    assert out["ok"], out
