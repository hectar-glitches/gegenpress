"""The MCP tool layer, tested without the SDK.

The logic functions are plain Python over the same Store the console
uses; `serve()` is the only thing that needs the `mcp` package. So these
tests prove the service tells the truth, and skip nothing.
"""

from __future__ import annotations

import pytest

from gegenpress import mcp_server as srv


@pytest.fixture(scope="module", autouse=True)
def built_world():
    return srv.world()        # built once; ~seconds


def test_match_info_names_the_synthetic_world():
    info = srv.match_info()
    assert info["match_id"].startswith("live-")
    assert info["season"]["matches"] >= 90
    assert "synthetic" in info["note"]


def test_player_resolution_is_fuzzy_but_unique():
    w = srv.world()
    some = w.league.players[0]
    assert w.player_id(some.name) == some.player_id
    assert w.player_id(some.name.upper()) == some.player_id
    assert w.player_id("zz-no-such-player") is None


def test_metric_resolves_by_label_and_key():
    w = srv.world()
    assert w.metric_key("pass range") == "pass_distance_m"
    assert w.metric_key("pass_distance_m") == "pass_distance_m"
    assert w.metric_key("recovery time") == "recovery_time_s"


def test_form_line_refuses_metrics_without_signal():
    out = srv.form_line(srv.world().league.players[0].name, "recovery time")
    assert out.get("refused") is True
    assert "league" in out["reason"].lower()


def test_form_line_returns_the_sayable_claim():
    # Find any player with a supportable line and check the payload.
    w = srv.world()
    lines = srv.compute_form_lines(w.store._form, w.live, w.signals, w.names,
                                   as_of_minute=90)
    assert lines, "no form lines in the live match"
    line = lines[0]
    out = srv.form_line(line.player_name, line.metric)
    assert out["tonight_mean"] == round(line.match_mean, 2)
    assert out["season_mean"] == round(line.season_mean, 2)
    assert line.player_name in out["sayable_claim"]


def test_verify_claim_passes_truth_and_rejects_invention():
    w = srv.world()
    lines = srv.compute_form_lines(w.store._form, w.live, w.signals, w.names,
                                   as_of_minute=90)
    line = lines[0]
    ok = srv.verify_claim(line.claim(), line.player_name, line.metric)
    assert ok["verdict"] == "passed", ok

    bad = srv.verify_claim(
        f"{line.player_name} has made 73.9 of these tonight.",
        line.player_name, line.metric)
    assert bad["verdict"] == "rejected"
    assert 73.9 in bad["unsupportable_numbers"]


def test_verify_claim_refuses_unsupportable_reference_class():
    w = srv.world()
    out = srv.verify_claim("His best recovery of the season, just 2.1s!",
                           w.league.players[0].name, "recovery time")
    assert out["verdict"] == "refused"
