"""Audio description: the console's spoken lines, voiced by Azure AI Speech.

The console writes what to say -- who has the ball, the long pass, the
goal, the Form Line claim -- and the browser can voice it on its own. A
browser voice varies by machine and is missing for some languages. A
neural voice is the same everywhere, in all four broadcast languages.

The key never reaches the browser. The page posts the text it wants
spoken to the local server (scripts/serve.py), and the server calls Azure
with the key from its environment and streams back the audio. With no key
configured the endpoint says so, and the page falls back to the browser's
voice -- or to the viewer's own screen reader, which is how most blind
fans already use a computer.

    AZURE_SPEECH_KEY=...  AZURE_SPEECH_REGION=uksouth  python3 scripts/serve.py

Nothing is said here that the page did not compose, and the page composes
claims only from text the Gate has already passed (see `describe()` in the
console and tests/test_audio_description.py).
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import urllib.error
import urllib.request
from xml.sax.saxutils import escape

# One neural voice per broadcast language. The plain-English register is
# English with a slightly slower delivery, not a different voice: it is
# the same commentator speaking plainly.
VOICES: dict[str, tuple[str, str]] = {
    "en": ("en-GB", "en-GB-RyanNeural"),
    "en-simple": ("en-GB", "en-GB-RyanNeural"),
    "es": ("es-ES", "es-ES-AlvaroNeural"),
    "fr": ("fr-FR", "fr-FR-HenriNeural"),
    "ar": ("ar-SA", "ar-SA-HamedNeural"),
}
OUTPUT_FORMAT = "audio-24khz-48kbitrate-mono-mp3"
MAX_CHARS = 400            # one line of commentary, not a document
CACHE = pathlib.Path(os.environ.get("GEGENPRESS_TTS_CACHE", ".cache/tts"))


class SpeechUnavailable(RuntimeError):
    """No key configured, or Azure refused: the page falls back."""


def configured() -> bool:
    return bool(os.environ.get("AZURE_SPEECH_KEY") and os.environ.get("AZURE_SPEECH_REGION"))


def ssml(text: str, lang: str = "en", rate: float = 1.0, excited: bool = False) -> str:
    """The request body. Text is XML-escaped: a player called O'Brien or a
    line with '<' in it must not break -- or inject into -- the markup."""
    if lang not in VOICES:
        lang = "en"
    xml_lang, voice = VOICES[lang]
    rate = max(0.5, min(2.0, rate)) * (0.9 if lang == "en-simple" else 1.0)
    pct = f"{round((rate - 1) * 100):+d}%"
    pitch = "+8%" if excited else "+0%"
    body = escape(text.strip()[:MAX_CHARS], {"'": "&apos;", '"': "&quot;"})
    return (f"<speak version='1.0' xml:lang='{xml_lang}'>"
            f"<voice name='{voice}'><prosody rate='{pct}' pitch='{pitch}'>{body}</prosody></voice>"
            f"</speak>")


def synthesize(text: str, lang: str = "en", rate: float = 1.0, excited: bool = False,
               timeout: float = 8.0) -> bytes:
    """-> MP3 bytes. Cached on disk by request, so a replayed match costs
    nothing and the free tier's 0.5M characters a month go a long way."""
    if not configured():
        raise SpeechUnavailable("AZURE_SPEECH_KEY / AZURE_SPEECH_REGION not set")
    body = ssml(text, lang, rate, excited).encode("utf-8")
    key = hashlib.sha256(body).hexdigest()[:32]
    hit = CACHE / f"{key}.mp3"
    if hit.exists():
        return hit.read_bytes()
    region = os.environ["AZURE_SPEECH_REGION"].strip()
    req = urllib.request.Request(
        f"https://{region}.tts.speech.microsoft.com/cognitiveservices/v1",
        data=body, method="POST",
        headers={
            "Ocp-Apim-Subscription-Key": os.environ["AZURE_SPEECH_KEY"].strip(),
            "Content-Type": "application/ssml+xml",
            "X-Microsoft-OutputFormat": OUTPUT_FORMAT,
            "User-Agent": "gegenpress",
        })
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            audio = r.read()
    except (urllib.error.URLError, TimeoutError) as e:   # HTTPError is a URLError
        raise SpeechUnavailable(f"Azure Speech: {e}") from e
    if not audio:
        raise SpeechUnavailable("Azure Speech returned no audio")
    try:
        CACHE.mkdir(parents=True, exist_ok=True)
        hit.write_bytes(audio)
    except OSError:
        pass                     # a read-only disk costs the cache, not the line
    return audio
