"""A player can see, and take, everything the system holds about him --
and the feed can prove its claims were not edited after the gate."""

from __future__ import annotations

import copy
import json
import pathlib

import pytest

from gegenpress.feed import verify_feed
from gegenpress.mcp_server import export_player_data
from gegenpress.privacy import SCHEMA, export_player
from gegenpress.season import build_league
from gegenpress.simulate import simulate_live, simulate_season

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEED = ROOT / "docs" / "feed.json"


@pytest.fixture(scope="module")
def world():
    league = build_league(seed=2026)
    season = simulate_season(league, seed=2026)
    live = simulate_live(league, league.fixtures[0], seed=2026)
    return league, season, live


@pytest.fixture(scope="module")
def kowalski(world):
    league, season, live = world
    pid = next(p.player_id for p in league.players if p.name == "Noor Kowalski")
    feed = json.loads(FEED.read_text()) if FEED.exists() else None
    return pid, export_player(league, season, live, pid, claims=feed and feed["moments"])


def test_every_event_that_names_him_and_no_other(world, kowalski):
    league, season, live = world
    pid, doc = kowalski
    held = sum(e.player_id == pid for m in season + [live] for e in m.events)
    assert doc["events"]["count"] == held == len(doc["events"]["rows"])
    ids = {e.event_id for m in season + [live] for e in m.events if e.player_id == pid}
    assert {r["event_id"] for r in doc["events"]["rows"]} == ids


def test_every_claim_aired_about_him_verbatim(kowalski):
    if not FEED.exists():  # pragma: no cover
        pytest.skip("feed not built")
    _, doc = kowalski
    feed = json.loads(FEED.read_text())
    aired = [m["text"] for m in feed["moments"] if m["player"] == "Noor Kowalski"]
    assert aired and [c["text"] for c in doc["claims"]] == aired
    assert all(c["writer"] and c["gate_passed"] is not None for c in doc["claims"])


def test_he_sees_what_the_system_refuses_to_say_too(kowalski):
    _, doc = kowalski
    by = {n["metric"]: n for n in doc["season_norms"]}
    assert by["recovery_time_s"]["personal_claims_allowed"] is False
    assert by["top_speed_ms"]["personal_claims_allowed"] is True
    assert all(n["why"] for n in doc["season_norms"])


def test_simulator_internals_are_not_exported(kowalski):
    _, doc = kowalski
    text = json.dumps(doc)
    for attr in ("pace", "pressing", "finishing", "tackling", "stamina", "attributes"):
        assert f'"{attr}"' not in text
    assert doc["not_included"] and doc["schema"] == SCHEMA and doc["synthetic"] is True


def test_the_mcp_tool_returns_the_same_document_shape():
    doc = export_player_data("Noor Kowalski")
    assert doc["schema"] == SCHEMA and doc["subject"]["name"] == "Noor Kowalski"
    assert "error" in export_player_data("Nobody Atall")


# ---------------------------------------------------------- provenance

def test_the_shipped_feed_verifies():
    if not FEED.exists():  # pragma: no cover
        pytest.skip("feed not built")
    feed = json.loads(FEED.read_text())
    assert feed["provenance"]["schema"] == "gegenpress-provenance/1"
    assert verify_feed(feed) == []


@pytest.mark.parametrize("tamper,expect", [
    (lambda m: m.__setitem__("text", m["text"].replace("13.77", "21.4")), "text changed"),
    (lambda m: m.__setitem__("allowed", m["allowed"] + [21.4]), "allowed numbers changed"),
    (lambda m: m["provenance"].__setitem__("generated_by", "ai"), "without sign-off"),
])
def test_an_edit_after_the_gate_is_caught(tamper, expect):
    if not FEED.exists():  # pragma: no cover
        pytest.skip("feed not built")
    feed = copy.deepcopy(json.loads(FEED.read_text()))
    m = next(m for m in feed["moments"] if "13.77" in m["text"])
    tamper(m)
    problems = verify_feed(feed)
    assert any(expect in p for p in problems), problems


# ---------------------------------------------------------- objection

def test_an_objecting_player_is_never_the_subject_of_a_claim(world, tmp_path, monkeypatch):
    from gegenpress import privacy
    from gegenpress.feed import build_feed
    from gegenpress.store import LocalStore
    league, season, live = world
    store = LocalStore()
    store.load_season(league, season)
    pid = next(p.player_id for p in league.players if p.name == "Noor Kowalski")

    optout = tmp_path / "optout.json"
    optout.write_text(json.dumps([pid]))
    monkeypatch.setattr(privacy, "OPTOUT", optout)
    monkeypatch.setattr(privacy.objections, "__defaults__", (optout,))
    feed = build_feed(store, league, live, season, limit=8)
    assert all(m["player"] != "Noor Kowalski" for m in feed["moments"])
    for lst in feed["follow_at"].values():
        assert all(f["player_id"] != pid for f in lst)
    assert len(feed["moments"]) == 8, "the slot goes to the next player, not to nobody"


def test_an_unreadable_objection_list_fails_closed(tmp_path):
    from gegenpress.privacy import objections
    bad = tmp_path / "optout.json"
    bad.write_text('{"not": "a list"}')
    with pytest.raises(ValueError):
        objections(bad)
    assert objections(tmp_path / "missing.json") == set()
