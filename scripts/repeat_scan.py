#!/usr/bin/env python3
"""repeat_scan.py — final/proof transcript 殘留重複掃描（deterministic，零 API）。

5-gram 全域重現 + 4-gram 近距（<15 字，fs 殘留 pattern）。qc_check ④ 同 proof_check 共用。
Usage: repeat_scan.py <transcript.json>   （exit 0 = 乾淨或只有短 run；exit 2 = 有 ≥8 字高危 run）
"""
import json
import re
import sys
from pathlib import Path


def norm_text(transcript: dict) -> str:
    ws = transcript["words"] if "words" in transcript else [
        w for s in transcript.get("segments", []) for w in s.get("words", [])]
    full = "".join((w.get("word") or w.get("text", "")) for w in ws)
    return re.sub(r"[\s,，。.?？!！、:：;；「」]", "", full)


def scan(norm: str) -> list[str]:
    """回 repeat run 文字 list（近距 4-gram 加「（近距4字）」suffix）。"""
    seen, runs = {}, []
    for i in range(len(norm) - 4):
        g = norm[i:i + 5]
        if g in seen and i - seen[g] >= 5:
            if runs and i == runs[-1][1] + 1:
                runs[-1] = (runs[-1][0], i, runs[-1][2] + g[-1])
            else:
                runs.append((i, i, g))
        else:
            seen.setdefault(g, i)
    seen4 = {}
    for i in range(len(norm) - 3):
        g = norm[i:i + 4]
        if g in seen4 and 4 <= i - seen4[g] < 15 and not any(a <= i <= b + 4 for a, b, _ in runs):
            runs.append((i, i, g + "（近距4字）"))
        seen4.setdefault(g, i)
    return [txt for _, _, txt in runs]


def main():
    import argparse
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("--allow", help="白名單檔（每行一個 substring）：判過係 intentional（refrain／疊詞）嘅 repeat，match 即降級唔算高危")
    a = ap.parse_args()
    allow = []
    if a.allow and Path(a.allow).exists():
        allow = [l.strip() for l in Path(a.allow).read_text().splitlines() if l.strip()]
    t = json.loads(Path(a.transcript).read_text())
    runs = scan(norm_text(t))
    danger = 0
    for txt in runs:
        core = txt.replace("（近距4字）", "")
        if any(w in core or core in w for w in allow):
            print(f"repeat（白名單 — 已判 intentional）：「{txt}」")
            continue
        hi = "🔴 高危" if len(core) >= 8 or txt.endswith("（近距4字）") else "留意"
        print(f"repeat（{hi}）：「{txt}」")
        if hi.startswith("🔴"):
            danger += 1
    if not runs:
        print("零殘留重複（5/4-gram 掃）")
    sys.exit(2 if danger else 0)


if __name__ == "__main__":
    main()
