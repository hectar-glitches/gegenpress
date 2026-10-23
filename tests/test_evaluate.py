"""The evaluation harness must itself be trustworthy."""

from __future__ import annotations

import pytest

from gegenpress.evaluate import CORRUPTIONS, run


@pytest.fixture(scope="module")
def results():
    return run(seeds=(2026,), matches_per_seed=2)


def test_valid_claims_are_never_rejected(results):
    """A false reject is worse than a miss: it silences true statements."""
    assert results.precision == 1.0, results.false_rejects


def test_every_asserted_number_recomputes(results):
    assert results.integrity_failed == 0
    assert results.integrity_checked > 0


def test_refusal_is_never_violated(results):
    """No personal claim on a metric without between-player signal."""
    assert results.refusals_violated == 0
    assert results.refusals_checked > 0


def test_digit_corruptions_are_caught(results):
    """What the Gate actually claims to do."""
    for kind in ("invented number", "fabricated scoreline"):
        assert results.recall(kind) == 1.0, (kind, results.recall(kind))
    assert results.recall("inflated number") > 0.97


def test_known_misses_stay_measured(results):
    """These are documented limits, pinned so a fix is noticed."""
    assert results.recall("number as words") == 0.0
    assert results.recall("misattached number") == 0.0


def test_harness_exercises_every_corruption(results):
    for kind in CORRUPTIONS:
        assert results.attempted.get(kind, 0) > 0, kind
