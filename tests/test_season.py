"""Tests that matter: determinism, persistence, and calibration across seeds."""

from __future__ import annotations

import pytest

from gegenpress.baselines import build_baselines, ground, rarity
from gegenpress.calibrate import run_checks
from gegenpress.season import build_league
from gegenpress.simulate import simulate_match, simulate_season

SEEDS = [2026, 7, 404, 11111]


@pytest.fixture(scope="module")
def league():
    return build_league(seed=2026)


@pytest.fixture(scope="module")
def season(league):
    return simulate_season(league, seed=2026)


def test_league_is_deterministic():
    a, b = build_league(seed=99), build_league(seed=99)
    assert [p.name for p in a.players] == [p.name for p in b.players]
    assert a.players[0].attributes == b.players[0].attributes


def test_different_seeds_give_different_leagues():
    a, b = build_league(seed=1), build_league(seed=2)
    assert [p.name for p in a.players] != [p.name for p in b.players]


def test_match_is_deterministic(league):
    a = simulate_match(league, league.fixtures[0], seed=2026)
    b = simulate_match(league, league.fixtures[0], seed=2026)
    assert len(a.events) == len(b.events)
    assert (a.home_goals, a.away_goals) == (b.home_goals, b.away_goals)
    assert [e.event_id for e in a.events] == [e.event_id for e in b.events]


def test_player_attributes_persist_across_the_season(league, season):
    """The premise of the personal reference class.

    A player's identity and ability must be identical in every match of
    the season, otherwise 'his best press in six games' is noise.
    """
    target = league.players[20]
    appearances = [m for m in season if target.club_id in (m.home_club_id, m.away_club_id)]
    assert len(appearances) >= 10
    assert league.player(target.player_id).attributes == target.attributes


def test_better_passers_complete_more_passes(league, season):
    """Attributes must actually drive outcomes, or the season means nothing."""
    completions: dict[str, list[int]] = {}
    for match in season:
        for e in match.events:
            if e.type == "pass":
                completions.setdefault(e.player_id, []).append(1 if e.outcome else 0)

    rated = [
        (league.player(pid).attributes.passing, sum(v) / len(v))
        for pid, v in completions.items()
        if len(v) >= 200
    ]
    assert len(rated) >= 20
    rated.sort()
    bottom = rated[: len(rated) // 4]
    top = rated[-len(rated) // 4:]
    avg_bottom = sum(a for _s, a in bottom) / len(bottom)
    avg_top = sum(a for _s, a in top) / len(top)
    assert avg_top > avg_bottom + 0.02, (avg_top, avg_bottom)


def test_event_ids_unique_within_match(league):
    match = simulate_match(league, league.fixtures[3], seed=2026)
    ids = [e.event_id for e in match.events]
    assert len(ids) == len(set(ids))


def test_grounding_reports_both_reference_classes(league, season):
    baselines = build_baselines(season)
    pid = next(
        p for (p, m) in baselines.personal if m == "pass_distance_m"
    )
    g = ground(baselines, "pass_distance_m", pid, 42.0)
    assert g.population_n > 1000
    assert g.personal_n > 0
    assert 0.0 <= g.population_percentile <= 1.0
    assert g.personal_mean is not None
    assert g.expected > 0


def test_rarity_direction_is_correct(league, season):
    """A fast recovery is remarkable; a slow one is not."""
    baselines = build_baselines(season)
    fast = rarity(baselines, "recovery_time_s", 1.0)
    slow = rarity(baselines, "recovery_time_s", 60.0)
    assert fast > 0.9, fast
    assert slow < 0.1, slow

    far = rarity(baselines, "pass_distance_m", 60.0)
    near = rarity(baselines, "pass_distance_m", 3.0)
    assert far > 0.9, far
    assert near < 0.1, near


@pytest.mark.parametrize("seed", SEEDS)
def test_calibration_holds_across_seeds(seed):
    """The generator was tuned on seed 2026; it must hold on seeds it never saw."""
    league = build_league(seed=seed)
    season = simulate_season(league, seed=seed)
    failures = [c for c in run_checks(season) if not c.passed]
    assert not failures, [(c.metric, round(c.observed, 2), c.target) for c in failures]
