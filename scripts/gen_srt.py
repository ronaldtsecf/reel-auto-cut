#!/usr/bin/env python3
"""Captions JSON → SRT（對應變速後 timing）。

reel-cut 出 rough cut（剪 NG + 1.05x）後，SRT timing 要對應變速後嘅片：
每個 timestamp ÷ speed。文字 = Claude 對齊 ground-truth（修 whisper drift）後嘅 captions。

Usage:
    gen_srt.py <captions.json> --speed 1.05 [-o out.srt]

captions.json: [{start, end, text}, ...]（pre-speed time，即 cut_master / source time）
或 {captions:[...]} / {segments:[...]}。
"""
import argparse
import json
from pathlib import Path


def ts(s: float) -> str:
    if s < 0:
        s = 0
    h = int(s // 3600)
    m = int(s % 3600 // 60)
    sec = int(s % 60)
    ms = int(round((s - int(s)) * 1000))
    if ms == 1000:
        sec += 1
        ms = 0
    return f"{h:02d}:{m:02d}:{sec:02d},{ms:03d}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("captions")
    ap.add_argument("--speed", type=float, default=1.0, help="rough cut 變速倍數（timing ÷ speed）")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()

    data = json.loads(Path(a.captions).read_text())
    caps = data if isinstance(data, list) else (data.get("captions") or data.get("segments") or [])
    lines, n = [], 0
    for c in caps:
        txt = c["text"].strip()
        if not txt:
            continue
        n += 1
        st, en = c["start"] / a.speed, c["end"] / a.speed
        lines.append(f"{n}\n{ts(st)} --> {ts(en)}\n{txt}\n")

    out = Path(a.output) if a.output else Path(a.captions).with_suffix(".srt")
    out.write_text("\n".join(lines))
    print(f"wrote {out} — {n} entries (speed {a.speed})")


if __name__ == "__main__":
    main()
