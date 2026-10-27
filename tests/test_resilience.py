"""Breaking things on purpose.

The claim under test is narrow and worth stating exactly: when one
dependency fails, the broadcast keeps its numbers. The wording may get
duller. The figures may not move.

A resilience test is easy to write badly -- catch an exception, assert
nothing crashed, feel reassured. These try not to. Each one checks that
the output is still *correct*, not merely still present, and the
ungrounded-model test first proves the bad sentence really would have
been rejected, so that the fallback it triggers is not a coincidence.
"""

from __future__ import annotations

import re

import pytest

from gegenpress.agents import Brief, Gate, TemplateModel, get_model
from gegenpress.resilience import (FAULTS, Faults, GroundedModel,
                                   ResilientStore,
                                   UngroundedModel, chaos_run)
from gegenpress.store import LocalStore

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

BRIEF = Brief(
    minute=30, player_name="Noor Kowalski", club_name="Jarrowdale Park",
    opponent_name="Ashcombe United", metric_label="pass range",
    value=13.77, expected=14.64, beats_pct=37.4,
    season_mean=17.07, z=-3.85, appearances=18, diverges=True,
)


@pytest.fixture(autouse=True)
def clean_faults():
    """No test may leak a broken world into the next one."""
    before = Faults(**vars(FAULTS))
    yield
    for attr in ("adx", "foundry", "model"):
        setattr(FAULTS, attr, getattr(before, attr))


class DiesAfter:
    """A store that answers, then stops. The outage that matters.

    `get_store()` already handles a cluster that is down at startup.
    This is the one that answers at kickoff and times out at 60'.
    """

    def __init__(self, calls_before_death: int = 1) -> None:
        self.remaining = calls_before_death
        self.loaded = False

    def load_season(self, league, matches) -> None:
        self.loaded = True

    def top_moments(self, *a, **k):
        if self.remaining <= 0:
            raise ConnectionError("cluster gone")
        self.remaining -= 1
        return ["from the primary"]


class Standby:
    """A standby that can say where its answer came from."""

    def __init__(self) -> None:
        self.loaded = False

    def load_season(self, league, matches) -> None:
        self.loaded = True

    def top_moments(self, *a, **k):
        return ["from the standby"]


def test_failover_happens_per_call_not_only_at_startup():
    primary, standby = DiesAfter(calls_before_death=1), Standby()
    store = ResilientStore(primary, standby=standby)
    store.load_season(None, [])

    assert store.top_moments() == ["from the primary"]
    assert store.failovers == 0

    # Second call: the cluster has gone. The pipeline has not.
    assert store.top_moments() == ["from the standby"]
    assert store.failovers == 1
    assert "ConnectionError" in store.log[0]


def test_the_standby_is_loaded_even_when_the_primary_dies_loading():
    class RefusesToLoad:
        def load_season(self, league, matches):
            raise ConnectionError("cluster gone")

    standby = Standby()
    store = ResilientStore(RefusesToLoad(), standby=standby)
    store.load_season(None, [])
    assert store.failovers == 1
    # A standby that never loaded the season is not a standby.
    assert standby.loaded


def test_injected_adx_outage_skips_the_primary_entirely():
    primary = DiesAfter(calls_before_death=99)
    store = ResilientStore(primary, standby=LocalStore())
    FAULTS.adx = True
    store.load_season(None, [])
    assert store.failovers == 1
    assert isinstance(store.log[0], str) and "Injected" in store.log[0]


def test_injected_foundry_outage_degrades_to_templates(monkeypatch):
    monkeypatch.setenv("FOUNDRY_PROJECT_ENDPOINT", "https://example/api/projects/p")
    monkeypatch.setenv("FOUNDRY_MODEL", "gpt-5-mini")
    FAULTS.foundry = True
    model = get_model()
    assert isinstance(model, TemplateModel)


def test_the_ungrounded_sentence_really_would_be_rejected():
    """Without this, the fallback test below proves nothing: a model
    whose output happened to pass would trigger no fallback at all."""
    bad = UngroundedModel().complete("", BRIEF.as_prompt())
    assert 21.4 in Gate().unsupported(bad, BRIEF)


def test_the_stub_model_is_actually_grounded():
    """The healthy baseline must pass the gate, or the comparison is
    between two fallbacks."""
    good = GroundedModel().complete("", BRIEF.as_prompt())
    assert Gate().unsupported(good, BRIEF) == []
    assert good != TemplateModel().complete("", BRIEF.as_prompt())


# --------------------------------------------------------------------------
# The whole pipeline, broken one piece at a time
# --------------------------------------------------------------------------

@pytest.fixture(scope="module")
def chaos():
    return chaos_run(seed=2026, limit=4)


def test_every_fault_still_delivers_every_claim(chaos):
    base = next(r for r in chaos.rows if r.fault.startswith("none"))
    for row in chaos.rows:
        assert row.claims == base.claims, f"{row.fault} lost claims"
        assert row.survived, row.fault


def test_no_fallback_changes_a_number(chaos):
    """The property worth having. Degrading is easy; degrading without
    editing the broadcast is not."""
    for row in chaos.rows:
        assert row.numbers_identical, (
            f"{row.fault} degraded to {row.degraded_to} and the numbers moved"
        )


def test_the_adx_fault_actually_exercised_the_failover(chaos):
    """Guards the embarrassing version of this test, where nothing broke
    and everything passed."""
    row = next(r for r in chaos.rows if r.fault == "adx")
    assert row.failovers > 0


def test_chaos_restores_the_world(chaos):
    assert not FAULTS.any()
