"""Render the crowd, offline, from nothing.

The first crowd was three bandpassed noise loops shaped in real time, and
it sounded like what it was: wind. The second was granular but built only
from two narrow vowel formants with nothing above 2.8 kHz -- hollow sung
tones, which is the recipe for a ghost choir, and that is what it got
called. A real crowd is mostly TRANSIENTS and AIR: scattered clapping,
the fricative crackle of thousands of consonants, whistles, energy out
past 6 kHz. The vowels are the minority.

So each voice grain now has three wide formants plus a consonant burst on
its onset, and two further layers exist outright: claps (short decaying
broadband snaps -- the single most recognisable crowd texture) and sparse
distant whistles. All of it ours, no third-party audio anywhere:

  docs/audio/crowd.mp3   seamless ~28s: chatter + scattered applause +
                         a couple of far whistles over a low rumble
  docs/audio/roar.mp3    ~6s one-shot: open-vowel shout grains over an
                         applause wall, fast swell, long decay

Run: python scripts/make_crowd.py        (writes docs/audio/, prints the
                                          measurements that define done)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import numpy as np
from scipy.signal import butter, sosfilt

SR = 44100
rng = np.random.default_rng(2026)

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "audio"


def voice_grain(dur: float, f1: float, f2: float, voiced: float) -> np.ndarray:
    """One short utterance. Three WIDE formants -- narrow ones whistle --
    and a consonant burst at the onset, because speech without consonants
    is a seance."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    src = rng.standard_normal(n) * 0.6
    if voiced > 0:
        f0 = rng.uniform(100, 280)
        # A pulse train with jitter: square-wave buzz through a narrow
        # band is an organ pipe.
        ph = 2 * np.pi * f0 * t * (1 + 0.02 * np.sin(2 * np.pi * 5.3 * t))
        buzz = (np.sin(ph) + .5 * np.sin(2 * ph + .7) + .25 * np.sin(3 * ph + 1.9))
        src = src * (1 - voiced * .8) + buzz * voiced * 0.45
    out = np.zeros(n)
    f3 = rng.uniform(2400, 3400)
    for fc, bw, w in ((f1, 180, 1.0), (f2, 300, 0.6), (f3, 500, 0.3)):
        sos = butter(2, [max(60, fc - bw), fc + bw], "bandpass", fs=SR, output="sos")
        out += w * sosfilt(sos, src)
    # Consonant onset: a short high-passed burst, the "t/s/k" that makes
    # it read as talking rather than humming.
    if rng.random() < 0.5:
        cn = int(rng.uniform(.02, .07) * SR)
        if cn < n:
            sos = butter(2, [2200, 7800], "bandpass", fs=SR, output="sos")
            burst = sosfilt(sos, rng.standard_normal(cn))
            out[:cn] += burst * rng.uniform(.35, .8) * np.linspace(1, 0, cn)
    syl = rng.uniform(3, 8)
    env = (np.sin(np.pi * np.minimum(1, t / dur)) ** 1.2
           * (0.55 + 0.45 * np.sin(2 * np.pi * syl * t + rng.uniform(0, 6))))
    return out * env


def clap() -> np.ndarray:
    """One clap: a few milliseconds of broadband snap with a fast decay.
    Thousands of these, uncoordinated, are the crackle every stadium
    recording is full of and every 'ghost choir' lacks."""
    n = int(rng.uniform(.008, .02) * SR)
    sos = butter(2, [900, 7500], "bandpass", fs=SR, output="sos")
    c = sosfilt(sos, rng.standard_normal(n))
    return c * np.exp(-np.arange(n) / (n * rng.uniform(.25, .5)))


