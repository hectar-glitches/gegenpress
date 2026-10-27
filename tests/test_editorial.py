"""No AI-written sentence airs without a named producer's approval.

The demo's writer is a template, so this path never runs in the shipped
feed. That is exactly why it is tested: a control that only exists on the
day someone switches a model on has to already work. The model here is
the resilience suite's well-behaved stand-in -- it phrases things
differently from the template on purpose, so we can tell which one aired.
"""

from __future__ import annotations

import json

import pytest

from gegenpress.agents import TemplateModel, run_desk
from gegenpress.editorial import ReviewLog, apply, needs_signoff
from gegenpress.feed import build_feed, verify_feed
from gegenpress.resilience import GroundedModel, UngroundedModel
from gegenpress.season import build_league
from gegenpress.simulate import simulate_live, simulate_season
from gegenpress.store import LocalStore


@pytest.fixture(scope="module")
def world():
    league = build_league(seed=2026)
    season = simulate_season(league, seed=2026)
    live = simulate_live(league, league.fixtures[0], seed=2026)
    store = LocalStore()
    store.load_season(league, season)
    return store, league, live, season


def _segs(world, model, limit=3):
    store, league, live, _ = world
    return run_desk(store, league, live, model=model, limit=limit)


def test_template_text_needs_no_signoff(world):
    for seg in _segs(world, TemplateModel()):
        assert not needs_signoff(seg)


def test_a_failed_model_falls_back_and_needs_no_signoff(world):
    """The gate already replaced it with the template: nothing AI-written airs."""
    for seg in _segs(world, UngroundedModel()):
        assert seg.verdict.fell_back and not needs_signoff(seg)


def test_an_unreviewed_model_sentence_never_airs(world, tmp_path):
    log = ReviewLog(tmp_path / "review.jsonl")
    for seg in _segs(world, GroundedModel()):
        draft = seg.verdict.text
        assert needs_signoff(seg)
        review = apply(seg, log)
        assert review["status"] == "pending" and review["required"]
        assert seg.verdict.text != draft, "the model's draft went to air unreviewed"
        assert seg.verdict.text == TemplateModel().complete("", seg.brief.as_prompt())
    assert len(log.pending()) == 3


def test_approval_puts_the_draft_on_air_with_a_name(world, tmp_path):
    log = ReviewLog(tmp_path / "review.jsonl")
    seg = _segs(world, GroundedModel(), limit=1)[0]
    draft = seg.verdict.text
    did = apply(seg, log)["id"]
    log.decide(did, "approved", "J. Producer")

    seg2 = _segs(world, GroundedModel(), limit=1)[0]
    review = apply(seg2, log)
    assert review["status"] == "approved" and review["by"] == "J. Producer"
    assert seg2.verdict.text == draft


def test_a_changed_draft_needs_a_new_approval(world, tmp_path):
    log = ReviewLog(tmp_path / "review.jsonl")
    seg = _segs(world, GroundedModel(), limit=1)[0]
    log.decide(apply(seg, log)["id"], "approved", "J. Producer")
    seg2 = _segs(world, GroundedModel(), limit=1)[0]
    seg2.verdict.text += " Remarkable."
    assert apply(seg2, log)["status"] == "pending"


def test_rejection_keeps_the_template_and_records_who(world, tmp_path):
    log = ReviewLog(tmp_path / "review.jsonl")
    seg = _segs(world, GroundedModel(), limit=1)[0]
    log.decide(apply(seg, log)["id"], "rejected", "A. Editor", "tone")
    seg2 = _segs(world, GroundedModel(), limit=1)[0]
    review = apply(seg2, log)
    assert review["status"] == "rejected" and review["by"] == "A. Editor"
    assert seg2.verdict.text == TemplateModel().complete("", seg2.brief.as_prompt())


def test_a_decision_needs_a_person(world, tmp_path):
    log = ReviewLog(tmp_path / "review.jsonl")
    seg = _segs(world, GroundedModel(), limit=1)[0]
    did = apply(seg, log)["id"]
    with pytest.raises(ValueError):
        log.decide(did, "approved", "   ")
    with pytest.raises(KeyError):
        log.decide("nope", "approved", "J. Producer")


def test_the_log_is_append_only(world, tmp_path):
    path = tmp_path / "review.jsonl"
    log = ReviewLog(path)
    seg = _segs(world, GroundedModel(), limit=1)[0]
    did = apply(seg, log)["id"]
    log.decide(did, "rejected", "A")
    log.decide(did, "approved", "B")
    events = [json.loads(line)["event"] for line in path.read_text().splitlines()]
    assert events == ["submitted", "rejected", "approved"]
    assert log.state()[did]["by"] == "B"


def test_the_feed_carries_the_review_and_verifies(world, tmp_path):
    store, league, live, season = world
    log = ReviewLog(tmp_path / "review.jsonl")
    feed = build_feed(store, league, live, season, model=GroundedModel(), limit=2, review_log=log)
    assert all(m["review"]["status"] == "pending" for m in feed["moments"])
    assert all(m["provenance"]["generated_by"] == "template" for m in feed["moments"])
    assert verify_feed(feed) == []

    for d in log.pending():
        log.decide(d["id"], "approved", "J. Producer")
    feed = build_feed(store, league, live, season, model=GroundedModel(), limit=2, review_log=log)
    assert all(m["review"]["status"] == "approved" for m in feed["moments"])
    assert all(m["provenance"]["generated_by"] == "ai" for m in feed["moments"])
    assert verify_feed(feed) == []
