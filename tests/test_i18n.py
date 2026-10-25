"""Four languages and a plain-English register, held to one gate.

The load-bearing tests here are the last two. Everything else is
housekeeping: that no language is missing a word, that nothing renders
blank. The claim worth proving is that translation does not weaken the
control -- the same Gate accepts every language, and the digits on screen
are identical in all of them.

That property is not a nicety. It is the reason this costs one module
instead of a verifier per locale: the Gate reads numbers, and numbers are
not a language. A fact-checker that is itself a model has to be retrained,
re-thresholded and re-evaluated in every language it ships, which is why
most systems ship one.
"""

from __future__ import annotations

import re

import pytest

from gegenpress.agents import Brief, Gate
from gegenpress.i18n import (DIRECTION, LANGUAGE_CODES, LANGUAGES, METRICS, UI,
                             form_claim, metric_label, moment_text, ui)

NUMBER = re.compile(r"-?\d+(?:\.\d+)?")

BRIEF = Brief(
    minute=30,
    player_name="Noor Kowalski",
    club_name="Jarrowdale Park",
    opponent_name="Ashcombe United",
    metric_label="pass range",
    value=13.77,
    expected=14.64,
    beats_pct=37.4,
    season_mean=17.07,
    z=-3.85,
    appearances=18,
    diverges=True,
)


def test_every_language_knows_every_metric():
    keys = set(METRICS["en"])
    for code in LANGUAGE_CODES:
        missing = keys - set(METRICS[code])
        assert not missing, f"{code} is missing {sorted(missing)}"


def test_every_language_knows_every_ui_string():
    keys = set(UI["en"])
    for code in LANGUAGE_CODES:
        missing = keys - set(UI[code])
        assert not missing, f"{code} is missing {sorted(missing)}"


def test_ui_never_renders_blank():
    """A missing key falls back to English rather than to nothing. An
    empty label on air is worse than an untranslated one."""
    for code in LANGUAGE_CODES:
        for key, value in ui(code).items():
            assert value.strip(), f"{code}.{key} is empty"


def test_direction_is_declared_for_each_language():
    assert set(DIRECTION) == set(LANGUAGE_CODES)
    assert DIRECTION["ar"] == "rtl"
    assert {d for _, _, d in LANGUAGES} <= {"ltr", "rtl"}


def test_arabic_is_actually_arabic():
    """Guards the dull failure where a locale is added and left in
    English, which reads as support without being it."""
    label = metric_label("pass_distance_m", "ar")
    assert any("؀" <= ch <= "ۿ" for ch in label), label
    assert label != metric_label("pass_distance_m", "en")


def test_plain_english_drops_the_jargon():
    """The register exists to be understood by someone who has not heard
    of a pass range, so it must not say 'pass range'."""
    for key in METRICS["en"]:
        simple = metric_label(key, "en-simple")
        assert simple != METRICS["en"][key], key
        assert simple.startswith("how "), simple


# --------------------------------------------------------------------------
# The two that matter
# --------------------------------------------------------------------------

@pytest.mark.parametrize("code", LANGUAGE_CODES)
def test_every_language_passes_the_same_gate(code):
    """One control, every locale, no second verifier."""
    gate = Gate()
    text = moment_text(
        code, minute=BRIEF.minute, player=BRIEF.player_name,
        metric_key="pass_distance_m", value=f"{BRIEF.value:g}",
        norm=f"{BRIEF.season_mean:g}",
    )
    assert gate.unsupported(text, BRIEF) == [], text

    claim = form_claim(
        code, player=BRIEF.player_name, metric_key="pass_distance_m",
        value=f"{BRIEF.value:.1f}", norm=f"{BRIEF.season_mean:.1f}",
        z=f"{BRIEF.z:+.1f}", appearances=BRIEF.appearances, direction="below",
    )
    assert gate.unsupported(claim, BRIEF) == [], claim


def test_the_numbers_do_not_move_when_the_language_does():
    """What a viewer should see when they switch: the words change and
    the figures do not. If this ever fails, the translation is editing
    the claim rather than restating it."""
    digits = {}
    for code in LANGUAGE_CODES:
        text = moment_text(
            code, minute=BRIEF.minute, player=BRIEF.player_name,
            metric_key="pass_distance_m", value=f"{BRIEF.value:g}",
            norm=f"{BRIEF.season_mean:g}",
        )
        digits[code] = sorted(NUMBER.findall(text))
    reference = digits["en"]
    for code, found in digits.items():
        assert found == reference, f"{code} shows {found}, English shows {reference}"


def test_western_digits_everywhere_including_arabic():
    """Arabic-Indic numerals would satisfy the Gate -- Python's \\d is
    Unicode-aware -- but one numeral set means the figure on screen is
    the figure in the payload in every locale."""
    text = moment_text(
        "ar", minute=30, player="Noor Kowalski",
        metric_key="pass_distance_m", value="13.77", norm="17.07",
    )
    assert "13.77" in text and "17.07" in text
    assert not any("٠" <= ch <= "٩" for ch in text)


def test_an_unknown_language_falls_back_rather_than_crashing():
    assert metric_label("pass_distance_m", "zz") == "pass range"
    assert ui("zz")["tonight"] == "TONIGHT"
    assert "13.77" in moment_text(
        "zz", minute=30, player="X", metric_key="pass_distance_m",
        value="13.77", norm="17.07",
    )
