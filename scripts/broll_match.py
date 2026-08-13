#!/usr/bin/env python3
"""按剪好字幕自動提議 B-roll 時段，再由 code 硬性守住節奏規則。

Usage:
    broll_match.py <work_dir> --index <broll_index.json>
                   [-o <broll_plan.json>] [--srt <subtitles.srt>]

broll_plan.json schema：
    {"version": 1, "video_duration": 60.0, "broll_dir": "../broll",
     "rules": {"max_coverage": 0.4, ...},
     "slots": [{"start": 8.0, "end": 11.0, "file": "clip.mp4",
                "reason": "...", "confidence": 0.8,
                "has_small_text": false, "orientation": "landscape"}],
     "dropped_slots": [{"slot": {...}, "reason": "...",
                        "kept_as": {...}}]}

dropped_slots 會記低完整剔除，同埋被裁過但仍保留嘅原提議；後者有 kept_as。
人手覆核／修改 slots 後，先交俾 render_broll.py。
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from kit_config import CONFIG
from gemini_key import resolve_gemini_key

MODEL = "gemini-2.5-flash"
MIN_GAP = 2.0


def srt_seconds(value: str) -> float:
    hours, minutes, rest = value.replace(",", ".").split(":")
    return int(hours) * 3600 + int(minutes) * 60 + float(rest)


def parse_srt(path: Path) -> list[dict]:
    entries = []
    blocks = re.split(r"\n\s*\n", path.read_text(encoding="utf-8").strip())
    for block in blocks:
        lines = block.strip().splitlines()
        if len(lines) < 3 or "-->" not in lines[1]:
            continue
        start, end = (part.strip() for part in lines[1].split("-->", 1))
        try:
            entries.append({"start": round(srt_seconds(start), 3),
                            "end": round(srt_seconds(end), 3),
                            "text": " ".join(lines[2:]).strip()})
        except (TypeError, ValueError):
            continue
    return entries


def probe_duration(path: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=noprint_wrappers=1:nokey=1", str(path)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


def ask_gemini(client, timeline: list[dict], items: list[dict]) -> list[dict]:
    from google.genai.types import GenerateContentConfig

    prompt = f"""你係廣東話短片 B-roll 配對員。根據剪好版字幕時間軸，同素材描述，
提議少量、最有幫助嘅全畫面 B-roll。唔好遮住開場 hook 同結尾 CTA；冇好 match 就留白。

字幕時間軸：
{json.dumps(timeline, ensure_ascii=False)}

B-roll 素材：
{json.dumps([{'file': i.get('file'), 'description': i.get('description'), 'tags': i.get('tags'), 'orientation': i.get('orientation'), 'has_small_text': i.get('has_small_text')} for i in items], ensure_ascii=False)}

