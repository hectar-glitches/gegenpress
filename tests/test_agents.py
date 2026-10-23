"""Tests for the agent layer.

The load-bearing ones are about the Gate. A fact-checker that passes
everything is worse than none, because it buys false confidence -- so
these feed it prose that is wrong in specific ways and insist it notices.
"""

from __future__ import annotations

import pytest

from gegenpress.agents import (
    Brief,
    Desk,
    Gate,
    Scout,
    TemplateModel,
    Why,
    get_model,
    run_desk,
)
from gegenpress.season import build_league
from gegenpress.simulate import simulate_match, simulate_season
from gegenpress.store import LocalStore


@pytest.fixture(scope="module")
def world():
    league = build_league(seed=2026)
    season = simulate_season(league, seed=2026)
    store = LocalStore()
    store.load_season(league, season)
    live = simulate_match(league, league.fixtures[0], seed=2027)
    return league, store, live


@pytest.fixture
def brief():
    return Brief(
        minute=63, player_name="Mateo Oyelaran", club_name="Ashcombe United",
        opponent_name="Jarrowdale Park", metric_label="pass range",
        value=15.2, expected=13.9, beats_pct=61.0,
        season_mean=13.9, z=1.9, appearances=18, diverges=True,
    )


# -- Gate ------------------------------------------------------------------

def test_gate_passes_prose_using_only_brief_numbers(brief):
    text = "63' Oyelaran is spraying it 15.2 metres against a season norm of 13.9."
    assert Gate().check(text, brief) == []


def test_gate_catches_an_invented_number(brief):
    text = "Oyelaran has completed 47 passes tonight, at 15.2 metres a time."
    assert 47.0 in Gate().check(text, brief)


def test_gate_catches_a_plausible_but_absent_score(brief):
    """The classic failure: a true-sounding scoreline nobody supplied."""
    text = "At 2-1, Oyelaran's range of 15.2 metres is telling."
    bad = Gate().check(text, brief)
    assert 2.0 in bad or 1.0 in bad


def test_gate_tolerates_rounding(brief):
    """Prose rounds; 61% and 15.2 must still match the brief."""
    text = "15.2 metres, beating 61% of the league."
    assert Gate().check(text, brief) == []


def test_gate_allows_the_z_score_and_appearances(brief):
    text = "15.2 metres, 1.9 standard deviations above his norm across 18 matches."
    assert Gate().check(text, brief) == []


@pytest.mark.xfail(reason="documented hole: the gate reads digits, not words", strict=True)
def test_gate_does_not_catch_numbers_written_as_words(brief):
    text = "Oyelaran has completed forty-seven passes tonight."
    assert Gate().check(text, brief) != []


@pytest.mark.xfail(reason="documented hole: presence is checked, not attachment", strict=True)
def test_gate_does_not_catch_a_number_attached_to_the_wrong_thing(brief):
    """Both numbers are in the brief; they are the wrong way round."""
    text = "Oyelaran's season norm is 15.2 metres; tonight he is at 13.9."
    assert Gate().check(text, brief) != []


# -- Brief -----------------------------------------------------------------

def test_brief_exposes_only_its_own_numbers(brief):
    allowed = brief.allowed_numbers()
    for value in (63, 15.2, 13.9, 61.0, 1.9, 18):
        assert any(abs(value - a) <= 0.051 for a in allowed), value
    assert not any(abs(99.0 - a) <= 0.051 for a in allowed)


def test_brief_without_personal_claim_omits_season_numbers():
    b = Brief(minute=10, player_name="X", club_name="A", opponent_name="B",
              metric_label="recovery time", value=4.2, expected=6.5, beats_pct=98.0)
    assert b.season_mean is None
    assert "season norm" not in b.as_prompt()


def test_diverging_brief_tells_the_writer_the_angle(brief):
    assert "ordinary league-wide" in brief.as_prompt()


# -- Desk ------------------------------------------------------------------

def test_desk_falls_back_when_the_model_will_not_comply(brief):
    class Liar:
        name = "liar"

        def complete(self, system, user):
            return "Oyelaran has 47 passes and 3 assists tonight."

    verdict = Desk(Liar()).write(brief)
    assert not verdict.passed
    assert verdict.fell_back
    assert verdict.attempts == 2
    # The fallback itself must be clean.
    assert Gate().check(verdict.text, brief) == []


def test_desk_retries_before_falling_back(brief):
    class SecondTimeLucky:
        name = "flaky"

        def __init__(self):
            self.calls = 0

        def complete(self, system, user):
            self.calls += 1
            if self.calls == 1:
                return "He has made 47 passes."
            return "Oyelaran's range is 15.2 metres against his 13.9 norm."

    model = SecondTimeLucky()
    verdict = Desk(model).write(brief)
    assert verdict.passed
    assert verdict.attempts == 2
    assert not verdict.fell_back


def test_template_model_output_always_passes_its_own_gate(brief):
    verdict = Desk(TemplateModel()).write(brief)
    assert verdict.passed
    assert verdict.model == "template"


# -- Pipeline --------------------------------------------------------------

def test_run_desk_produces_grounded_segments(world):
    league, store, live = world
    segments = run_desk(store, league, live, model=TemplateModel(), limit=4)
    assert segments
    for seg in segments:
        assert seg.verdict.passed
        assert Gate().check(seg.verdict.text, seg.brief) == []
        assert seg.brief.player_name in seg.verdict.text


def test_scout_puts_diverging_form_first(world):
    _league, store, live = world
    lines = Scout(store).form(live)
    diverging = [f.diverges for f in lines]
    if any(diverging) and not all(diverging):
        assert diverging[0], "a diverging line should lead"


def test_why_refuses_a_personal_claim_on_an_ungated_metric(world):
    league, store, live = world
    why = Why(league)
    for moment in store.top_moments(live, min_beats=0.97, limit=20):
        brief = why.brief_from_moment(moment, live)
        if not moment.personal_claim_allowed:
            assert brief.season_mean is None, moment.metric


def test_get_model_falls_back_without_foundry(monkeypatch):
    monkeypatch.delenv("FOUNDRY_PROJECT_ENDPOINT", raising=False)
    assert get_model().name == "template"
