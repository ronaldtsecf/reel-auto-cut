#!/usr/bin/env python3
"""Gemini 聽 audio cross-check whisper transcript — 搵漏網 retakes。

Whisper 係 LM 導向，會自動平滑化重複位（結巴、即時重讀、false start
可能完全唔出現喺 transcript），淨靠 whisper 出 EDL 會漏剪。呢個 script
用 Gemini 聽 raw audio 逐段對照，輸出 findings JSON 俾 LLM 修 EDL。

Usage:
    verify_takes_gemini.py <audio> <takes_packed.md> [-o findings.json]

需要 GOOGLE_AI_API_KEY env var（genai-env 跑）。
"""
import argparse
import base64
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from google import genai
from google.genai.types import GenerateContentConfig

MODEL = "gemini-2.5-pro"          # 聽力 ground-truth 用 pro；quota 問題先退 flash
FALLBACK_MODEL = "gemini-2.5-flash"

PROMPT = """你會收到一段廣東話口播 raw 錄音，同埋 whisper 對佢嘅 transcript（逐行，行首係 [開始秒-結束秒]，⏸ 行係靜默標記）。

背景：speaker 跟稿讀，讀唔順就即刻重讀，所以錄音入面有好多 NG takes。whisper 有個已知缺陷：佢會「平滑化」輸出 — 重複講嘅句子可能只出一次、結巴位被執走、有啲 take 完全漏咗。你嘅任務係用對耳搵返所有被漏低嘅重複。

逐段細聽成條 audio（唔好跳），搵出**所有**「同一句／同一意思講多過一次」嘅位置：
1. 完整句重讀（同句讀兩次或以上，字眼可以有出入）
2. 半句 false start（講到一半斷咗重新嚟）
3. 句子中途窒咗、倒返轉頭重講嗰幾隻字（mid-sentence stumble）
4. whisper transcript 完全冇出現嘅講話段

輸出 JSON array，每個 finding：
{
  "approx_start": <重複區開始嘅大約秒數，數字，±5 秒容差>,
  "approx_end": <重複區結束嘅大約秒數>,
  "heard": "你實際聽到嘅 verbatim（包齊所有重複，用｜分隔每個 take）",
  "whisper_ref": "對應 whisper transcript 行嘅開頭幾隻字，搵唔到對應就寫 MISSING",
  "takes": <聽到幾多個 take>,
  "keep_last": "最後一個 take 嘅文字（呢個係要保留嘅）",
  "kind": "full-retake | false-start | stumble | missing-from-whisper"
}

規則：寧濫勿缺，懷疑係重複就報。如果成段 audio 完全冇漏網，輸出 []。只輸出 JSON array，唔好有其他文字。"""


def to_mp3(audio: Path) -> bytes:
    if audio.suffix.lower() == ".mp3":
        return audio.read_bytes()
    with tempfile.NamedTemporaryFile(suffix=".mp3") as tf:
        subprocess.run(["ffmpeg", "-y", "-v", "error", "-i", str(audio),
                        "-ac", "1", "-b:a", "64k", tf.name], check=True)
        return Path(tf.name).read_bytes()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("audio")
    ap.add_argument("packed")
    ap.add_argument("-o", "--output", default=None)
    a = ap.parse_args()

    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        sys.exit("GOOGLE_AI_API_KEY not set")
    client = genai.Client(api_key=api_key, http_options={"timeout": 300_000})

    audio_b64 = base64.b64encode(to_mp3(Path(a.audio))).decode()
    packed = Path(a.packed).read_text()

    for model in (MODEL, FALLBACK_MODEL):
        try:
            resp = client.models.generate_content(
                model=model,
                contents=[
                    {"inline_data": {"mime_type": "audio/mpeg", "data": audio_b64}},
                    f"{PROMPT}\n\n=== whisper transcript ===\n{packed}",
                ],
                config=GenerateContentConfig(response_mime_type="application/json"),
            )
            findings = json.loads(resp.text)
            break
        except Exception as e:  # quota / model unavailable → fallback
            print(f"{model} fail: {e}", file=sys.stderr)
            if model == FALLBACK_MODEL:
                raise
    out = Path(a.output) if a.output else Path(a.packed).parent / "gemini_findings.json"
    out.write_text(json.dumps({"model": model, "findings": findings},
                              ensure_ascii=False, indent=1))
    print(f"wrote {out} — {len(findings)} findings（model: {model}）")
    for f in findings:
        print(f"  [{f.get('approx_start', '?')}s] {f.get('kind')}: "
              f"{str(f.get('heard', ''))[:60]}")


if __name__ == "__main__":
    main()
