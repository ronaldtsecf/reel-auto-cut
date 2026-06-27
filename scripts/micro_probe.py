#!/usr/bin/env python3
"""Micro-probe: 抽短 clip 餵 Gemini 問精確 take 邊界秒。retake-dense 顯微定位用。

Usage: micro_probe.py <source_video> <probes.json> [-o out.json]
probes.json: [{"label":..., "start":..., "end":..., "question":...}, ...]
source 秒 = clip start + clip_seconds。需要 GOOGLE_AI_API_KEY。
"""
import argparse, base64, json, os, subprocess, sys, tempfile
from pathlib import Path
from google import genai
from google.genai.types import GenerateContentConfig

MODEL = "gemini-2.5-pro"

PROMPT_TMPL = """你會收到一段廣東話口播 raw 錄音 clip。speaker 跟稿讀，讀唔順就即刻重讀，所以 clip 入面通常有重複 take（同一句講多過一次）。

呢個 clip 由 source 影片第 {start:.2f} 秒開始（即係 clip 內部 0.00s 對應 source {start:.2f}s）。

問題：{question}

仔細聽（可以聽多幾次），答案精確到 clip 內部相對秒（小數一位）。輸出 JSON：
{{"clip_seconds": <相對 clip 開頭嘅秒數，數字；如問題有兩個位就用 clip_seconds 同 clip_seconds_2>, "clip_seconds_2": <第二個位，冇就 null>, "takes_heard": <聽到幾多個 take>, "heard": "你聽到嘅 verbatim（多個 take 用｜分隔）", "confidence": "high|medium|low", "note": "簡短解釋"}}
只輸出 JSON。"""


def clip_mp3(src, start, end):
    tf = tempfile.NamedTemporaryFile(suffix=".mp3", delete=False)
    tf.close()
    subprocess.run(["ffmpeg", "-y", "-v", "error", "-ss", str(start), "-to", str(end),
                    "-i", str(src), "-vn", "-ac", "1", "-b:a", "64k", tf.name], check=True)
    return Path(tf.name)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("source"); ap.add_argument("probes"); ap.add_argument("-o", "--output")
    a = ap.parse_args()
    key = os.environ.get("GOOGLE_AI_API_KEY")
    if not key:
        sys.exit("GOOGLE_AI_API_KEY not set")
    client = genai.Client(api_key=key, http_options={"timeout": 300_000})
    probes = json.loads(Path(a.probes).read_text())
    results = []
    for p in probes:
        c = clip_mp3(a.source, p["start"], p["end"])
        b64 = base64.b64encode(c.read_bytes()).decode()
        prompt = PROMPT_TMPL.format(start=p["start"], question=p["question"])
        try:
            resp = client.models.generate_content(
                model=MODEL,
                contents=[{"inline_data": {"mime_type": "audio/mpeg", "data": b64}}, prompt],
                config=GenerateContentConfig(response_mime_type="application/json"))
            ans = json.loads(resp.text)
        except Exception as e:
            ans = {"error": str(e)}
        ans["label"] = p["label"]; ans["clip_range"] = [p["start"], p["end"]]
        cs = ans.get("clip_seconds")
        if isinstance(cs, (int, float)):
            ans["source_seconds"] = round(p["start"] + cs, 2)
        cs2 = ans.get("clip_seconds_2")
        if isinstance(cs2, (int, float)):
            ans["source_seconds_2"] = round(p["start"] + cs2, 2)
        results.append(ans)
        c.unlink(missing_ok=True)
        print(f'[{p["label"]}] src={ans.get("source_seconds","?")}'
              f'{"/"+str(ans["source_seconds_2"]) if "source_seconds_2" in ans else ""} '
              f'({ans.get("confidence","?")}) {str(ans.get("heard",""))[:55]}')
    out = Path(a.output) if a.output else Path("micro_probe_out.json")
    out.write_text(json.dumps(results, ensure_ascii=False, indent=1))
    print(f"wrote {out}")


if __name__ == "__main__":
    main()
