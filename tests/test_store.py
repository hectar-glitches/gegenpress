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

    Run after:
        python -m gegenpress ingest --bootstrap --reset --load

    Both sides must be built from the same seed, which they are: the
    ingest command simulates with `build_league(seed)` and
    `league.fixtures[0]`, exactly as this module's fixture does.
    """
    from gegenpress.adx import AdxStore

    league, _season, live, local = fixture_set
    remote = AdxStore.from_env()
    remote.load_season(league, [])

    a = local.top_moments(live, min_beats=0.98, limit=10)
    b = remote.top_moments(live, min_beats=0.98, limit=10)

    # Fail loudly on an empty cluster rather than asserting [] == [] and
    # reporting parity that was never tested. Queued ingestion on a free
    # cluster lands a minute or two after the command returns.
    assert a, "local found no moments: the fixture itself is wrong"
    assert b, (
        f"ADX returned no moments for {live.match_id}. Ingestion may still "
        "be in flight, or the cluster holds a different season. Run "
        "`python -m gegenpress doctor` and check the row counts."
    )

    assert [m.event_id for m in a] == [m.event_id for m in b], (
        "the two implementations rank moments differently"
    )
    for x, y in zip(a, b):
        assert x.metric == y.metric
        assert abs(x.value - y.value) < 1e-6, (x.metric, x.value, y.value)
        # Both sides now compute the SAME quantity: the exact share of the
        # population strictly below the value, rounded to 4 places. The
        # tolerance is one rounding unit, for .NET vs Python round() at
        # an exact midpoint -- not a licence for approximation. (The first
        # version allowed 0.02 here because KQL used a 101-cut T-Digest
        # estimate; that tolerance hid the very drift this test exists to
        # catch, and the ranking assertion above is what exposed it.)
        #
        # Not asserted: `expected` (the league median). KQL's percentile()
        # is a T-Digest estimate and Python's is exact; it is a display
        # value, not part of what decides which moments surface.
        assert abs(x.beats - y.beats) <= 1.5e-4, (x.metric, x.beats, y.beats)
        # The ICC gate is the thing this project is actually about, and
        # it is computed twice -- `variancep` in KQL, `pvariance` in
        # Python. If those ever disagree, one of the two backends is
        # permitting a personal claim the other refuses, which is the
        # exact drift this test exists to catch.
        assert x.personal_claim_allowed == y.personal_claim_allowed, (
            x.metric, x.personal_claim_allowed, y.personal_claim_allowed
        )
