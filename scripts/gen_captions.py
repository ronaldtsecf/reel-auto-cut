#!/usr/bin/env python3
"""
Transcript（剪好 final video 嘅 STT）→ phrase-level captions.json。

⚠️ 餵嘅係 **final video re-transcribe** 出嘅 transcript（timing 已對最終片，
含變速），唔係 source transcript。咁 timing 零估算（唔使補 pad、唔使 ÷ speed）。

文字 = whisper raw（粵→書面/簡體 drift + 機器斷句）→ **draft**。
下一步由 Claude 對 script.md ground-truth 修文字，再 gen_srt。

Usage:
    gen_captions.py <transcript.json> [-o captions.json] [--max-words 14] [--gap 0.45]

transcript.json: transcribe.py normalized shape {words:[{start,end,text}]}，
或 raw whisper {segments:[{words:[{word,start,end}]}]}（自動 flatten）。

Output: [{start, end, text}, ...]（final-video timeline）→ 餵 gen_srt --speed 1.0。
"""

import argparse
import json
from pathlib import Path


def load_words(data) -> list:
    """Normalize transcript shape → [{start, end, text}]."""
    if isinstance(data, list):
        return data
    if "words" in data and data["words"]:
        return data["words"]
    # raw whisper: flatten segments[].words
    words = []
    for seg in data.get("segments", []):
        for w in seg.get("words", []):
            t = (w.get("word") or w.get("text") or "").strip()
            if t:
                words.append({"start": w["start"], "end": w["end"], "text": t})
    return words


def group_phrases(words: list, max_chars: int, gap: float) -> list:
    """Group word list into phrase-level [{start, end, text}]。
    斷句用「顯示字數」唔用 word 數 — 中英混時 word-count 會撞英文長詞（automated/
    workflow）爆行（舊 bug：14 words 出到 37 字）。char-count 中英都準。"""
    # gap-aware：盡量喺停頓位（句邊界）斷，唔好夠字數就硬切（會撈埋上句尾+下句頭）。
    # MIN 後遇自然停頓就斷，max_chars 係最後手段硬斷。
    MIN_CHARS = 6
    GAP_BREAK = 0.14
    phrases, cur = [], []
    for i, w in enumerate(words):
        cur.append(w)
        is_last = (i == len(words) - 1)
        next_gap = (words[i + 1]["start"] - w["end"]) if not is_last else 999
        # 中文句末標點都係斷句信號
        ends_punct = w["text"].strip().endswith(("。", "?", "!", "？", "！", "."))
        ends_comma = w["text"].strip().endswith(("，", ",", "、"))
        cur_chars = sum(len(x["text"]) for x in cur)
        big_gap = next_gap >= gap                                     # 大停頓必斷
        comma_break = ends_comma and cur_chars >= MIN_CHARS           # whisper 逗號 = 語意停頓,夠長就斷
        nat_break = cur_chars >= MIN_CHARS and next_gap >= GAP_BREAK   # 夠長 + 自然停頓 → 喺句邊界斷
        # char 上限硬斷（最後手段）；但唔好斷喺英文 word 中間（whisper 將 experience tokenize 做 exper+ience）
        cur_en = w["text"].strip().isascii() and any(c.isalpha() for c in w["text"])
        next_en = (not is_last) and words[i + 1]["text"].strip().isascii() and any(c.isalpha() for c in words[i + 1]["text"])
        hard = cur_chars >= max_chars and not (cur_en and next_en)
        if ends_punct or comma_break or big_gap or nat_break or hard or is_last:
            text = "".join(x["text"] for x in cur).strip()
            if text:
                phrases.append({
                    "start": round(cur[0]["start"], 3),
                    "end": round(cur[-1]["end"], 3),
                    "text": text,
                })
            cur = []
    return phrases


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("transcript", help="final video re-transcribe 出嘅 transcript.json")
    ap.add_argument("-o", "--output", default=None, help="output captions.json path")
    ap.add_argument("--max-chars", type=int, default=15, help="每句字數上限（逗號/gap 優先斷,呢個係 fallback；英文 word 中間唔斷）")
    ap.add_argument("--gap", type=float, default=0.45, help="inter-word silence gap to break phrase (s)")
    args = ap.parse_args()

    data = json.loads(Path(args.transcript).read_text())
    words = load_words(data)
    if not words:
        print("ERROR: no words found in transcript", flush=True)
        raise SystemExit(1)

    captions = group_phrases(words, args.max_chars, args.gap)

    out = Path(args.output) if args.output else Path(args.transcript).with_name("captions.json")
    out.write_text(json.dumps(captions, ensure_ascii=False, indent=2))
    dur = captions[-1]["end"] if captions else 0
    print(f"wrote {out} — {len(captions)} captions (draft 文字，timing 對 final ~{dur:.1f}s)")
    print("⚠️ 文字係 whisper raw — Claude 下一步對 script.md 修，再跑 gen_srt --speed 1.0")


if __name__ == "__main__":
    main()
