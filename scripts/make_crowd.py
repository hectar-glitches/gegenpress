"""Render the crowd, offline, from nothing.

The first crowd was three bandpassed noise loops shaped in real time, and
it sounded like what it was: wind. A crowd is not filtered static -- it is
tens of thousands of short voiced sounds overlapping, which is a granular
texture, and granular synthesis is an offline job.

Two files come out of this, both ours, no third-party audio anywhere:

  docs/audio/crowd.mp3   a seamless ~28s murmur loop: ~9,000 chatter
                         grains, each a noise burst pushed through two
                         vocal formants with syllabic (3-8 Hz) amplitude
                         movement, panned across the stand, over a low
                         stadium rumble
  docs/audio/roar.mp3    a ~6s one-shot: the same grains, denser, louder,
                         formants shifted toward open-mouth vowels, with
                         a fast swell and a long decay

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


def formant_grain(dur: float, f1: float, f2: float, voiced: float) -> np.ndarray:
    """One short utterance: noise (and a touch of buzz) through two
    vocal-tract resonances, with a syllabic envelope."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    src = rng.standard_normal(n) * 0.6
    if voiced > 0:
        f0 = rng.uniform(95, 260)                      # a speaking pitch
        buzz = np.sign(np.sin(2 * np.pi * f0 * t + rng.uniform(0, 6)))
        src = src * (1 - voiced) + buzz * voiced * 0.5
    out = np.zeros(n)
    for fc, bw, w in ((f1, 110, 1.0), (f2, 160, 0.55)):
        sos = butter(2, [max(60, fc - bw), fc + bw], "bandpass", fs=SR, output="sos")
        out += w * sosfilt(sos, src)
    # Syllables: a few amplitude humps across the grain.
    syl = rng.uniform(3, 8)
    env = (np.sin(np.pi * np.minimum(1, t / dur)) ** 1.5
           * (0.55 + 0.45 * np.sin(2 * np.pi * syl * t + rng.uniform(0, 6))))
    return out * env


def chatter_bed(secs: float, grains: int, spread: float = 1.0) -> np.ndarray:
    """Overlap-add a crowd of grains into a stereo bed."""
    n = int(secs * SR)
    bed = np.zeros((2, n))
    for _ in range(grains):
        dur = rng.uniform(0.25, 1.1)
        g = formant_grain(dur, rng.uniform(280, 820), rng.uniform(900, 2600),
                          voiced=rng.uniform(0, 0.5))
        amp = rng.lognormal(mean=-2.1, sigma=0.55)
        pan = rng.uniform(0.5 - 0.5 * spread, 0.5 + 0.5 * spread)
        at = rng.integers(0, n)
        m = min(len(g), n - at)
        bed[0, at:at + m] += g[:m] * amp * (1 - pan)
        bed[1, at:at + m] += g[:m] * amp * pan
        if m < len(g):                                  # wrap: keeps the loop seamless
            r = len(g) - m
            bed[0, :r] += g[m:] * amp * (1 - pan)
            bed[1, :r] += g[m:] * amp * pan
    return bed


def rumble(secs: float) -> np.ndarray:
    """The low stadium bed under everything."""
    n = int(secs * SR)
    sos = butter(2, 180, "lowpass", fs=SR, output="sos")
    r = np.stack([sosfilt(sos, rng.standard_normal(n)),
                  sosfilt(sos, rng.standard_normal(n))])
    # Fade the join so the loop point is silent in this layer too.
    k = int(0.5 * SR)
    w = np.linspace(0, 1, k)
    r[:, :k] = r[:, :k] * w + r[:, -k:] * (1 - w)
    r[:, -k:] = r[:, :k][:, ::-1] * 0 + r[:, -k:] * 0  # tail unused after wrap
    return np.concatenate([r[:, :n - k], r[:, :k]], axis=1)[:, :n]


def normalise(x: np.ndarray, rms_db: float) -> np.ndarray:
    rms = np.sqrt(np.mean(x ** 2))
    x = x * (10 ** (rms_db / 20) / max(rms, 1e-9))
    return np.clip(x, -0.99, 0.99)


def encode(x: np.ndarray, path: pathlib.Path) -> None:
    raw = (x.T * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
         "-c:a", "libmp3lame", "-b:a", "128k", str(path)],
        input=raw, check=True)


def measure(x: np.ndarray, name: str) -> None:
    mono = x.mean(axis=0)
    # Modulation spectrum: a crowd chatters at syllable rate. Filtered
    # static has no such peak; speech-like texture does.
    env = np.abs(mono)
    sos = butter(2, 30, "lowpass", fs=SR, output="sos")
    env = sosfilt(sos, env)[:: SR // 200]               # 200 Hz envelope
    env = env - env.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    freqs = np.fft.rfftfreq(len(env), 1 / 200)
    band = lambda a, b: spec[(freqs >= a) & (freqs < b)].mean()
    syllabic = band(3, 8) / max(band(12, 30), 1e-9)
    seam = abs(mono[0] - mono[-1])
    print(f"{name}: rms {20 * np.log10(np.sqrt(np.mean(mono ** 2))):.1f} dBFS, "
          f"syllabic/flutter energy ratio {syllabic:.2f} (chatter if > 1), "
          f"loop seam delta {seam:.5f}")


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)

    print("rendering bed (~9,000 grains)...")
    bed = chatter_bed(28.0, 9000) + 0.8 * rumble(28.0)
    bed = normalise(bed, -21.0)
    # Belt and braces on the seam: a 40ms equal-power crossfade.
    k = int(0.04 * SR)
    w = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
    bed[:, :k] = bed[:, :k] * w + bed[:, -k:] * (1 - w)
    bed = bed[:, : bed.shape[1] - k]
    measure(bed, "crowd.mp3")
    encode(bed, OUT / "crowd.mp3")

    print("rendering roar (~5,000 grains)...")
    n = int(6.0 * SR)
    roar = np.zeros((2, n))
    for _ in range(5000):
        dur = rng.uniform(0.3, 1.6)
        g = formant_grain(dur, rng.uniform(500, 1000), rng.uniform(1100, 2400),
                          voiced=rng.uniform(0.3, 0.75))    # open-mouth vowels
        at = int(abs(rng.normal(0.55, 0.9)) * SR)           # bunched at the front
        if at >= n:
            continue
        m = min(len(g), n - at)
        amp = rng.lognormal(-1.7, 0.5)
        pan = rng.uniform(0.15, 0.85)
        roar[0, at:at + m] += g[:m] * amp * (1 - pan)
        roar[1, at:at + m] += g[:m] * amp * pan
    t = np.arange(n) / SR
    shape = np.minimum(1, t / 0.35) * np.exp(-np.maximum(0, t - 1.6) / 1.9)
    roar = normalise(roar * shape, -16.0)
    roar[:, -int(0.2 * SR):] *= np.linspace(1, 0, int(0.2 * SR))
    measure(roar, "roar.mp3 ")
    encode(roar, OUT / "roar.mp3")

    for f in sorted(OUT.glob("*.mp3")):
        print(f"{f.relative_to(OUT.parent.parent)}  {f.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
