"""Tests for the Form Line -- the project's actual differentiator.

The load-bearing test is `test_form_lines_diverge_from_league_percentile`.
If a player's match form never disagrees with his league percentile, the
second number is decoration and the whole premise collapses. That was true
of an earlier version of this model, so it is pinned here.
"""

from __future__ import annotations

import pytest

from gegenpress.form import (
    MIN_EFFECT_VS_LEAGUE_SD,
    NOTABLE_Z,
    build_form_baselines,
    form_lines,
)
from gegenpress.season import build_league
from gegenpress.signal import PERSONAL_CLAIM_ICC, measure_signal
from gegenpress.simulate import simulate_match, simulate_season
from gegenpress.store import LocalStore


@pytest.fixture(scope="module")
def world():
    league = build_league(seed=2026)
    season = simulate_season(league, seed=2026)
    store = LocalStore()
    store.load_season(league, season)
    live = simulate_match(league, league.fixtures[0], seed=2027)
    return league, season, store, live


def test_metrics_driven_by_attributes_carry_player_signal(world):
    """The personal reference class needs between-player variance."""
    _league, season, _store, _live = world
    signals = measure_signal(season)
    # These are functions of a player's permanent attributes.
    for metric in ("top_speed_ms", "ball_speed_ms", "pass_distance_m", "carry_distance_m"):
        assert signals[metric].personal_claim_allowed, (metric, signals[metric].icc)


def test_match_level_metrics_are_refused_a_personal_claim(world):
    """Recovery time measures possession length, not the recoverer.

    Counter-pressing is a team behaviour, so 'his best recovery' would be
    league noise with his name on it. The system must refuse it.
    """
    _league, season, _store, _live = world
    signals = measure_signal(season)
    assert not signals["recovery_time_s"].personal_claim_allowed
    assert signals["recovery_time_s"].icc < PERSONAL_CLAIM_ICC


def test_no_form_line_for_a_refused_metric(world):
    _league, season, store, live = world
    refused = {m for m, s in measure_signal(season).items() if not s.personal_claim_allowed}
    assert refused, "expected at least one refused metric"
    for line in store.form_lines(live, notable_only=False):
        assert line.metric not in refused


def test_z_is_direction_aware(world):
    """Positive z must always mean 'better', whichever tail is good."""
    _league, _season, store, live = world
    for line in store.form_lines(live, notable_only=False):
        if line.direction == "low_is_good":
            # A faster (lower) match mean than his norm must score positive.
            assert (line.match_mean < line.season_mean) == (line.z > 0) or line.z == 0
        else:
            assert (line.match_mean > line.season_mean) == (line.z > 0) or line.z == 0


def test_notable_requires_both_significance_and_effect(world):
    _league, _season, store, live = world
    for line in store.form_lines(live, notable_only=True):
        assert abs(line.z) >= NOTABLE_Z
        assert line.effect_vs_league_sd >= MIN_EFFECT_VS_LEAGUE_SD


def test_trivial_shifts_are_excluded(world):
    """A statistically clear but tiny shift is not a story.

    ~90 passes a match makes the distribution of match means very tight,
    so a shift of a few tenths can clear 2 SD while being invisible to a
    viewer. Those must not be surfaced.
    """
    _league, _season, store, live = world
    everything = store.form_lines(live, notable_only=False)
    trivial = [f for f in everything
               if abs(f.z) >= NOTABLE_Z and f.effect_vs_league_sd < MIN_EFFECT_VS_LEAGUE_SD]
    notable = store.form_lines(live, notable_only=True)
    assert not any(f in notable for f in trivial)


def test_labels_are_readable(world):
    """A chained str.replace once produced 'ballpeed' from 'ball_speed_ms'."""
    _league, _season, store, live = world
    for line in store.form_lines(live, notable_only=False):
        text = line.claim()
        assert "_" not in text
        assert "ballpeed" not in text
        assert line.player_name in text


@pytest.mark.parametrize("seed", [2026, 7, 404])
def test_form_lines_diverge_from_league_percentile(seed):
    """THE load-bearing test.

    There must exist moments that are strong for the player but ordinary
    league-wide. If not, the Form Line tells you nothing the league
    percentile did not, and the project has no differentiator.
    """
    league = build_league(seed=seed)
    season = simulate_season(league, seed=seed)
    store = LocalStore()
    store.load_season(league, season)

    diverging = 0
    for fixture in league.fixtures[:5]:
        live = simulate_match(league, fixture, seed=seed + 1)
        diverging += sum(1 for f in store.form_lines(live) if f.diverges)
    assert diverging >= 3, f"only {diverging} diverging form lines across 5 matches"


def test_form_baselines_exclude_short_appearances(world):
    _league, season, _store, _live = world
    baselines = build_form_baselines(season)
    signals = measure_signal(season)
    league2 = build_league(seed=2026)
    live = simulate_match(league2, league2.fixtures[1], seed=99)
    for line in form_lines(baselines, live, signals):
        assert line.appearances >= 6
        assert line.events_this_match >= 5
