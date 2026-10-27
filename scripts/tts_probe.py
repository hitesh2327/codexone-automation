"""Probe edge-tts voices for Hinglish narration: duration, speaking rate and word boundaries.

Edge TTS is blocked in some sandboxes, so this is meant to run in GitHub Actions or on a laptop.
Writes one MP3 per voice and line into --out (upload it as an artifact to listen) and prints a report.

Usage:
    python scripts/tts_probe.py --out tts_probe
"""
from __future__ import annotations

import argparse
import asyncio
import subprocess
import sys
from pathlib import Path

import edge_tts
import imageio_ffmpeg

VOICES = ["hi-IN-MadhurNeural", "hi-IN-SwaraNeural", "en-US-AndrewMultilingualNeural"]
RATE = "+6%"   # the brand base rate (src/reel_v2/render.py BASE_RATE)
LINES = [
    "सोचो, हर request सीधा database पे जाए तो क्या होगा? यहीं cache काम आता है।",
    "Binary search हर step में आधा array हटा देता है, इसलिए time O of log n है।",
    "Load balancer traffic को तीन servers में बाँटता है, और एक crash हो जाए तो बाकी संभाल लेते हैं।",
    "ऐसे और explainers के लिए follow करो Code Xone By Hitesh।",
]
ENGLISH_WPS = 75 / 27.0   # MAX_WORDS=75 fills ~27 s with the English voices at +6%


async def synth(text: str, voice: str, out: Path) -> list[tuple[str, float, float]]:
    comm = edge_tts.Communicate(text, voice, rate=RATE, boundary="WordBoundary")
    words = []
    with out.open("wb") as f:
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                f.write(chunk["data"])
            elif chunk["type"] == "WordBoundary":
                s = chunk["offset"] / 1e7
                words.append((chunk["text"], s, s + chunk["duration"] / 1e7))
    return words


def duration(path: Path) -> float:
    err = subprocess.run([imageio_ffmpeg.get_ffmpeg_exe(), "-i", str(path)], capture_output=True, text=True).stderr
    h, m, s = err.split("Duration: ")[1].split(",")[0].split(":")
    return int(h) * 3600 + int(m) * 60 + float(s)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", type=Path, default=Path("tts_probe"))
    args = ap.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    ok = True
    for voice in VOICES:
        total_words = total_secs = 0.0
        print(f"\n=== {voice} ===")
        for i, line in enumerate(LINES):
            mp3 = args.out / f"{voice}_{i}.mp3"
            try:
                words = asyncio.run(synth(line, voice, mp3))
            except Exception as e:  # noqa: BLE001 -- report every voice
                print(f"line {i}: FAILED {type(e).__name__}: {e}")
                ok = False
                continue
            d = duration(mp3)
            n = len(line.split())
            total_words += n
            total_secs += d
            print(f"line {i}: {d:.2f}s, {n} words, {n / d:.2f} w/s, boundaries={len(words)}")
            print("   " + " | ".join(w for w, _, _ in words))
        if total_secs:
            wps = total_words / total_secs
            print(f"TOTAL {voice}: {wps:.2f} w/s (English reference {ENGLISH_WPS:.2f}) "
                  f"-> words for 27 s: {int(wps * 27)}")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
