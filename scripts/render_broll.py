#!/usr/bin/env python3
"""將已覆核嘅 B-roll plan 全畫面疊落 rough cut，主片聲軌保持不變。

Usage:
    render_broll.py <rough.mp4> <broll_plan.json> -o <out.mp4>

plan 最少要有 slots；每項係 start、end、file。相對 file 由 plan 嘅 broll_dir
（相對 plan 所在資料夾）開始搵。相片會由 1.0 緩慢 zoom 到 1.06。
"""
from __future__ import annotations

import argparse
import json
import platform
import subprocess
import sys
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp"}


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def probe(path: Path) -> dict:
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height,r_frame_rate:format=duration",
             "-of", "json", str(path)])
    try:
        data = json.loads(r.stdout)
        stream = data["streams"][0]
        num, den = stream.get("r_frame_rate", "30/1").split("/", 1)
        return {"width": int(stream["width"]), "height": int(stream["height"]),
                "fps": float(num) / float(den),
                "duration": float(data.get("format", {}).get("duration") or 0)}
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError, json.JSONDecodeError):
        raise RuntimeError(f"讀唔到片嘅資料: {path.name}")


def pick_vcodec() -> list[str]:
    if platform.system() == "Darwin":
        r = run(["ffmpeg", "-hide_banner", "-encoders"])
        if "h264_videotoolbox" in r.stdout:
            return ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-tag:v", "avc1"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]


def resolve_root(plan_path: Path, plan: dict) -> Path:
    if plan.get("broll_dir") is not None:
        root = Path(str(plan["broll_dir"])).expanduser()
        return root if root.is_absolute() else (plan_path.parent / root).resolve()
    if plan.get("source_index"):
        index = Path(str(plan["source_index"])).expanduser()
        index = index if index.is_absolute() else (plan_path.parent / index).resolve()
        return index.parent
    return plan_path.parent


