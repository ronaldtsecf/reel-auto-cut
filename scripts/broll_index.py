#!/usr/bin/env python3
"""建立 B-roll 視覺索引，俾配對器按內容揀素材。

Usage:
    broll_index.py <broll_dir> [--out <broll_index.json>] [--force]

輸出 schema：
    {"version": 1, "model": "...", "items": [
      {"file": "clip.mp4", "size": 123, "mtime": 1234567890.0,
       "description": "廣東話一句", "tags": ["..."],
       "has_small_text": false,
       "orientation": "landscape|portrait|square"}
    ]}

file 永遠係相對 broll_dir 嘅檔名；cache key 係同一檔名嘅 size + mtime。
"""
from __future__ import annotations

import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

MODEL = "gemini-2.5-flash"
MEDIA_EXTS = {".mp4", ".mov", ".m4v", ".jpg", ".jpeg", ".png", ".webp"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v"}
MIME_TYPES = {
    ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".png": "image/png",
    ".webp": "image/webp",
}

PROMPT = """你會收到一張相，或者同一條 B-roll 嘅 3 張代表畫面。
請用香港廣東話描述素材，輸出 JSON：
- description：一句，講清畫面主體同動作
- tags：3 至 6 個短標籤
- has_small_text：畫面有冇細字，裁畫面後可能睇唔清嗰種
- orientation：landscape、portrait 或 square
只輸出 JSON，唔好加其他文字。"""


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def media_info(path: Path) -> tuple[int, int, float]:
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation:format=duration",
             "-of", "json", str(path)])
    try:
        data = json.loads(r.stdout)
        stream = data["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        rotation = stream.get("tags", {}).get("rotate", 0)
        for side_data in stream.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = side_data["rotation"]
                break
        if abs(int(float(rotation))) % 180 == 90:
            width, height = height, width
        return width, height, float(data.get("format", {}).get("duration") or 0)
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        raise RuntimeError(f"讀唔到素材資料: {path.name}")


def orientation_of(width: int, height: int) -> str:
    ratio = width / height
    if 0.95 <= ratio <= 1.05:
        return "square"
    return "landscape" if width > height else "portrait"


def extract_video_frames(path: Path, duration: float, tmp: Path) -> list[Path]:
    if duration <= 0:
        raise RuntimeError(f"條片冇有效時長: {path.name}")
    frames = []
    for i, fraction in enumerate((0.1, 0.5, 0.9), 1):
        out = tmp / f"frame_{i}.jpg"
        r = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{duration * fraction:.3f}",
                 "-i", str(path), "-frames:v", "1", "-q:v", "2", str(out)])
        if r.returncode != 0 or not out.exists():
            raise RuntimeError(f"抽唔到 {path.name} 第 {i} 張畫面: {r.stderr[-300:]}")
        frames.append(out)
    return frames


def ask_gemini(client, images: list[tuple[Path, str]]) -> dict:
    from google.genai.types import GenerateContentConfig

    contents = []
    for path, mime in images:
        contents.append({"inline_data": {
            "mime_type": mime,
            "data": base64.b64encode(path.read_bytes()).decode(),
        }})
    contents.append(PROMPT)
    last = None
    for attempt in (1, 2):
        try:
            response = client.models.generate_content(
                model=MODEL,
                contents=contents,
                config=GenerateContentConfig(
                    temperature=0.2,
                    response_mime_type="application/json",
                    response_schema={
                        "type": "OBJECT",
                        "properties": {
                            "description": {"type": "STRING"},
                            "tags": {"type": "ARRAY", "items": {"type": "STRING"},
                                     "minItems": 3, "maxItems": 6},
                            "has_small_text": {"type": "BOOLEAN"},
                            "orientation": {"type": "STRING",
                                            "enum": ["landscape", "portrait", "square"]},
                        },
                        "required": ["description", "tags", "has_small_text", "orientation"],
                    },
                ),
            )
            return json.loads(response.text)
        except Exception as exc:
            last = exc
            print(f"{MODEL} attempt {attempt} fail: {exc}", file=sys.stderr)
    raise last


def index_one(client, path: Path) -> dict:
    width, height, duration = media_info(path)
    if path.suffix.lower() in VIDEO_EXTS:
        with tempfile.TemporaryDirectory(prefix="broll-index-") as td:
            frames = extract_video_frames(path, duration, Path(td))
            result = ask_gemini(client, [(frame, "image/jpeg") for frame in frames])
    else:
        result = ask_gemini(client, [(path, MIME_TYPES[path.suffix.lower()])])
    tags = [str(tag).strip() for tag in result.get("tags", []) if str(tag).strip()][:6]
    if not str(result.get("description", "")).strip() or len(tags) < 3:
        raise RuntimeError("Gemini 回應欠 description 或足夠 tags")
    return {
        "description": str(result.get("description", "")).strip(),
        "tags": tags,
        "has_small_text": bool(result.get("has_small_text", False)),
        "orientation": orientation_of(width, height),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="用 Gemini 幫 B-roll 素材寫視覺索引")
    ap.add_argument("broll_dir", help="B-roll 素材資料夾（只掃最外層）")
    ap.add_argument("--out", help="索引輸出位置（預設放返素材資料夾）")
    ap.add_argument("--force", action="store_true", help="無視 cache，全部重新睇一次")
    args = ap.parse_args()

    broll_dir = Path(args.broll_dir).expanduser().resolve()
    if not broll_dir.is_dir():
        print(f"ERROR: 搵唔到 B-roll 資料夾: {broll_dir}", file=sys.stderr)
        return 1
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        print("ERROR: 冇 GOOGLE_AI_API_KEY，B-roll 視覺索引要 Gemini 先做到。", file=sys.stderr)
        return 2
    out = Path(args.out).expanduser().resolve() if args.out else broll_dir / "broll_index.json"
    media = sorted((p for p in broll_dir.iterdir()
                    if p.is_file() and p.suffix.lower() in MEDIA_EXTS),
                   key=lambda p: p.name.lower())
    if not media:
        print("ERROR: 呢個資料夾冇支援嘅 B-roll 片或相", file=sys.stderr)
        return 1

    try:
        from google import genai
    except ImportError:
        print("ERROR: 未裝 google-genai，先跟 SETUP 裝好現有 requirements。", file=sys.stderr)
        return 1
    client = genai.Client(api_key=api_key, http_options={"timeout": 120_000})

    cached = {}
    if out.exists() and not args.force:
        try:
            old = json.loads(out.read_text(encoding="utf-8"))
            cached = {item["file"]: item for item in old.get("items", []) if "file" in item}
        except (OSError, json.JSONDecodeError, TypeError):
            print("舊 index 讀唔到，今次重新整過。", file=sys.stderr)

    items = []
    for i, path in enumerate(media, 1):
        stat = path.stat()
        old = cached.get(path.name)
        if (old and old.get("size") == stat.st_size
                and old.get("mtime") == stat.st_mtime and not args.force):
            print(f"[{i}/{len(media)}] cache ✓ {path.name}")
            items.append(old)
            continue
        print(f"[{i}/{len(media)}] 睇緊 {path.name} ...")
        try:
            result = index_one(client, path)
        except Exception as exc:
            print(f"ERROR: {path.name} 索引失敗: {exc}", file=sys.stderr)
            return 1
        items.append({"file": path.name, "size": stat.st_size, "mtime": stat.st_mtime,
                      **result})

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"version": 1, "model": MODEL, "items": items},
                              ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"寫好 {out} — {len(items)} 件素材")
    return 0


if __name__ == "__main__":
    sys.exit(main())
