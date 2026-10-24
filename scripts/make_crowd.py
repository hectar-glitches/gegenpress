"""Render the crowd, offline, from nothing.

This file is an argument that has been had four times, and each round was
settled by a different instrument:

  v1  realtime bandpassed noise        "wind"            (ears)
  v2  granular, narrow vowel formants  "ghost choir"     (ears)
  v3  bright: claps, consonants, air   "shrieks"         (spectrogram: the
      whistles, plus a 2-6kHz field as loud as the voices)
  v4  tilted, whistle-free             "old-TV static"   (the bed was
      texturally UNIFORM: dry, stationary, mostly unvoiced)

Static is what uniformity sounds like. A real crowd has structure at
every timescale, and v5 adds the three kinds v4 lacked:

  PITCH   grains are now mostly voiced, like swell.mp3 -- the one render
          that has passed the ear test -- not mostly noise
  WAVES   the level breathes over 4-10 second swells (integer cycles per
          loop, so the seam survives); a crowd is never the same loudness
          two moments running
  A ROOM  everything is placed in a synthetic stadium: a 2-second
          decaying-noise impulse response, applied to the loop by
          CIRCULAR convolution so the reverb itself wraps seamlessly

Seeds are per-section, so re-rendering one file can never silently change
another. swell.mp3 is only rendered if missing: the shipped file was
blessed by ear and stays byte-identical.

All of it ours, no third-party audio anywhere:

  docs/audio/crowd.mp3   seamless ~28s bed
  docs/audio/roar.mp3    ~8s goal roar (reverb tail included)
  docs/audio/swell.mp3   ~2.4s "oooh" for a chance (unchanged)

Run: python scripts/make_crowd.py        (writes docs/audio/, prints the
                                          measurements that define done)
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

import numpy as np
from scipy.signal import butter, fftconvolve, sosfilt

SR = 44100
rng = np.random.default_rng(2026)      # reassigned per section in main()

OUT = pathlib.Path(__file__).resolve().parent.parent / "docs" / "audio"


def voice_grain(dur: float, f1: float, f2: float, voiced: float) -> np.ndarray:
    """One short utterance: three WIDE formants (narrow ones whistle),
    usually a consonant burst at the onset, syllabic movement."""
    n = int(dur * SR)
    t = np.arange(n) / SR
    src = rng.standard_normal(n) * 0.6
    if voiced > 0:
        f0 = rng.uniform(100, 280)
        ph = 2 * np.pi * f0 * t * (1 + 0.02 * np.sin(2 * np.pi * 5.3 * t))
        buzz = (np.sin(ph) + .5 * np.sin(2 * ph + .7) + .25 * np.sin(3 * ph + 1.9))
        src = src * (1 - voiced * .8) + buzz * voiced * 0.45
    out = np.zeros(n)
    f3 = rng.uniform(2400, 3400)
    for fc, bw, w in ((f1, 180, 1.0), (f2, 300, 0.6), (f3, 500, 0.3)):
        sos = butter(2, [max(60, fc - bw), fc + bw], "bandpass", fs=SR, output="sos")
        out += w * sosfilt(sos, src)
    if rng.random() < 0.5:
        cn = int(rng.uniform(.02, .07) * SR)
        if cn < n:
            sos = butter(2, [2000, 5600], "bandpass", fs=SR, output="sos")
            burst = sosfilt(sos, rng.standard_normal(cn))
            out[:cn] += burst * rng.uniform(.3, .65) * np.linspace(1, 0, cn)
    syl = rng.uniform(3, 8)
    env = (np.sin(np.pi * np.minimum(1, t / dur)) ** 1.2
           * (0.55 + 0.45 * np.sin(2 * np.pi * syl * t + rng.uniform(0, 6))))
    return out * env


def clap() -> np.ndarray:
    n = int(rng.uniform(.008, .02) * SR)
    sos = butter(2, [800, 4200], "bandpass", fs=SR, output="sos")
    c = sosfilt(sos, rng.standard_normal(n))
    return c * np.exp(-np.arange(n) / (n * rng.uniform(.25, .5)))


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


def tilt(x: np.ndarray, mix: float) -> np.ndarray:
    """Distance: keep the voices, lose the sizzle."""
    sos = butter(1, 1600, "lowpass", fs=SR, output="sos")
    low = np.stack([sosfilt(sos, x[0]), sosfilt(sos, x[1])])
    return x * (1 - mix) + low * mix


def stadium_ir(secs: float = 2.4, rt60: float = 2.0) -> np.ndarray:
    """A bowl of concrete and air: exponentially decaying noise with the
    top damped, decorrelated left/right. Unit energy per channel, so the
    wet level tracks the dry."""
    irng = np.random.default_rng(2030)
    n = int(secs * SR)
    t = np.arange(n) / SR
    ir = np.stack([irng.standard_normal(n), irng.standard_normal(n)])
    ir *= np.exp(-t / (rt60 / 6.91))
    sos = butter(1, 2600, "lowpass", fs=SR, output="sos")
    ir = np.stack([sosfilt(sos, ir[0]), sosfilt(sos, ir[1])])
    return ir / np.sqrt((ir ** 2).sum(axis=1, keepdims=True))


def reverb_loop(x: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    """CIRCULAR convolution: the reverb of the loop's end spills into its
    start, exactly as if the crowd had been murmuring forever. The seam
    stays seamless by construction."""
    n = x.shape[1]
    pad = np.pad(ir, ((0, 0), (0, n - ir.shape[1])))
    w = np.fft.irfft(np.fft.rfft(x, axis=1) * np.fft.rfft(pad, axis=1), n=n, axis=1)
    return (1 - wet) * x + wet * w


def reverb_oneshot(x: np.ndarray, ir: np.ndarray, wet: float) -> np.ndarray:
    out = np.stack([fftconvolve(x[c], ir[c]) for c in (0, 1)])
    dry = np.pad(x, ((0, 0), (0, out.shape[1] - x.shape[1])))
    return (1 - wet) * dry + wet * out


def waves(n: int, parts=((3, .20), (7, .13), (13, .08))) -> np.ndarray:
    """The slow breathing of a crowd: a few sinusoids at whole numbers of
    cycles per loop (so the seam survives), summing to swells of several
    seconds. Stationarity is what static IS; this removes it."""
    t = np.arange(n) / n
    g = np.ones(n)
    for cycles, depth in parts:
        g += depth * np.sin(2 * np.pi * cycles * t + rng.uniform(0, 6))
    return g


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
    return np.tanh(x / .85) * .85          # soft saturation, never a clip


def encode(x: np.ndarray, path: pathlib.Path) -> None:
    raw = (x.T * 32767).astype("<i2").tobytes()
    subprocess.run(
        ["ffmpeg", "-y", "-loglevel", "error",
         "-f", "s16le", "-ar", str(SR), "-ac", "2", "-i", "-",
         "-c:a", "libmp3lame", "-b:a", "160k", str(path)],
        input=raw, check=True)


def measure(x: np.ndarray, name: str) -> None:
    mono = x.mean(axis=0)
    env = np.abs(mono)
    sos = butter(2, 30, "lowpass", fs=SR, output="sos")
    env = sosfilt(sos, env)[:: SR // 200]
    env = env - env.mean()
    spec = np.abs(np.fft.rfft(env * np.hanning(len(env))))
    freqs = np.fft.rfftfreq(len(env), 1 / 200)
    band = lambda a, b: spec[(freqs >= a) & (freqs < b)].mean()
    syllabic = band(3, 8) / max(band(12, 30), 1e-9)

    fspec = np.abs(np.fft.rfft(mono * np.hanning(len(mono)))) ** 2
    ff = np.fft.rfftfreq(len(mono), 1 / SR)
    centroid = float((fspec * ff).sum() / fspec.sum())
    e = lambda a, b: fspec[(ff >= a) & (ff < b)].sum()
    hf_db = 10 * np.log10(e(2000, 6000) / max(e(300, 800), 1e-12))

    # Anti-static: how much the loudness BREATHES across the file.
    # Static is stationary (CV near zero); a crowd comes in waves.
    w = SR
    wrms = np.sqrt((mono[: len(mono) // w * w].reshape(-1, w) ** 2).mean(1))
    macro_cv = float(wrms.std() / wrms.mean()) if len(wrms) > 3 else float("nan")

    seam = abs(mono[0] - mono[-1])
    print(f"{name}: rms {20 * np.log10(np.sqrt(np.mean(mono ** 2))):.1f} dBFS, "
          f"centroid {centroid:.0f} Hz, hi/voice {hf_db:+.1f} dB, "
          f"macro-wave CV {macro_cv:.3f}, syllabic {syllabic:.2f}, "
          f"peak {np.abs(x).max():.2f}, seam {seam:.5f}")


def main() -> int:
    global rng
    OUT.mkdir(parents=True, exist_ok=True)
    SECS = 28.0
    n = int(SECS * SR)
    ir = stadium_ir()

    print("rendering bed...")
    rng = np.random.default_rng(2026)
    bed = np.zeros((2, n))
    for _ in range(9000):                           # chatter -- mostly VOICED
        g = voice_grain(rng.uniform(.15, .9),       # now: pitch is what reads
                        rng.uniform(300, 850),      # as human, and unvoiced
                        rng.uniform(1000, 2600),    # grain wash reads as static
                        voiced=rng.uniform(.3, .7))
        scatter(bed, g, rng.lognormal(-2.1, .55), int(rng.integers(0, n)))
    for _ in range(int(SECS * 520)):                # applause as a wash
        scatter(bed, clap(), min(float(rng.lognormal(-2.6, .5)), .14),
                int(rng.integers(0, n)))
    bed *= waves(n)                                 # the crowd breathes
    bed = tilt(bed, .5)
    bed = reverb_loop(bed, ir, wet=.45)             # put it in a stadium
    bed = bed + 0.4 * rumble(SECS)
    bed = normalise(bed, -21.0)
    k = int(0.04 * SR)
    w = np.sin(np.linspace(0, np.pi / 2, k)) ** 2
    bed[:, :k] = bed[:, :k] * w + bed[:, -k:] * (1 - w)
    bed = bed[:, : bed.shape[1] - k]
    measure(bed, "crowd.mp3")
    encode(bed, OUT / "crowd.mp3")

    print("rendering roar...")
    rng = np.random.default_rng(2027)
    rn = int(6.0 * SR)
    roar = np.zeros((2, rn))
    for _ in range(4200):
        g = voice_grain(rng.uniform(.3, 1.4),
                        rng.uniform(500, 1000), rng.uniform(1100, 2400),
                        voiced=rng.uniform(.3, .7))
        at = int(abs(rng.normal(.55, .9)) * SR)
        if at < rn:
            scatter(roar, g, rng.lognormal(-1.7, .5), at)
    for _ in range(9000):
        at = int(abs(rng.normal(1.3, 1.3)) * SR)
        if at < rn:
            scatter(roar, clap(), min(float(rng.lognormal(-2.0, .5)), .3), at)
    t = np.arange(rn) / SR
    shape = np.minimum(1, t / 0.3) * np.exp(-np.maximum(0, t - 1.6) / 1.9)
    roar = tilt(roar, .35) * shape
    roar = reverb_oneshot(roar, ir, wet=.4)         # the roar fills the bowl
    roar = normalise(roar, -16.5)
    roar[:, -int(0.3 * SR):] *= np.linspace(1, 0, int(0.3 * SR))
    measure(roar, "roar.mp3 ")
    encode(roar, OUT / "roar.mp3")

    # swell.mp3 passed the ear test as a FILE, so the file is the spec:
    # it is rendered only if missing. (The shipped one came from the
    # pre-split shared RNG sequence and is not bit-reproducible here.)
    if not (OUT / "swell.mp3").exists():
        print("rendering swell (missing)...")
        rng = np.random.default_rng(2028)
        sn = int(2.4 * SR)
        sw = np.zeros((2, sn))
        for _ in range(1400):
            g = voice_grain(rng.uniform(.25, .9),
                            rng.uniform(380, 820), rng.uniform(950, 2100),
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
