"""The strap's headline: where tonight ranks among his own matches.

"Lowest of his 18 matches" replaces "-3.85 SD" as the big figure because
a fan can read it. It has to be exactly as true as the z-score it stands
in for, so it is recomputed here from the season, independently of the
feed, and checked to point the same way as the z.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from gegenpress.baselines import METRICS
from gegenpress.feed import season_rank
from gegenpress.form import build_form_baselines
from gegenpress.season import build_league
from gegenpress.simulate import simulate_season

ROOT = pathlib.Path(__file__).resolve().parents[1]
FEED = ROOT / "docs" / "feed.json"
LABEL_TO_KEY = {"pass range": "pass_distance_m", "ball speed": "ball_speed_ms",
                "top speed": "top_speed_ms", "carry range": "carry_distance_m",
                "recovery time": "recovery_time_s", "pass difficulty": "pass_difficulty",
                "shot speed": "shot_speed_ms", "xG": "xg"}


def test_ranks_from_the_right_end():
    means = [10.0, 12.0, 14.0, 16.0]
    assert season_rank(means, 9.0, -2.0) == {"pos": 1, "of": 4, "end": "lowest"}
    assert season_rank(means, 13.0, -1.0) == {"pos": 3, "of": 4, "end": "lowest"}
    assert season_rank(means, 17.0, 2.0) == {"pos": 1, "of": 4, "end": "highest"}
    assert season_rank(means, 15.0, 1.0) == {"pos": 2, "of": 4, "end": "highest"}


def test_a_tie_does_not_count_as_a_record():
    """'Lowest' must mean lower than every match he has played."""
    assert season_rank([10.0, 12.0], 10.0, -1.5)["pos"] == 2


def test_low_is_good_metrics_rank_in_raw_values():
    # Worse (z < 0) on a low-is-good metric is a HIGH value.
    assert season_rank([20.0, 25.0, 30.0], 35.0, -2.0, low_is_good=True)["end"] == "highest"
    assert season_rank([20.0, 25.0, 30.0], 15.0, 2.0, low_is_good=True)["end"] == "lowest"


def test_no_rank_without_a_direction():
    assert season_rank([1.0, 2.0], 1.5, 0) is None
    assert season_rank([], 1.5, -1.0) is None


@pytest.fixture(scope="module")
def form():
    league = build_league(seed=2026)
    return league, build_form_baselines(simulate_season(league, seed=2026))


def test_every_shipped_rank_recomputes_from_the_season(form):
    if not FEED.exists():  # pragma: no cover
        pytest.skip("feed not built")
    league, fb = form
    names = {p.name: p.player_id for p in league.players}
    feed = json.loads(FEED.read_text())
    for m in feed["moments"]:
        if m.get("season_mean") is None:
            continue
        key = LABEL_TO_KEY[m["metric"]]
        means = fb.player_match_means[(names[m["player"]], key)]
        rk = m["season_rank"]
        assert rk["of"] == len(means) == m["appearances"], m["player"]
        low = METRICS[key][2] == "low_is_good"
        if (rk["end"] == "lowest") != low:
            assert (m["z"] < 0), (m["player"], "a 'lowest' must be a night below his level")
            assert rk["pos"] == 1 + sum(x <= m["value"] for x in means)
        else:
            assert (m["z"] > 0), (m["player"], "a 'highest' must be a night above his level")
            assert rk["pos"] == 1 + sum(x >= m["value"] for x in means)


def test_the_opener_is_his_lowest_of_the_season():
    """The demo's first frame: pin it, so a regenerated feed cannot quietly
    change what the video says."""
    if not FEED.exists():  # pragma: no cover
        pytest.skip("feed not built")
    feed = json.loads(FEED.read_text())
    k = next(m for m in feed["moments"] if m["player"] == "Noor Kowalski" and m["minute"] == 30)
    assert k["season_rank"] == {"pos": 1, "of": 18, "end": "lowest"}


def test_the_strap_has_a_label_for_every_rank_it_can_show():
    feed = json.loads(FEED.read_text())
    for lang, ui in feed["i18n"]["ui"].items():
        for end in ("lowest", "highest"):
            for pos in (1, 2, 3):
                assert ui.get(f"rank_{end}_{pos}"), (lang, end, pos)
        assert "{n}" in ui["rank_of"], lang
