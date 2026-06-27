#!/usr/bin/env python3
"""Pack word-level transcript → phrase-level markdown 俾 LLM 出 EDL。

Usage:
    pack_transcript.py <transcript.json> [-o takes_packed.md]

支援兩種 input：transcribe.py 嘅 normalized shape（top-level words[]），
或 whisper CLI raw json（segments[].words[]，word key 係 "word"）。

Output 每行一個 phrase（inter-word gap ≥ PHRASE_GAP 斷行）：
    [012.34-015.67] 句子內容
phrase 之間 gap ≥ MARK_GAP 加標記行（take 邊界最強 signal）：
    ⏸ gap 1.6s
"""
import argparse
import json
import sys
from pathlib import Path

PHRASE_GAP = 0.5   # inter-word silence ≥ 呢個值 → 斷 phrase
MARK_GAP = 0.8     # phrase 之間 gap ≥ 呢個值 → 插 ⏸ 標記行


def load_words(path: Path) -> list[dict]:
    data = json.loads(path.read_text())
    if "words" in data and data["words"]:          # normalized shape
        return data["words"]
    words = []                                      # whisper CLI raw json
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            t = (w.get("text") or w.get("word", "")).strip()
            if t:
                words.append({"start": w["start"], "end": w["end"], "text": t})
    return words


def pack(words: list[dict]) -> str:
    lines = []
    phrase: list[dict] = []

    def flush():
        if phrase:
            text = "".join(w["text"] for w in phrase)
            lines.append(f"[{phrase[0]['start']:07.2f}-{phrase[-1]['end']:07.2f}] {text}")
            phrase.clear()

    prev_end = None
    for w in words:
        if prev_end is not None:
            gap = w["start"] - prev_end
            if gap >= PHRASE_GAP:
                flush()
                if gap >= MARK_GAP:
                    lines.append(f"⏸ gap {gap:.1f}s")
        phrase.append(w)
        prev_end = w["end"]
    flush()
    return "\n".join(lines) + "\n"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()
    src = Path(a.transcript).expanduser()
    words = load_words(src)
    if not words:
        sys.exit("no words found in transcript（word_timestamps 冇開？）")
    out = Path(a.output) if a.output else src.parent / "takes_packed.md"
    out.write_text(pack(words))
    print(f"wrote {out} — {len(words)} words")


if __name__ == "__main__":
    main()
