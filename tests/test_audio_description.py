"""Audio description says nothing the data does not, in any language.

A blind fan cannot glance at the strap to check a number they heard. So
the spoken lines are held to a stricter rule than the screen: the console's
own `describe()` runs here in Node over every event of the match, in every
language, and every number it would ever say must come from that event's
row (a pass length), the score at that second, or the clock. Claims are
never composed by the describer at all -- they are the Gate's text,
verbatim -- and the Call it question may contain only numbers the Gate
allows for that moment.

The Azure half is tested without Azure: the SSML is escaped, the voice
matches the language, and with no key the server says so rather than
failing silently, which is what lets the page fall back.
"""

from __future__ import annotations

import io
import json
import pathlib
import re
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
CONSOLE = ROOT / "docs" / "index.html"
FEED = ROOT / "docs" / "feed.json"
NUM = re.compile(r"-?\d+(?:\.\d+)?")


def _fn(src: str, name: str) -> str:
    m = re.search(rf"function {name}\(.*?\n\}}", src, re.S)
    assert m, f"{name}() not found in the console"
    return m.group(0)


@pytest.fixture(scope="module")
def spoken(tmp_path_factory):
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    if not FEED.exists():  # pragma: no cover
        pytest.skip("docs/feed.json not built")
    src = CONSOLE.read_text()
    tmp = tmp_path_factory.mktemp("ad")
    script = tmp / "ad.cjs"
    script.write_text("\n".join(_fn(src, n) for n in ("fill", "describe", "describeMinute", "tallyStream")) + r"""
const feed = JSON.parse(require('fs').readFileSync(process.argv[2], 'utf8'));
const out = [];
const names = {};
for (const s of ['home', 'away']) for (const m of feed.lineups[s]) names[m.id] = m.last;
for (const lang of Object.keys(feed.i18n.ui)) {
  const ui = { ...feed.i18n.ui.en, ...feed.i18n.ui[lang] };
  let last = null;
  for (const e of feed.stream) {
    const t = e.tb ?? e.t, T2 = tallyStream(feed.stream, feed.match.home.id, t);
    for (const verbosity of ['key', 'full']) for (const named of [true, false]) {
      const l = describe(e, { name: names[e.p], club: e.m === feed.match.home.id ? feed.match.home.name : feed.match.away.name,
        verbosity, last, named, home: feed.match.home.name, away: feed.match.away.name,
        hg: T2.home.goals, ag: T2.away.goals }, ui);
      if (l) out.push({ lang, text: l.text, allowed: [e.d != null ? Math.round(e.d) : null, T2.home.goals, T2.away.goals] });
    }
    if (e.k === 'pa' || e.k === 'ca' || e.k === 're') last = e.p;
  }
  for (const min of [15, 30, 45, 60, 75]) {
    const T2 = tallyStream(feed.stream, feed.match.home.id, min * 60);
    const l = describeMinute(min, { home: feed.match.home.name, away: feed.match.away.name,
      hg: T2.home.goals, ag: T2.away.goals }, ui);
    out.push({ lang, text: l.text, allowed: [min, T2.home.goals, T2.away.goals] });
  }
}
console.log(JSON.stringify(out));
""")
    out = subprocess.run(["node", str(script), str(FEED)], capture_output=True, text=True, check=True).stdout
    return json.loads(out)


def test_it_has_plenty_to_say(spoken):
    langs = {s["lang"] for s in spoken}
    assert langs == {"en", "es", "fr", "ar", "en-simple"}
    assert len(spoken) > 5 * 1000


def test_every_spoken_number_comes_from_the_data(spoken):
    bad = []
    for s in spoken:
        allowed = {a for a in s["allowed"] if a is not None}
        for tok in NUM.findall(s["text"]):
            if float(tok) not in allowed:
                bad.append((s["lang"], s["text"], tok))
    assert not bad, f"{len(bad)} spoken numbers not in the data, e.g. {bad[:3]}"


def test_no_template_leaks_into_speech(spoken):
    for s in spoken:
        assert "{" not in s["text"] and "undefined" not in s["text"] and "null" not in s["text"], s


def test_every_goal_is_announced_with_the_score(spoken):
    feed = json.loads(FEED.read_text())
    goals = sum(1 for e in feed["stream"] if e["k"] == "sh" and e.get("g"))
    for lang in ("en", "ar"):
        said = [s for s in spoken if s["lang"] == lang and s["text"] and (
            s["text"].startswith("Goal") or s["text"].startswith("هدف"))]
        # key + full verbosity, named + unnamed
        assert len(said) == goals * 4, (lang, len(said), goals)
    final = [s for s in spoken if s["lang"] == "en" and s["text"].startswith("Goal")][-1]["text"]
    assert f"{feed['match']['home']['goals']}" in final and f"{feed['match']['away']['goals']}" in final


