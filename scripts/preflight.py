#!/usr/bin/env python3
"""Follower-facing installation and runtime preflight.

No media is uploaded or modified.  The check only reads the local Python,
FFmpeg, package, key-presence, filter, font, and free-disk state.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path


KIT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(KIT / "lib"))

from gemini_key import resolve_gemini_key


CRITICAL_CHECKS = {
    "python_3_10_plus", "ffmpeg", "ffprobe", "whisper_engine",
    "google_genai", "numpy", "pillow", "ffmpeg_filters",
}


def _command(name: str) -> dict:
    path = shutil.which(name)
    return {"ok": bool(path), "detail": path or f"搵唔到 {name}"}


def _module(name: str) -> dict:
    try:
        found = importlib.util.find_spec(name) is not None
    except (ImportError, ModuleNotFoundError, ValueError):
        found = False
    return {"ok": found, "detail": "已安裝" if found else f"未安裝 {name}"}


def _ffmpeg_filters() -> dict:
    if not shutil.which("ffmpeg"):
        return {"ok": False, "missing": ["zscale", "tonemap", "subtitles", "drawtext"]}
    result = subprocess.run(
        ["ffmpeg", "-hide_banner", "-filters"], capture_output=True, text=True,
    )
    text = result.stdout + result.stderr
    required = ["zscale", "tonemap", "subtitles", "drawtext"]
    missing = [name for name in required if name not in text]
    return {"ok": not missing, "missing": missing}


def _font() -> dict:
    from kit_config import CONFIG

    configured = str(CONFIG["brand"].get("subtitle_font") or "").strip()
    defaults = {
        "Darwin": "PingFang TC",
        "Windows": "Microsoft JhengHei",
        "Linux": "Noto Sans CJK TC",
    }
    wanted = configured or defaults.get(platform.system(), "Noto Sans CJK TC")
    fc_match = shutil.which("fc-match")
    if not fc_match:
        return {"ok": True, "font": wanted, "detail": "系統冇 fc-match；出片時再由 FFmpeg 驗證"}
    result = subprocess.run([fc_match, wanted], capture_output=True, text=True)
    matched = result.stdout.strip().splitlines()[0] if result.stdout.strip() else ""
    return {
        "ok": result.returncode == 0 and bool(matched),
        "font": wanted,
        "detail": matched or "搵唔到可用字體",
    }


def build_report() -> dict:
    python_ok = sys.version_info >= (3, 10)
    engine = _module("mlx_whisper") if (
        platform.system() == "Darwin" and platform.machine() == "arm64"
    ) else _module("faster_whisper")
    if not engine["ok"]:
        fallback = _module("faster_whisper")
        if fallback["ok"]:
            engine = fallback
    disk = shutil.disk_usage(KIT)
    _gemini_key, gemini_key_env = resolve_gemini_key()
    checks = {
        "python_3_10_plus": {
            "ok": python_ok,
            "detail": platform.python_version(),
        },
        "ffmpeg": _command("ffmpeg"),
        "ffprobe": _command("ffprobe"),
        "whisper_engine": engine,
        "google_genai": _module("google.genai"),
        "numpy": _module("numpy"),
        "pillow": _module("PIL"),
        "ffmpeg_filters": _ffmpeg_filters(),
        "subtitle_font": _font(),
        "gemini_key": {
            "ok": bool(_gemini_key),
            "detail": f"已設定（{gemini_key_env}）" if _gemini_key else "未設定（會退化，捉重複同字幕清潔會失效）",
        },
        "free_disk_gb": {
            "ok": disk.free >= 10 * 1024**3,
            "detail": round(disk.free / 1024**3, 1),
        },
    }
    critical_failures = [
        name for name in CRITICAL_CHECKS if not checks[name]["ok"]
    ]
    warnings = [
        name for name in checks if name not in CRITICAL_CHECKS and not checks[name]["ok"]
    ]
    return {
        "status": "pass" if not critical_failures else "fail",
        "critical_failures": sorted(critical_failures),
        "warnings": warnings,
        "checks": checks,
    }


def should_fail(report: dict, strict: bool) -> bool:
    return bool(report["critical_failures"] or (strict and report["warnings"]))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--strict", action="store_true", help="連 Gemini key／字體／disk 警告都要齊")
    args = parser.parse_args()
    report = build_report()
    failed = should_fail(report, args.strict)
    report["status"] = "fail" if failed else "pass"
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        for name, result in report["checks"].items():
            icon = "✓" if result["ok"] else "✗"
            detail = result.get("detail", result.get("missing", ""))
            print(f"{icon} {name}: {detail}")
        print("PREFLIGHT FAIL" if failed else "PREFLIGHT PASS")
    return 2 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
