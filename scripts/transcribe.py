#!/usr/bin/env python3
"""Transcribe 口播 video → word-level timestamp JSON（跨平台 whisper）。

Engine（自動揀，可用 env 強制）:
  - Apple Silicon Mac → mlx-whisper（Metal 加速，快）
  - Windows / Linux / Intel Mac → faster-whisper（CTranslate2，CPU/CUDA 都跑）
兩個 engine normalize 成同一 transcript.json shape，downstream 零改。

Usage:
    transcribe.py <video_path> --out-dir <dir> [--language yue] [--initial-prompt "..."]

Env:
    JYUT_WHISPER_ENGINE = mlx | faster   (default: auto by platform)
    JYUT_WHISPER_MODEL  = 覆寫 model      (mlx default whisper-large-v3-mlx; faster default large-v3，CPU 慢可改 medium)
    JYUT_WHISPER_DEVICE = cpu | cuda     (faster only; default auto-detect)

Output: <out-dir>/transcript.json
    {source, source_key, duration, language, words:[{start,end,text}], segments:[{start,end,text}]}
Cache: source_key = path+size+mtime hash。transcript.json 已 match 就 skip。
"""
import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
from pathlib import Path

MLX_MODEL = os.environ.get("JYUT_WHISPER_MODEL", "mlx-community/whisper-large-v3-mlx")
FW_MODEL = os.environ.get("JYUT_WHISPER_MODEL", "large-v3")


def source_key(path: Path) -> str:
    st = path.stat()
    return hashlib.sha256(f"{path}|{st.st_size}|{st.st_mtime_ns}".encode()).hexdigest()[:16]


def pick_audio_map(video: Path) -> "str | None":
    """iPhone spatial audio 片有條 codec=unknown 嘅 spatial track（ffmpeg decode 唔到，排喺正常 aac 前），
    `-vn` 預設攞佢就 'no decoder found' 死。多 audio track 時揀返第一條可 decode 嘅，返 ffmpeg -map spec；
    單 track（正常片）返 None 行預設，唔變舊行為。"""
    out = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a",
         "-show_entries", "stream=index,codec_name", "-of", "csv=p=0", str(video)],
        capture_output=True, text=True,
    ).stdout.strip()
    streams = [tuple(p.strip() for p in line.split(",")[:2])
               for line in out.splitlines() if "," in line]
    if len(streams) <= 1:
        return None
    for idx, codec in streams:
        if codec.lower() not in ("unknown", "none", ""):
            return f"0:{idx}"
    return None


def extract_audio(video: Path, wav: Path) -> None:
    amap = pick_audio_map(video)
    cmd = ["ffmpeg", "-y", "-v", "error", "-i", str(video)]
    if amap:
        cmd += ["-map", amap]
    cmd += ["-vn", "-ac", "1", "-ar", "16000", "-c:a", "pcm_s16le", str(wav)]
    subprocess.run(cmd, check=True)


def pick_engine() -> str:
    forced = os.environ.get("JYUT_WHISPER_ENGINE", "").lower()
    if forced in ("mlx", "faster"):
        return forced
    if platform.system() == "Darwin" and platform.machine() == "arm64":
        try:
            import mlx_whisper  # noqa: F401
            return "mlx"
        except ImportError:
            pass
    return "faster"


def run_whisper(wav: Path, language: str, initial_prompt: str):
    """跑 whisper，返 (segments, detected_language)。
    segments: [{text,start,end,words:[{word,start,end}]}] — 兩 engine normalize 成同 shape，
    downstream（pack/gen_captions/filter）食呢個 shape，唔關 engine 事。"""
    engine = pick_engine()
    if engine == "mlx":
        import mlx_whisper
        print(f"engine: mlx ({MLX_MODEL})", file=sys.stderr)
        r = mlx_whisper.transcribe(
            str(wav), path_or_hf_repo=MLX_MODEL, language=language,
            word_timestamps=True, condition_on_previous_text=False,
            hallucination_silence_threshold=2.0, initial_prompt=initial_prompt or None,
            verbose=False)
        return r["segments"], r.get("language", language)

    # faster-whisper（跨平台 base）
    from faster_whisper import WhisperModel
    device = os.environ.get("JYUT_WHISPER_DEVICE", "").lower()
    if device not in ("cpu", "cuda"):
        device = "cpu"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
        except Exception:
            pass
    ct = "float16" if device == "cuda" else "int8"
    print(f"engine: faster-whisper ({FW_MODEL}, {device}/{ct})", file=sys.stderr)
    model = WhisperModel(FW_MODEL, device=device, compute_type=ct)
    segs, info = model.transcribe(
        str(wav), language=language, word_timestamps=True,
        condition_on_previous_text=False, initial_prompt=initial_prompt or None)
    norm = []
    for s in segs:  # generator → 物化（同時 trigger transcribe）
        norm.append({
            "text": s.text, "start": s.start, "end": s.end,
            "words": [{"word": w.word, "start": w.start, "end": w.end}
                      for w in (s.words or [])],
        })
    return norm, (info.language or language)


def transcribe(video: Path, out_dir: Path, language: str, initial_prompt: str) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / "transcript.json"
    wav = out_dir / "audio.wav"          # persist：Gemini 驗證 + 顯微抽 clip 都要用
    key = source_key(video)
    if out_path.exists():
        cached = json.loads(out_path.read_text())
        if cached.get("source_key") == key:
            print(f"cache hit — {out_path}")
            return out_path

    # cache miss（source 新或變）→ force re-extract wav（同名覆寫會令舊 wav stale）。
    extract_audio(video, wav)
    segs, detected_lang = run_whisper(wav, language, initial_prompt)

    words, segments = [], []
    for seg in segs:
        text = seg["text"].strip()
        if text:
            segments.append({"start": round(seg["start"], 3), "end": round(seg["end"], 3), "text": text})
        for w in seg.get("words", []):
            t = w["word"].strip()
            if t:
                words.append({"start": round(w["start"], 3), "end": round(w["end"], 3), "text": t})

    duration = float(subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(video)],
        capture_output=True, text=True, check=True,
    ).stdout.strip())

    out_path.write_text(json.dumps(
        {"source": str(video), "source_key": key, "duration": duration,
         "language": detected_lang, "words": words, "segments": segments},
        ensure_ascii=False, indent=1))
    print(f"wrote {out_path} — {len(words)} words / {len(segments)} segments / {duration:.1f}s")
    return out_path


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("video")
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--language", default="yue")
    ap.add_argument("--initial-prompt", default="以下係廣東話口語。")
    a = ap.parse_args()
    video = Path(a.video).expanduser()
    if not video.exists():
        sys.exit(f"video not found: {video}")
    transcribe(video, Path(a.out_dir).expanduser(), a.language, a.initial_prompt)


if __name__ == "__main__":
    main()
