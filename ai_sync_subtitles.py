import re
import json
import requests
from pathlib import Path
from sentence_transformers import SentenceTransformer, util

API_URL = "http://localhost:1234/v1/chat/completions"
MODEL_NAME = "phi-4"
HEADERS = {"Content-Type": "application/json"}

model = SentenceTransformer("paraphrase-multilingual-MiniLM-L12-v2")


def parse_srt(path: Path):
    with path.open("r", encoding="utf-8") as f:
        content = f.read().strip()
    blocks = []
    for match in re.finditer(r"(\d+)\n([\d:,]+) --> ([\d:,]+)\n(.+?)(?=\n\n|\Z)", content, re.DOTALL):
        blocks.append({
            "index": int(match.group(1)),
            "start": match.group(2),
            "end": match.group(3),
            "text": match.group(4).replace("\n", " ").strip()
        })
    return blocks


def write_srt(blocks, path: Path):
    with path.open("w", encoding="utf-8") as f:
        for i, b in enumerate(blocks, 1):
            f.write(f"{i}\n{b['start']} --> {b['end']}\n{b['text']}\n\n")


def call_llm_text(system_prompt: str, user_prompt: str, temperature: float = 0.2, max_tokens: int = 100) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        "temperature": temperature,
        "max_tokens": max_tokens
    }
    try:
        r = requests.post(API_URL, json=payload, headers=HEADERS, timeout=60)
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as e:
        print(f"\u26a0\ufe0f LLM call failed: {e}")
        return ""


def ask_lm_equivalence(ar_text, en_text):
    system_prompt = (
        "You're a subtitle reviewer. Compare the two lines and judge if they express the same core meaning "
        "even if they have extra words, emotional tone, or different sentence structure."
    )
    user_prompt = (
        f"Arabic: {ar_text}\n"
        f"English: {en_text}\n\n"
        "Answer YES or NO only. Say YES if they mostly mean the same thing."
    )
    response = call_llm_text(system_prompt, user_prompt)
    return response.upper().startswith("YES")


def semantic_fallback(ar_text, en_text):
    try:
        a = model.encode(ar_text, convert_to_tensor=True)
        b = model.encode(en_text, convert_to_tensor=True)
        score = float(util.cos_sim(a, b)[0][0])
        return score >= 0.7
    except:
        return False


def is_equivalent(ar_text, en_text):
    if ask_lm_equivalence(ar_text, en_text):
        return True
    return semantic_fallback(ar_text, en_text)


def srt_to_ms(srt_time):
    h, m, s = srt_time.split(":")
    s, ms = s.split(",")
    return (int(h) * 3600 + int(m) * 60 + int(s)) * 1000 + int(ms)


def ms_to_srt(ms):
    h = ms // 3600000
    m = (ms % 3600000) // 60000
    s = (ms % 60000) // 1000
    ms = ms % 1000
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def smart_sync_subs(en_path, ar_path, output_path):
    en_blocks = parse_srt(en_path)
    ar_blocks = parse_srt(ar_path)

    # Start from the middle (minute 10 = 600,000ms)
    en_start_index = next((i for i, b in enumerate(en_blocks) if srt_to_ms(b['start']) >= 600000), 0)
    ar_start_index = next((i for i, b in enumerate(ar_blocks) if srt_to_ms(b['start']) >= 600000), 0)

    sync_found = False
    for ai in range(ar_start_index, len(ar_blocks) - 5):
        for ei in range(en_start_index, len(en_blocks) - 5):
            score = 0
            for offset in range(5):
                ar_text = ar_blocks[ai + offset]['text']
                en_text = en_blocks[ei + offset]['text']
                if is_equivalent(ar_text, en_text):
                    score += 1
            if score >= 3:
                print(f"\u2705 Sync anchor found: AR[{ai}] \u2194 EN[{ei}]")
                sync_found = True
                break
        if sync_found:
            break

    if not sync_found:
        print("\u274c No sync point found.")
        return

    # Compute shift and scaling
    ar_anchor_time = srt_to_ms(ar_blocks[ai]['start'])
    en_anchor_time = srt_to_ms(en_blocks[ei]['start'])
    offset = en_anchor_time - ar_anchor_time

    synced_blocks = []
    for block in ar_blocks:
        new_start = srt_to_ms(block['start']) + offset
        new_end = srt_to_ms(block['end']) + offset
        if new_start < 0 or new_end < 0:
            continue
        synced_blocks.append({
            'start': ms_to_srt(new_start),
            'end': ms_to_srt(new_end),
            'text': block['text']
        })

    write_srt(synced_blocks, output_path)
    print(f"\u2705 Synced subtitle saved to: {output_path}")
