"""Compose the bundled background tracks for image reels (brand/music/*.mp3).

Original music generated from code (chords, a soft bass and light drums), so there is no licence to
clear. Run once; the MP3s are committed. Replace or add your own MP3s in brand/music/ (any file there is
used; you are responsible for its rights).

    python scripts/make_music.py            # writes brand/music/{calm,focus,upbeat}.mp3
"""
from __future__ import annotations

import subprocess
import sys
import tempfile
import wave
from pathlib import Path

import numpy as np

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "brand" / "music"

# name: (bpm, chord progression as MIDI root+intervals, drum pattern per 16th: k=kick, s=snare, h=hat)
TRACKS = {
    "calm":   (72,  [(57, (0, 3, 7, 10)), (53, (0, 4, 7, 11)), (60, (0, 4, 7, 11)), (55, (0, 4, 7, 10))],
               "k...h...s...h..." ),
    "focus":  (90,  [(50, (0, 3, 7, 10)), (55, (0, 3, 7, 10)), (58, (0, 4, 7, 11)), (53, (0, 4, 7, 11))],
               "k.h.h.h.s.h.h.hk"),
    "upbeat": (112, [(60, (0, 4, 7, 11)), (57, (0, 3, 7, 10)), (53, (0, 4, 7, 11)), (55, (0, 4, 7, 10))],
               "k.h.s.h.k.hks.h."),
}
BARS = 8   # a seamless loop; the image reel loops it to its length


def hz(midi: float) -> float:
    return 440.0 * 2 ** ((midi - 69) / 12)


def env(n: int, attack: float, release: float) -> np.ndarray:
    a, r = max(1, int(attack * SR)), max(1, int(release * SR))
    e = np.ones(n)
    e[:a] = np.linspace(0, 1, a)
    e[-r:] *= np.linspace(1, 0, r)
    return e


def pad(freqs: list[float], n: int, rng: np.random.Generator) -> np.ndarray:
    t = np.arange(n) / SR
    out = np.zeros(n)
    for f in freqs:
        for detune in (-0.12, 0.0, 0.12):                    # slight chorus, warm
            fr = f * 2 ** (detune / 12)
            out += np.sin(2 * np.pi * fr * t + rng.uniform(0, 6.28)) + 0.3 * np.sin(4 * np.pi * fr * t)
    return out / (len(freqs) * 3) * env(n, 0.4, 0.6)


def bass(f: float, n: int) -> np.ndarray:
    t = np.arange(n) / SR
    return (np.sin(2 * np.pi * f * t) + 0.25 * np.sin(4 * np.pi * f * t)) * env(n, 0.01, 0.3)


def drum(kind: str, rng: np.random.Generator) -> np.ndarray:
    if kind == "k":
        n = int(0.35 * SR); t = np.arange(n) / SR
        return np.sin(2 * np.pi * (45 + 80 * np.exp(-t * 30)) * t) * np.exp(-t * 9) * 0.9
    if kind == "s":
        n = int(0.2 * SR); t = np.arange(n) / SR
        return (rng.normal(0, 1, n) * 0.5 + np.sin(2 * np.pi * 190 * t)) * np.exp(-t * 22) * 0.35
    n = int(0.05 * SR); t = np.arange(n) / SR                 # hat: high, filtered noise
    noise = rng.normal(0, 1, n)
    return np.diff(noise, prepend=0) * np.exp(-t * 90) * 0.12


def compose(bpm: int, chords: list, pattern: str, seed: int) -> np.ndarray:
    rng = np.random.default_rng(seed)
    beat = 60 / bpm
    bar = int(4 * beat * SR)
    mix = np.zeros(bar * BARS + SR)
    for b in range(BARS):
        root, iv = chords[b % len(chords)]
        start = b * bar
        mix[start:start + bar] += 0.33 * pad([hz(root + i) for i in iv], bar, rng)
        for step in range(4):                                # bass on each beat, root then fifth
            note = root - 24 + (7 if step == 2 else 0)
            s = start + int(step * beat * SR)
            seg = bass(hz(note), int(beat * SR * 0.9))
            mix[s:s + len(seg)] += 0.28 * seg
        for i, ch in enumerate(pattern):                     # drums on 16ths
            if ch == ".":
                continue
            hit = drum(ch, rng)
            s = start + int(i * beat / 4 * SR)
            mix[s:s + len(hit)] += hit[: len(mix) - s]
    mix = mix[: bar * BARS]
    # soft low-pass (one-pole) for a warm, background feel, then normalise to -3 dBFS
    y = np.empty_like(mix); acc = 0.0
    for i, x in enumerate(mix):
        acc += 0.35 * (x - acc); y[i] = acc
    return y / np.max(np.abs(y)) * 0.7


def write_mp3(samples: np.ndarray, path: Path) -> None:
    with tempfile.TemporaryDirectory() as d:
        wav = Path(d) / "t.wav"
        with wave.open(str(wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR)
            w.writeframes((samples * 32767).astype("<i2").tobytes())
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(wav), "-ac", "2",
                        "-codec:a", "libmp3lame", "-b:a", "128k", str(path)], check=True)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    for i, (name, (bpm, chords, pattern)) in enumerate(TRACKS.items()):
        path = OUT / f"{name}.mp3"
        write_mp3(compose(bpm, chords, pattern, seed=i), path)
        print(f"{path.relative_to(OUT.parent.parent)}  {bpm} bpm  {path.stat().st_size // 1024} KB")
    return 0


if __name__ == "__main__":
    sys.exit(main())