def test_the_call_it_question_says_only_what_the_gate_allows():
    """The question is spoken and printed before the answer: it may show
    the number tonight, never the norm or the verdict."""
    feed = json.loads(FEED.read_text())
    tol = feed["gate"]["tolerance"]
    for lang, ui in feed["i18n"]["ui"].items():
        for m in feed["moments"]:
            if m.get("season_mean") is None:
                continue
            q = ui["call_q"].format(name=m["player"], metric=m["metric"], value=m["value"])
            if m["diverges"]:
                q += " " + ui["call_league"]
            nums = [float(t) for t in NUM.findall(q)]
            assert nums == [m["value"]], (lang, q)
            assert all(any(abs(n - a) <= tol for a in m["allowed"]) for n in nums)
            # and it does not give the answer away
            assert str(m["season_mean"]) not in q and str(m["z"]) not in q


# ---------------------------------------------------------------- Azure side

from gegenpress import speech  # noqa: E402


def test_ssml_is_escaped_and_voiced_per_language():
    x = speech.ssml("O'Brien <shoots> & scores", "fr", 1.25, excited=True)
    assert "O&apos;Brien &lt;shoots&gt; &amp; scores" in x
    assert "fr-FR-HenriNeural" in x and "xml:lang='fr-FR'" in x
    assert "rate='+25%'" in x and "pitch='+8%'" in x
    assert "ar-SA-HamedNeural" in speech.ssml("هدف", "ar")
    assert "en-GB-RyanNeural" in speech.ssml("x", "klingon")   # unknown language: English, not an error
    assert "rate='-10%'" in speech.ssml("x", "en-simple")      # plain register speaks a little slower


def test_without_a_key_it_says_so(monkeypatch):
    monkeypatch.delenv("AZURE_SPEECH_KEY", raising=False)
    monkeypatch.delenv("AZURE_SPEECH_REGION", raising=False)
    assert not speech.configured()
    with pytest.raises(speech.SpeechUnavailable):
        speech.synthesize("Goal!")


def test_with_a_key_it_calls_azure_once_and_caches(monkeypatch, tmp_path):
    monkeypatch.setenv("AZURE_SPEECH_KEY", "k")
    monkeypatch.setenv("AZURE_SPEECH_REGION", "uksouth")
    monkeypatch.setattr(speech, "CACHE", tmp_path)
    calls = []

    def fake_urlopen(req, timeout=0):
        calls.append(req)
        return io.BytesIO(b"ID3fake-mp3")

    monkeypatch.setattr(speech.urllib.request, "urlopen", fake_urlopen)
    a = speech.synthesize("Kowalski, long ball, 31 metres", "en")
    b = speech.synthesize("Kowalski, long ball, 31 metres", "en")
    assert a == b == b"ID3fake-mp3"
    assert len(calls) == 1, "second identical line must come from the cache"
    req = calls[0]
    assert req.full_url == "https://uksouth.tts.speech.microsoft.com/cognitiveservices/v1"
    assert req.get_header("Ocp-apim-subscription-key") == "k"
    assert req.get_header("X-microsoft-outputformat") == speech.OUTPUT_FORMAT
    assert b"en-GB-RyanNeural" in req.data


def test_the_browser_voice_prefers_microsofts_natural_voices(tmp_path):
    """No Azure account needed for a neural voice: Edge hands every page
    Microsoft's own "Online (Natural)" voices. Prefer them, and skip the
    half-populated entries an Edge 150 regression produced."""
    if shutil.which("node") is None:
        pytest.skip("node not installed")
    src = CONSOLE.read_text()
    script = tmp_path / "voice.cjs"
    script.write_text(_fn(src, "pickVoice") + r"""
const V = (name, lang) => ({ name, lang });
global.speechSynthesis = { getVoices: () => [
  V('Microsoft George - English (United Kingdom)', 'en-GB'),
  V('Microsoft undefined Online (Natural) - undefined', 'en-GB'),
  V('Google UK English Male', 'en-GB'),
  V('Microsoft Ryan Online (Natural) - English (United Kingdom)', 'en-GB'),
  V('Microsoft Hamed Online (Natural) - Arabic (Saudi Arabia)', 'ar-SA'),
  V('Microsoft Pablo - Spanish (Spain)', 'es-ES'),
  V('Microsoft Jenny Online (Natural) - English (United States)', 'en-US'),
]};
console.log(JSON.stringify(['en-GB', 'ar-SA', 'es-ES', 'en-AU', 'fr-FR'].map(l => (pickVoice(l) || {}).name || null)));
""")
    out = json.loads(subprocess.run(["node", str(script)], capture_output=True, text=True, check=True).stdout)
    assert out == ["Microsoft Ryan Online (Natural) - English (United Kingdom)",
                   "Microsoft Hamed Online (Natural) - Arabic (Saudi Arabia)",
                   "Microsoft Pablo - Spanish (Spain)",
                   "Microsoft Ryan Online (Natural) - English (United Kingdom)",   # nearest English, Natural first
                   None]
