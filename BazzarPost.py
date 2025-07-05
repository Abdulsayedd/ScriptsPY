# AI Subtitle Auto-Sync for Bazarr
# Author: OpenAI ChatGPT
#
# This script synchronizes Arabic subtitles (.ar.srt) with
# English subtitles (.en.srt) using AI-based semantic matching.
# It finds a sync point based on meaning and adjusts the Arabic
# subtitle timestamps accordingly.

from __future__ import annotations

import os
import sys
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple

try:
    import openai  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    openai = None  # type: ignore


@dataclass
class SubtitleLine:
    index: int
    start: float  # seconds
    end: float  # seconds
    text: str


TIME_SEP = " --> "


def time_to_seconds(t: str) -> float:
    """Convert SRT timestamp to seconds."""
    hms, ms = t.split(',')
    h, m, s = hms.split(':')
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000.0


def seconds_to_time(s: float) -> str:
    """Convert seconds back to SRT timestamp."""
    ms = int(round((s - int(s)) * 1000))
    s = int(s)
    h = s // 3600
    s -= h * 3600
    m = s // 60
    s -= m * 60
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"


def parse_srt(path: str) -> List[SubtitleLine]:
    with open(path, encoding="utf-8-sig") as f:
        content = f.read().strip()
    entries = []
    for block in content.split("\n\n"):
        lines = block.splitlines()
        if len(lines) >= 3:
            try:
                idx = int(lines[0].strip())
            except ValueError:
                continue
            times = lines[1]
            if TIME_SEP not in times:
                continue
            start_str, end_str = times.split(TIME_SEP)
            start = time_to_seconds(start_str.strip())
            end = time_to_seconds(end_str.strip())
            text = " ".join(l.strip() for l in lines[2:])
            entries.append(SubtitleLine(idx, start, end, text))
    return entries


def format_srt(entries: List[SubtitleLine]) -> str:
    parts = []
    for i, line in enumerate(entries, start=1):
        parts.append(str(i))
        parts.append(
            f"{seconds_to_time(line.start)}{TIME_SEP}{seconds_to_time(line.end)}"
        )
        parts.append(line.text)
        parts.append("")
    return "\n".join(parts)


def _init_openai_client() -> Optional[object]:
    if openai is None:
        return None
    key = os.getenv("OPENAI_API_KEY")
    if not key:
        return None
    openai.api_key = key
    api_base = os.getenv("OPENAI_API_BASE")
    if api_base:
        openai.api_base = api_base
    return openai


def cosine_similarity(v1: List[float], v2: List[float]) -> float:
    num = sum(a * b for a, b in zip(v1, v2))
    den1 = math.sqrt(sum(a * a for a in v1))
    den2 = math.sqrt(sum(b * b for b in v2))
    if den1 == 0 or den2 == 0:
        return 0.0
    return num / (den1 * den2)


def embedding(text: str, client) -> List[float]:
    resp = client.Embedding.create(model="text-embedding-ada-002", input=text)
    return resp["data"][0]["embedding"]


def llm_match(ar: str, en: str, client, threshold: float = 0.7) -> bool:
    system = (
        "You determine if an Arabic subtitle line has the same meaning as an English "
        "subtitle line. Reply with YES or NO."
    )
    prompt = f"Arabic: {ar}\nEnglish: {en}"
    try:
        chat = client.ChatCompletion.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "system", "content": system}, {"role": "user", "content": prompt}],
            temperature=0,
        )
        content = chat["choices"][0]["message"]["content"].strip().lower()
        if content.startswith("yes"):
            return True
        # fallback to similarity
        ar_emb = embedding(ar, client)
        en_emb = embedding(en, client)
        sim = cosine_similarity(ar_emb, en_emb)
        return sim >= threshold
    except Exception:
        return False


def find_sync_point(
    eng: List[SubtitleLine], ara: List[SubtitleLine], client
) -> Optional[Tuple[int, int]]:
    mid_time = eng[len(eng) // 2].start if eng else 0
    start_idx = next(
        (i for i, s in enumerate(ara) if s.start >= mid_time), len(ara) // 2
    )
    for ai in range(start_idx, len(ara)):
        for ei, e in enumerate(eng):
            if llm_match(ara[ai].text, e.text, client):
                matches = 1
                for offset in range(1, 6):
                    if ai + offset >= len(ara) or ei + offset >= len(eng):
                        break
                    if llm_match(ara[ai + offset].text, eng[ei + offset].text, client):
                        matches += 1
                if matches >= 3:
                    return ei, ai
    return None


def compute_shift_scale(
    eng: List[SubtitleLine], ara: List[SubtitleLine], ei: int, ai: int
) -> Tuple[float, float]:
    shift = eng[ei].start - ara[ai].start
    if ei + 5 < len(eng) and ai + 5 < len(ara):
        eng_delta = eng[ei + 5].start - eng[ei].start
        ara_delta = ara[ai + 5].start - ara[ai].start
    else:
        eng_delta = eng[ei + 1].start - eng[ei].start
        ara_delta = ara[ai + 1].start - ara[ai].start
    scale = eng_delta / ara_delta if ara_delta else 1.0
    return shift, scale


def apply_sync(
    ara: List[SubtitleLine], shift: float, scale: float
) -> List[SubtitleLine]:
    synced = []
    for line in ara:
        start = line.start * scale + shift
        end = line.end * scale + shift
        synced.append(SubtitleLine(line.index, start, end, line.text))
    return synced


def main(en_path: str, ar_path: str) -> None:
    eng = parse_srt(en_path)
    ara = parse_srt(ar_path)
    client = _init_openai_client()
    if client is None:
        sys.stderr.write("OpenAI client is not configured. Set OPENAI_API_KEY.\n")
        sys.exit(1)
    sync = find_sync_point(eng, ara, client)
    if not sync:
        sys.stderr.write("Failed to find sync point.\n")
        sys.exit(1)
    ei, ai = sync
    shift, scale = compute_shift_scale(eng, ara, ei, ai)
    synced = apply_sync(ara, shift, scale)
    out_path = ar_path.replace(".ar.srt", ".ar.synced.srt")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(format_srt(synced))
    print(f"Synced subtitle saved to {out_path}")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        print("Usage: python BazzarPost.py <english.en.srt> <arabic.ar.srt>")
        sys.exit(1)
    main(sys.argv[1], sys.argv[2])