輸出 slots，每項要有 start、end、file、reason、confidence（0 至 1）。只輸出 JSON。"""
    last = None
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=prompt,
                config=GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {"slots": {
                            "type": "ARRAY",
                            "items": {
                                "type": "OBJECT",
                                "properties": {
                                    "start": {"type": "NUMBER"}, "end": {"type": "NUMBER"},
                                    "file": {"type": "STRING"}, "reason": {"type": "STRING"},
                                    "confidence": {"type": "NUMBER"},
                                },
                                "required": ["start", "end", "file", "reason", "confidence"],
                            },
                        }},
                        "required": ["slots"],
                    },
                ),
            )
            return json.loads(response.text).get("slots", [])
        except Exception as exc:
            last = exc
            print(f"{MODEL} attempt {attempt} fail: {exc}", file=sys.stderr)
    raise last


def enforce_rules(proposals: list[dict], items: list[dict], duration: float,
                  rules: dict) -> tuple[list[dict], list[dict]]:
    by_file = {item.get("file"): item for item in items}
    kept = []
    dropped = []
    coverage = 0.0
    budget = max(0.0, duration * rules["max_coverage"])
    window_start = rules["lead_protect"]
    window_end = max(window_start, duration - rules["tail_protect"])

    def sort_key(slot: dict) -> tuple[float, float]:
        try:
            return float(slot.get("start", 0)), -float(slot.get("confidence", 0))
        except (TypeError, ValueError, AttributeError):
            return 0.0, 0.0

    for raw in sorted(proposals, key=sort_key):
        if not isinstance(raw, dict):
            dropped.append({"slot": raw, "reason": "格式唔係 object"})
            continue
        reasons = []
        try:
            start, end = float(raw["start"]), float(raw["end"])
            confidence = float(raw.get("confidence", 0))
        except (KeyError, TypeError, ValueError):
            dropped.append({"slot": raw, "reason": "start、end 或 confidence 格式唔啱"})
            continue
        file = str(raw.get("file", ""))
        if confidence < rules["min_confidence"]:
            dropped.append({"slot": raw, "reason": f"confidence {confidence:.2f} 低過門檻"})
            continue
        if file not in by_file:
            dropped.append({"slot": raw, "reason": "index 入面搵唔到呢件素材"})
            continue
        if end <= start:
            dropped.append({"slot": raw, "reason": "end 要遲過 start"})
            continue

        protected_start, protected_end = start, end
        start, end = max(start, window_start), min(end, window_end)
        if start != protected_start or end != protected_end:
            reasons.append("裁走片頭／片尾保護區")
        if end - start > rules["max_slot"]:
            end = start + rules["max_slot"]
            reasons.append(f"裁到最長 {rules['max_slot']:.1f}s")
        if kept and start < kept[-1]["end"] + MIN_GAP:
            start = kept[-1]["end"] + MIN_GAP
            reasons.append(f"留返 {MIN_GAP:.1f}s 真人畫面")

        remaining = budget - coverage
        if end - start > remaining:
            end = start + max(0.0, remaining)
            reasons.append("裁到總覆蓋上限")
        if end - start < rules["min_slot"]:
            reason = "；".join(reasons + [f"裁完短過 {rules['min_slot']:.1f}s"])
            dropped.append({"slot": raw, "reason": reason})
            continue

        item = by_file[file]
        slot = {"start": round(start, 3), "end": round(end, 3), "file": file,
                "reason": str(raw.get("reason", "")).strip(),
                "confidence": round(confidence, 3),
                "has_small_text": bool(item.get("has_small_text", False)),
                "orientation": item.get("orientation", "landscape")}
        kept.append(slot)
        coverage += end - start
        if reasons:
            dropped.append({"slot": raw, "reason": "；".join(reasons), "kept_as": slot})
    return kept, dropped


def load_mock(value: str) -> list[dict]:
    text = value
    try:
        candidate = Path(value)
        if candidate.is_file():
            text = candidate.read_text(encoding="utf-8")
    except OSError:
        pass
    data = json.loads(text)
    return data.get("slots", []) if isinstance(data, dict) else data


def main() -> int:
    ap = argparse.ArgumentParser(description="按剪好字幕自動配 B-roll，先出 plan 俾你覆核")
    ap.add_argument("work_dir")
    ap.add_argument("--index", required=True, help="broll_index.py 生成嘅 JSON")
    ap.add_argument("-o", "--output", help="輸出 plan（預設 work_dir/broll_plan.json）")
    ap.add_argument("--srt", help="字幕位置；自動搵唔到先用呢個")
    ap.add_argument("--mock-response", help=argparse.SUPPRESS)
    args = ap.parse_args()

    work = Path(args.work_dir).expanduser().resolve()
    index_path = Path(args.index).expanduser().resolve()
    out = Path(args.output).expanduser().resolve() if args.output else work / "broll_plan.json"
    if not work.is_dir():
        print(f"ERROR: 搵唔到工作資料夾: {work}", file=sys.stderr)
        return 1
    if not index_path.is_file():
        print(f"ERROR: 搵唔到 B-roll index: {index_path}", file=sys.stderr)
        return 1
    try:
        index = json.loads(index_path.read_text(encoding="utf-8"))
        items = index["items"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError):
        print("ERROR: B-roll index 格式唔啱", file=sys.stderr)
        return 1

    if args.srt:
        srt = Path(args.srt).expanduser().resolve()
    else:
        found = sorted(work.glob("*_pack/*_subtitles.srt"))
        srt = found[0] if found else None
    if not srt or not srt.is_file():
        print("ERROR: 自動搵唔到剪好字幕，請加 --srt 指定。", file=sys.stderr)
        return 1
    timeline = parse_srt(srt)
    if not timeline:
        print("ERROR: 字幕入面讀唔到有效時間軸", file=sys.stderr)
        return 1

    duration = max(entry["end"] for entry in timeline)
    roughs = sorted(work.glob("*_pack/*_roughcut.mp4")) + sorted(work.glob("*_roughcut.mp4"))
    if roughs:
        duration = max(duration, probe_duration(roughs[0]))

    cfg = CONFIG.get("broll", {})
    try:
        rules = {
            "max_coverage": float(cfg.get("max_coverage", 0.40)),
            "min_slot": float(cfg.get("min_slot", 1.5)),
            "max_slot": float(cfg.get("max_slot", 6.0)),
            "lead_protect": float(cfg.get("lead_protect", 3.0)),
            "tail_protect": float(cfg.get("tail_protect", 5.0)),
            "min_confidence": float(cfg.get("min_confidence", 0.6)),
            "min_gap": MIN_GAP,
        }
    except (TypeError, ValueError):
        print("ERROR: config broll 數值格式唔啱", file=sys.stderr)
        return 1
    if not (0 <= rules["max_coverage"] <= 1
            and 0 < rules["min_slot"] <= rules["max_slot"]
            and rules["lead_protect"] >= 0 and rules["tail_protect"] >= 0
            and 0 <= rules["min_confidence"] <= 1):
        print("ERROR: config broll 嘅覆蓋、時長、保護區或 confidence 數值唔合理", file=sys.stderr)
        return 1

    if args.mock_response is not None:
        try:
            proposals = load_mock(args.mock_response)
        except (OSError, json.JSONDecodeError, TypeError) as exc:
            print(f"ERROR: mock JSON 讀唔到: {exc}", file=sys.stderr)
            return 1
        model = "mock"
    else:
        api_key, _key_env = resolve_gemini_key()
        if not api_key:
            print("ERROR: 冇 GEMINI_API_KEY／GOOGLE_API_KEY，B-roll 自動配對要 Gemini 先做到。", file=sys.stderr)
            return 2
        try:
            from google import genai
        except ImportError:
            print("ERROR: 未裝 google-genai，先跟 SETUP 裝好現有 requirements。", file=sys.stderr)
            return 1
        client = genai.Client(api_key=api_key, http_options={"timeout": 120_000})
        try:
            proposals = ask_gemini(client, timeline, items)
        except Exception as exc:
            print(f"ERROR: Gemini 配對失敗: {exc}", file=sys.stderr)
            return 1
        model = MODEL

    slots, dropped = enforce_rules(proposals, items, duration, rules)
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = {
        "version": 1,
        "model": model,
        "video_duration": round(duration, 3),
        "srt": os.path.relpath(srt, out.parent),
        "broll_dir": os.path.relpath(index_path.parent, out.parent),
        "rules": rules,
        "slots": slots,
        "dropped_slots": dropped,
    }
    out.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    coverage = sum(slot["end"] - slot["start"] for slot in slots)
    print(f"寫好 {out} — 留 {len(slots)} 段／{coverage:.1f}s，記低 {len(dropped)} 個裁剪或剔除")
    print("未 render，先覆核 broll_plan.json；啱先交俾 render_broll.py。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