def main() -> int:
    ap = argparse.ArgumentParser(description="將 B-roll plan 疊落 rough cut，字幕之後先燒")
    ap.add_argument("rough")
    ap.add_argument("plan")
    ap.add_argument("-o", "--output", required=True)
    args = ap.parse_args()

    rough = Path(args.rough).expanduser().resolve()
    plan_path = Path(args.plan).expanduser().resolve()
    out = Path(args.output).expanduser().resolve()
    if not rough.is_file():
        print(f"ERROR: 搵唔到 rough cut: {rough}", file=sys.stderr)
        return 1
    if not plan_path.is_file():
        print(f"ERROR: 搵唔到 B-roll plan: {plan_path}", file=sys.stderr)
        return 1
    if out == rough:
        print("ERROR: 輸出唔可以直接蓋住 rough cut，請用另一個檔名。", file=sys.stderr)
        return 1
    try:
        plan = json.loads(plan_path.read_text(encoding="utf-8"))
        slots = plan["slots"]
        main = probe(rough)
    except (OSError, KeyError, TypeError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"ERROR: plan 或 rough cut 讀唔到: {exc}", file=sys.stderr)
        return 1

    root = resolve_root(plan_path, plan)
    def slot_start(slot: dict) -> float:
        try:
            return float(slot.get("start", 0))
        except (AttributeError, TypeError, ValueError):
            return 0.0

    prepared = []
    for i, slot in enumerate(sorted(slots, key=slot_start), 1):
        try:
            start = max(0.0, float(slot["start"]))
            end = min(main["duration"], float(slot["end"]))
            file = Path(str(slot["file"])).expanduser()
        except (KeyError, TypeError, ValueError):
            print(f"ERROR: slot {i} 嘅 start、end 或 file 格式唔啱", file=sys.stderr)
            return 1
        media = file if file.is_absolute() else (root / file).resolve()
        if not media.is_file():
            print(f"ERROR: slot {i} 搵唔到素材: {file}", file=sys.stderr)
            return 1
        is_image = media.suffix.lower() in IMAGE_EXTS
        if not is_image:
            try:
                broll_duration = probe(media)["duration"]
            except RuntimeError as exc:
                print(f"ERROR: {exc}", file=sys.stderr)
                return 1
            wanted = end - start
            if broll_duration < wanted:
                end = start + broll_duration
                print(f"slot {i}: {media.name} 得 {broll_duration:.2f}s，收窄到 {start:.2f}–{end:.2f}s")
        if end - start <= 0.05:
            print(f"slot {i}: 裁完冇有效長度，跳過。")
            continue
        prepared.append({"start": start, "end": end, "path": media,
                         "image": is_image, "input": len(prepared) + 1})

    out.parent.mkdir(parents=True, exist_ok=True)
    if not prepared:
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(rough),
                 "-map", "0", "-c", "copy", str(out)])
        if r.returncode != 0:
            print(f"ERROR: 複製 rough cut 失敗:\n{r.stderr[-600:]}", file=sys.stderr)
            return 1
        print(f"plan 冇有效 slot，原片照抄到 {out}")
        return 0

    fps = main["fps"] or 30.0
    fps_text = f"{fps:.6f}".rstrip("0").rstrip(".")
    inputs = ["-i", str(rough)]
    for slot in prepared:
        duration = slot["end"] - slot["start"]
        if slot["image"]:
            inputs += ["-loop", "1", "-framerate", fps_text, "-t", f"{duration:.3f}",
                       "-i", str(slot["path"])]
        else:
            inputs += ["-i", str(slot["path"])]

    width, height = main["width"], main["height"]
    filters = [f"[0:v]fps={fps_text},format=yuv420p,setpts=PTS-STARTPTS[base0]"]
    last = "base0"
    for i, slot in enumerate(prepared, 1):
        start, end = slot["start"], slot["end"]
        duration = end - start
        cover = (f"scale={width}:{height}:force_original_aspect_ratio=increase,"
                 f"crop={width}:{height},setsar=1")
        if slot["image"]:
            step = 0.06 / max(1.0, duration * fps)
            source = (f"[{slot['input']}:v]{cover},"
                      f"zoompan=z='min(1.0+on*{step:.9f},1.06)':"
                      f"x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
                      f"s={width}x{height}:fps={fps_text},trim=duration={duration:.3f},"
                      f"setpts=PTS-STARTPTS+{start:.3f}/TB[br{i}]")
        else:
            source = (f"[{slot['input']}:v]trim=start=0:duration={duration:.3f},"
                      f"setpts=PTS-STARTPTS,{cover},fps={fps_text},"
                      f"setpts=PTS+{start:.3f}/TB[br{i}]")
        filters.append(source)
        filters.append(f"[{last}][br{i}]overlay=enable='between(t,{start:.3f},{end:.3f})':"
                       f"eof_action=pass:repeatlast=0[base{i}]")
        last = f"base{i}"

    def render_cmd(vcodec: list[str]) -> list[str]:
        return ["ffmpeg", "-y", "-v", "error", *inputs,
                "-filter_complex", ";".join(filters),
                "-map", f"[{last}]", "-map", "0:a?", *vcodec,
                "-c:a", "copy", "-t", f"{main['duration']:.3f}",
                "-movflags", "+faststart", str(out)]

    vcodec = pick_vcodec()
    r = run(render_cmd(vcodec))
    if r.returncode != 0 and any("videotoolbox" in arg for arg in vcodec):
        print("硬件 encoder 開唔到，轉用 libx264 再試。", file=sys.stderr)
        fallback = ["-c:v", "libx264", "-preset", "medium", "-crf", "18",
                    "-pix_fmt", "yuv420p"]
        r = run(render_cmd(fallback))
    if r.returncode != 0:
        print(f"ERROR: 疊 B-roll 失敗:\n{r.stderr[-1000:]}", file=sys.stderr)
        return 1
    print(f"疊好 {len(prepared)} 段 B-roll → {out}")
    print("主片聲軌冇郁，字幕可以而家先燒上去。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