def whistle(dur: float) -> np.ndarray:
    """A far-off crowd whistle: a bright tone that bends."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    f = rng.uniform(1700, 2600) * (1 + .08 * np.sin(2 * np.pi * rng.uniform(2, 5) * t))
    w = np.sin(2 * np.pi * np.cumsum(f) / SR)
    return w * np.sin(np.pi * t / dur) ** 2


def scatter(bed: np.ndarray, g: np.ndarray, amp: float, at: int) -> None:
    """Drop a grain into the stereo bed, wrapping so loops stay seamless."""
    n = bed.shape[1]
    pan = rng.uniform(0, 1)
    at %= n
    m = min(len(g), n - at)
    bed[0, at:at + m] += g[:m] * amp * (1 - pan)
    bed[1, at:at + m] += g[:m] * amp * pan
    if m < len(g):
        r = len(g) - m
        bed[0, :r] += g[m:] * amp * (1 - pan)
        bed[1, :r] += g[m:] * amp * pan


def rumble(secs: float) -> np.ndarray:
    n = int(secs * SR)
    sos = butter(2, 180, "lowpass", fs=SR, output="sos")
    r = np.stack([sosfilt(sos, rng.standard_normal(n)),
                  sosfilt(sos, rng.standard_normal(n))])
    k = int(0.5 * SR)
    w = np.linspace(0, 1, k)
    r[:, :k] = r[:, :k] * w + r[:, -k:] * (1 - w)
    return r


def normalise(x: np.ndarray, rms_db: float) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2))
    x = x * (10 ** (rms_db / 20) / max(rms, 1e-9))
    # Soft saturation, never a hard clip: a hard-clipped transient is
    # electrical crackle by construction.
    return np.tanh(x / .85) * .85


def encode(x: np.ndarray, path: pathlib.Path) -> None:
    raw = (x.T * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
         "-c:a", "libmp3lame", "-b:a", "128k", str(path)],
        input=raw, check=True)


def measure(x: np.ndarray, name: str) -> None:
    mono = x.mean(axis=0)
    # Syllabic modulation: chatter peaks at 3-8 Hz, static has no peak.
    env = np.abs(mono)
    sos = butter(2, 30, "lowpass", fs=SR, output="sos")
    env = sosfilt(sos, env)[:: SR // 200]
    env = env - env.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    freqs = np.fft.rfftfreq(len(env), 1 / 200)
    band = lambda a, b: spec[(freqs >= a) & (freqs < b)].mean()
    syllabic = band(3, 8) / max(band(12, 30), 1e-9)

    # Muffle test: spectral centroid, and high band vs voice band. The
    # ghost-choir version centroided around 600 Hz; a crowd has air.
    fspec = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) ** 2
    ff = np.fft.rfftfreq(len(mono), 1 / SR)
    centroid = float((fspec * ff).sum() / fspec.sum())
    e = lambda a, b: fspec[(ff >= a) & (ff < b)].sum()
    hf_db = 10 * np.log10(e(2000, 6000) / max(e(300, 800), 1e-12))

    # Crackle: clap/consonant transients per second in the 2-8 kHz band.
    sos = butter(2, [2000, 8000], "bandpass", fs=SR, output="sos")
    hi = np.abs(sosfilt(sos, mono))
    sos = butter(2, 60, "lowpass", fs=SR, output="sos")
    hi = sosfilt(sos, hi)

    # Crackle vs wash. Sparse snaps sit on near-silence, so the hi-band
    # envelope spends measurable time in brief spikes above 2x its own
    # median; a wash hovers AT its median and never spikes. Low is good
    # ONLY alongside a healthy hi/voice level, which proves the band is
    # loud-and-steady rather than absent.
    sosd = butter(2, 80, "lowpass", fs=SR, output="sos")
    denv = sosfilt(sosd, hi)
    duty = float((denv > 2 * np.median(denv)).mean())

    seam = abs(mono[0] - mono[-1])
    print(f"{name}: rms {20 * np.log10(np.sqrt(np.mean(mono ** 2))):.1f} dBFS, "
          f"centroid {centroid:.0f} Hz, hi/voice {hf_db:+.1f} dB, "
          f"hi-band spikiness {duty:.2f} (0 = steady wash), "
          f"syllabic {syllabic:.2f}, "
          f"peak {np.abs(x).max():.2f}, seam {seam:.5f}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    SECS = 28.0
    n = int(SECS * SR)

    print("rendering bed...")
    bed = np.zeros((2, n))
    for _ in range(9000):                           # chatter
        g = voice_grain(rng.uniform(.15, .9),
                        rng.uniform(300, 850), rng.uniform(1000, 2600),
                        voiced=rng.uniform(0, .45))
        scatter(bed, g, rng.lognormal(-2.1, .55), int(rng.integers(0, n)))
    # Applause as a WASH. Ninety claps a second is the density of a
    # crackling fire: distinct snaps with silence between them, which is
    # exactly what got heard as "disturbing crackling". Five hundred a
    # second at a third the level is the density of applause -- the snaps
    # fuse into texture. Levels are capped so no single clap pops out.
    for _ in range(int(SECS * 520)):
        scatter(bed, clap(), min(float(rng.lognormal(-2.6, .5)), .2),
                int(rng.integers(0, n)))
    for _ in range(3):                              # a couple of far whistles
        scatter(bed, whistle(rng.uniform(.3, .7)), .05, int(rng.integers(0, n)))
    bed = bed + 0.45 * rumble(SECS)
    bed = normalise(bed, -21.0)
    k = int(0.04 * SR)
    w = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
    bed[:, :k] = bed[:, :k] * w + bed[:, -k:] * (1 - w)
    bed = bed[:, : bed.shape[1] - k]
    measure(bed, "crowd.mp3")
    encode(bed, OUT / "crowd.mp3")

    print("rendering roar...")
    rn = int(6.0 * SR)
    roar = np.zeros((2, rn))
    for _ in range(4200):                           # the shout
        g = voice_grain(rng.uniform(.3, 1.4),
                        rng.uniform(500, 1000), rng.uniform(1100, 2400),
                        voiced=rng.uniform(.3, .7))
        at = int(abs(rng.normal(.55, .9)) * SR)
        if at < rn:
            scatter(roar, g, rng.lognormal(-1.7, .5), at)
    for _ in range(9000):                           # the applause wall
        at = int(abs(rng.normal(1.3, 1.3)) * SR)
        if at < rn:
            scatter(roar, clap(), min(float(rng.lognormal(-2.0, .5)), .3), at)
    for _ in range(5):                              # whistles in the din
        at = int(abs(rng.normal(1.0, 1.0)) * SR)
        if at < rn:
            scatter(roar, whistle(rng.uniform(.25, .6)), .08, at)
    t = np.arange(rn) / SR
    shape = np.minimum(1, t / 0.3) * np.exp(-np.maximum(0, t - 1.6) / 1.9)
    roar = normalise(roar * shape, -16.0)
    roar[:, -int(0.2 * SR):] *= np.linspace(1, 0, int(0.2 * SR))
    measure(roar, "roar.mp3 ")
    encode(roar, OUT / "roar.mp3")

    print("rendering swell...")
    sn = int(2.4 * SR)
    sw = np.zeros((2, sn))
    for _ in range(1400):                           # voices only, no claps:
        g = voice_grain(rng.uniform(.25, .9),       # the "oooh" of a chance,
                        rng.uniform(380, 820),      # not a burst of static
                        rng.uniform(950, 2100),
                        voiced=rng.uniform(.35, .7))
        at = int(abs(rng.normal(.4, .5)) * SR)
        if at < sn:
            scatter(sw, g, rng.lognormal(-1.9, .45), at)
    st = np.arange(sn) / SR
    sw = sw * (np.minimum(1, st / .3) * np.exp(-np.maximum(0, st - .9) / .55))
    sw = normalise(sw, -18.5)
    sw[:, -int(.15 * SR):] *= np.linspace(1, 0, int(.15 * SR))
    measure(sw, "swell.mp3")
    encode(sw, OUT / "swell.mp3")

    for f in sorted(OUT.glob("*.mp3")):
        print(f"{f.relative_to(OUT.parent.parent)}  {f.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
