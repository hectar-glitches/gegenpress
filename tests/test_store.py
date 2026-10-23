"""Store-level tests, plus the local/ADX parity check.

The parity test is the one that matters once a cluster exists: the KQL in
kql/02_functions.kql and the Python in store.py are two implementations of
the same semantics, and two implementations drift. It skips cleanly when
ADX_CLUSTER is unset, so CI stays green without Azure.
"""

from __future__ import annotations

import os

import pytest

from gegenpress.season import build_league
from gegenpress.simulate import simulate_live, simulate_season
from gegenpress.store import LocalStore

ADX_CONFIGURED = bool(os.environ.get("ADX_CLUSTER"))


@pytest.fixture(scope="module")
def fixture_set():
    league = build_league(seed=2026)
    season = simulate_season(league, seed=2026)
    live = simulate_live(league, league.fixtures[0], seed=2026)
    store = LocalStore()
    store.load_season(league, season)
    return league, season, live, store


def test_top_moments_are_ranked_and_grounded(fixture_set):
    _league, _season, live, store = fixture_set
    moments = store.top_moments(live, min_beats=0.97, limit=10)
    assert moments, "no standout moments found"
    assert all(m.beats >= 0.97 for m in moments)
    assert moments == sorted(moments, key=lambda m: -m.beats)
    for m in moments:
        # Every claim the narrative layer could make must be backed.
        assert m.population_n > 1000
        assert m.expected > 0
        assert m.player_name and m.player_name != m.player_id
        assert m.event_id


def test_live_match_is_excluded_from_its_own_baseline(fixture_set):
    """A moment must not be judged against a season containing itself.

    The live match carries its own id, so the season cannot contain it
    even by accident. Before this, it reused a fixture's id and the ADX
    path silently queried the season's version of that match instead.
    """
    league, season, live, _store = fixture_set
    assert live.match_id.startswith("live-")
    assert live.match_id not in {m.match_id for m in season}


def test_match_state_window_is_respected(fixture_set):
    _league, _season, live, store = fixture_set
    narrow = store.match_state(live, as_of_minute=75, window_minutes=5)
    wide = store.match_state(live, as_of_minute=75, window_minutes=45)
    for team in narrow:
        assert wide[team]["passes"] >= narrow[team]["passes"]


def test_match_state_reports_both_teams(fixture_set):
    league, _season, live, store = fixture_set
    state = store.match_state(live, as_of_minute=90, window_minutes=90)
    assert set(state) == {live.home_club_id, live.away_club_id}
    for team_state in state.values():
        assert 0.0 <= team_state["pass_accuracy"] <= 1.0
        assert team_state["gegenpress_idx"] >= 0.0


def test_follow_target_is_ranked(fixture_set):
    _league, _season, live, store = fixture_set
    ranked = store.follow_target(live, as_of_minute=90)
    assert len(ranked) >= 5
    scores = [s for _p, s in ranked]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.skipif(not ADX_CONFIGURED, reason="ADX_CLUSTER not set")
def test_local_and_adx_agree(fixture_set):
    """Parity: the KQL and the Python must return the same moments.

    Run after `python -m gegenpress ingest --bootstrap --load`.
    """
    from gegenpress.adx import AdxStore

    league, _season, live, local = fixture_set
    remote = AdxStore.from_env()
    remote.load_season(league, [])

    a = local.top_moments(live, min_beats=0.98, limit=10)
    b = remote.top_moments(live, min_beats=0.98, limit=10)
    assert [m.event_id for m in a] == [m.event_id for m in b]
    for x, y in zip(a, b):
        assert x.metric == y.metric
        assert abs(x.value - y.value) < 1e-6
        # Percentiles differ slightly: KQL uses 101 cut points, Python the
        # full sorted sample. One percentile point of tolerance.
        assert abs(x.beats - y.beats) < 0.02, (x.metric, x.beats, y.beats)
