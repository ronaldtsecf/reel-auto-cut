#!/usr/bin/env python3
"""Render EDL → 剪好 + 變速嘅 reel（frame-accurate re-encode pipeline）。

Usage:
    render_edl.py <edl.json> --out <final.mp4> [--speed 1.05] [--rejects]
                  [--keep-master] [--encoder videotoolbox|libx264]
                  [--punch | --no-punch]

Phases: lint EDL → report silences → per-segment extract（EDL + pad only,
30ms audio fades, fps normalisation, HDR safety）→ concat → final pass
（setpts/atempo + faststart）→ cut_list.md + qc.json。

EDL schema（video-use 相容 + 自家 fields）:
    {"version": 1, "sources": {"ID": "/abs/path.mp4"},
     "ranges": [{"source": "ID", "start": 12.24, "end": 18.91,
                 "quote": "...", "take": "3/3", "dropped": [[3.1, 7.8]],
                 "flag": false, "note": ""}]}
start/end 係 transcript word boundary（source-time）；pad 由 render 加。
"""
from __future__ import annotations  # PEP 604 union annotation（X | None）→ lazy，Python 3.9 都 import 得

import argparse
import json
import platform
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from kit_config import CONFIG

PAD_BEFORE = 0.05      # 首字前 pad（word timestamp 慣性遲報字頭）；v7 aggressive 0.10→0.05
PAD_AFTER = 0.08       # 尾字後 pad（粵語句尾助詞拖尾）；v7 aggressive 0.15→0.08
CUT_IN_LEAD = 0.06     # snap 後：聲音開始前留幾多 silence；v7 aggressive 0.12→0.06
CUT_OUT_TAIL = 0.08    # snap 後：聲音停後留幾多 silence；v7 aggressive 0.16→0.08（每句留白 ≈ 0.14s，floor 防食字頭）
SNAP_MAX = 1.0         # cut-out 向後 snap 搜尋上限；超過 → 唔 snap + warning
SNAP_MAX_IN = 0.3      # cut-in 向前 snap 上限 — 太遠會倒灌吞咗 NG 殘音（EP1 zone C 教訓）
MIN_RANGE = 0.3        # range 最短長度（「拜拜」級短句都要過到）
FADE = 0.03            # 30ms audio fade 防 click（video-use rule #3）
SIL_NOISE = "-30dB"
SIL_MIN = 0.25
BT709_TAG_ARGS = [
    "-colorspace", "bt709", "-color_primaries", "bt709", "-color_trc", "bt709",
]


def run(cmd: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=True, text=True)


def ffprobe_duration(path: str) -> float:
    r = run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", path])
    return float(r.stdout.strip())


def ffprobe_size(path: str) -> tuple[int, int]:
    r = run(["ffprobe", "-v", "error", "-select_streams", "v:0",
             "-show_entries", "stream=width,height:stream_tags=rotate:stream_side_data=rotation",
             "-of", "json", path])
    try:
        stream = json.loads(r.stdout)["streams"][0]
        width, height = int(stream["width"]), int(stream["height"])
        rotation = stream.get("tags", {}).get("rotate", 0)
        for side_data in stream.get("side_data_list", []):
            if "rotation" in side_data:
                rotation = side_data["rotation"]
                break
        if abs(int(float(rotation))) % 180 == 90:
            width, height = height, width
        return width, height
    except (KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
        sys.exit(f"讀唔到片嘅解像度: {path}")


def punch_filter(width: int, height: int, zoom: float) -> str:
    """Crop 入去再 scale 返原尺寸；crop window 向上偏 8% 保住頭部。"""
    crop_w = max(2, int(width / zoom) // 2 * 2)
    crop_h = max(2, int(height / zoom) // 2 * 2)
    return (f"crop={crop_w}:{crop_h}:x=(iw-ow)/2:y=(ih-oh)*0.42,"
            f"scale={width}:{height}")


def pick_audio_map(src: str) -> "str | None":
    """iPhone spatial audio 片有條 codec=unknown 嘅 spatial track（ffmpeg decode 唔到，排喺正常 aac 前），
    預設攞佢就 'no decoder found' 死（exit 234）。多 audio track 時揀返第一條可 decode 嘅，返 ffmpeg -map spec；
    單 track（正常片）返 None 行預設，唔變舊行為。同 transcribe.py pick_audio_map 一致。"""
    out = run(["ffprobe", "-v", "error", "-select_streams", "a",
               "-show_entries", "stream=index,codec_name", "-of", "csv=p=0", src]).stdout.strip()
    streams = [tuple(p.strip() for p in line.split(",")[:2])
               for line in out.splitlines() if "," in line]
    if len(streams) <= 1:
        return None
    for idx, codec in streams:
        if codec.lower() not in ("unknown", "none", ""):
            return f"0:{idx}"
    return None


def detect_silences(src: str, amap: "str | None" = None) -> list[tuple[float, float]]:
    pre = ["-map", "0:v:0", "-map", amap] if amap else []
    r = run(["ffmpeg", "-i", src, *pre, "-af",
             f"silencedetect=noise={SIL_NOISE}:d={SIL_MIN}", "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    return list(zip(starts, ends))


def in_silence(t: float, sils: list) -> tuple[float, float] | None:
    for s, e in sils:
        if s <= t <= e:
            return (s, e)
    return None


def snap_edge(t: float, kind: str, sils: list, warnings: list, tag: str) -> float:
    """kind='in'：cut-in 只可向前（早）移；kind='out'：只可向後（遲）移。"""
    hit = in_silence(t, sils)
    if hit:
        s, e = hit
        return max(s, e - CUT_IN_LEAD) if kind == "in" else min(e, s + CUT_OUT_TAIL)
    if kind == "in":
        cands = [(s, e) for s, e in sils if e <= t and t - e <= SNAP_MAX_IN]
        if cands:
            s, e = cands[-1]
            return max(s, e - CUT_IN_LEAD)
    else:
        cands = [(s, e) for s, e in sils if s >= t and s - t <= SNAP_MAX]
        if cands:
            s, e = cands[0]
            return min(e, s + CUT_OUT_TAIL)
    warnings.append(f"{tag}: cut-{kind} {t:.2f}s 唔喺 silence（±{SNAP_MAX}s 內冇刀位）— 硬切，人耳 check")
    return t


def split_on_internal_silences(cut_in: float, cut_out: float, sils: list,
                               thresh: float, log: list, tag: str) -> list[tuple[float, float]]:
    """Range 內部 silence ≥ thresh → 中間斬開壓縮（抖氣位收緊）。
    聲尾留 CUT_OUT_TAIL、聲頭前留 CUT_IN_LEAD → 壓完任何停頓 ≈ 0.35s。"""
    pieces = []
    cur = cut_in
    for s, e in sils:
        if s <= cur + MIN_RANGE or e >= cut_out - MIN_RANGE:
            continue                      # 唔係完全喺內部（或太貼邊）
        if (e - s) < thresh:
            continue
        top_end, next_start = s + CUT_OUT_TAIL, e - CUT_IN_LEAD
        if next_start - top_end < 0.05:   # 壓無可壓
            continue
        pieces.append((cur, top_end))
        log.append({"range": tag, "silence": [round(s, 2), round(e, 2)],
                    "saved_s": round(next_start - top_end, 2)})
        cur = next_start
    pieces.append((cur, cut_out))
    return pieces


def subtract_drops(cut_in: float, cut_out: float, dropped: list) -> list[tuple[float, float]]:
    """[cut_in, cut_out] 減去 range 內 dropped sub-ranges（NG 喺 take 中間，e.g. false start）。"""
    if not dropped:
        return [(cut_in, cut_out)]
    keeps, pos = [], cut_in
    for ds, de in sorted((float(d[0]), float(d[1])) for d in dropped):
        ds, de = max(cut_in, ds), min(cut_out, de)
        if de <= pos:
            continue
        if ds > pos:
            keeps.append((pos, ds))
        pos = max(pos, de)
    if pos < cut_out:
        keeps.append((pos, cut_out))
    return keeps


def lint(edl: dict, src_dur: float) -> None:
    ranges = edl["ranges"]
    if not ranges:
        sys.exit("EDL 冇 ranges")
    if len({r["source"] for r in ranges}) != 1:
        sys.exit("MVP 只支援 single source")
    prev_end = -1.0
    for i, r in enumerate(ranges):
        if not (0 <= r["start"] < r["end"] <= src_dur + 0.5):
            sys.exit(f"range {i} 出界: {r['start']}-{r['end']} (source {src_dur:.1f}s)")
        if r["end"] - r["start"] < MIN_RANGE:
            sys.exit(f"range {i} 短過 {MIN_RANGE}s")
        if r["start"] < prev_end:
            sys.exit(f"range {i} 同上一段 overlap")
        prev_end = r["end"]


def _mac_vt() -> bool:
    """Mac + videotoolbox 可用？否則跨平台用 libx264。"""
    if platform.system() != "Darwin":
        return False
    r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
    return "videotoolbox" in r.stdout


_MAC_VT = _mac_vt()


def encoder_args(quality: str, stage: str = "final") -> list[str]:
    if quality == "rough":                       # 近無損俾 CapCut 後製
        if _MAC_VT:                              # Mac：H.265 videotoolbox（seg 80M → final 50M）
            return ["-c:v", "hevc_videotoolbox", "-b:v", "80M" if stage == "seg" else "50M", "-tag:v", "hvc1"]
        # 跨平台：libx264 高質（crf 16 seg / 18 final）≈ 近無損
        return ["-c:v", "libx264", "-crf", "16" if stage == "seg" else "18", "-preset", "medium", "-pix_fmt", "yuv420p"]
    if quality == "libx264":
        return ["-c:v", "libx264", "-crf", "18", "-preset", "fast"]
    # preview default
    if _MAC_VT:
        return ["-c:v", "h264_videotoolbox", "-b:v", "12M"]
    return ["-c:v", "libx264", "-crf", "20", "-preset", "fast", "-pix_fmt", "yuv420p"]


def audio_bitrate(quality: str) -> str:
    return "256k" if quality == "rough" else "128k"


def source_visual_filter(src: str) -> tuple[str, str, list[str]]:
    """Return the exact source colour prefix and classification.

    HLG/PQ sources receive one canonical HDR→BT.709 conversion before any
    frame-rate or scaling filter.  Contradictory high-risk metadata blocks the
    render; ordinary incomplete SDR metadata is preserved with a warning.
    """
    from visual_preflight import (
        VisualPreflightError,
        build_source_visual_preflight,
        probe_source_color,
    )

    try:
        preflight = build_source_visual_preflight(probe_source_color(Path(src)))
    except VisualPreflightError as exc:
        sys.exit(f"色彩 preflight FAIL：{exc}")
    classification = str(preflight["source_color"]["classification"])
    warnings = list(preflight.get("warnings", []))
    if preflight["tone_map_applied"]:
        print(f"源片色彩：{classification} → HDR→BT.709（恰好 1 次）")
    else:
        print(f"源片色彩：{classification} → 保留原色彩（0 次 tone-map）")
    return preflight["effective_color_filter"], classification, warnings


def extract(src: str, start: float, end: float, out: Path, enc: list[str],
            abr: str = "128k", vf_extra: str = "", label: str = "",
            acodec: str = "pcm_s16le", amap: "str | None" = None,
            audio_only: bool = False, vf_prefix: str = "") -> None:
    dur = end - start
    if audio_only:
        # proof render：唔郁 video（秒級 vs 分鐘級），刀位/fade 同真 render 完全一致
        af = (f"aresample=async=1,afade=t=in:st=0:d={FADE},"
              f"afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}")
        amap_args = ["-map", amap] if amap else []
        r = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src,
                 "-t", f"{dur:.3f}", *amap_args, "-vn", "-af", af,
                 "-c:a", acodec, str(out)])
        if r.returncode != 0:
            sys.exit(f"extract fail {out.name}:\n{r.stderr[-800:]}")
        return
    vf = (vf_prefix + "," if vf_prefix else "") + "fps=60,format=yuv420p"
    vf += "," + vf_extra if vf_extra else ""
    if label:
        safe = label.replace(":", r"\:")
        vf += (f",drawtext=text='{safe}':x=20:y=60:fontsize=36:fontcolor=white"
               ":box=1:boxcolor=black@0.5:boxborderw=8")
    af = (f"aresample=async=1,afade=t=in:st=0:d={FADE},"
          f"afade=t=out:st={max(0.0, dur - FADE):.3f}:d={FADE}")
    # iPhone spatial audio 多 track：明確 -map video + 揀正 aac track（unknown spatial track 會 decode 死）
    amap_args = ["-map", "0:v:0", "-map", amap] if amap else []
    # 中間 segment 用 PCM（無 AAC encoder priming delay）→ concat -c copy 唔累積 A/V drift。
    # 之前 bug：每段 aac priming ~32ms，22 段 = 0.7s audio 拖後（final 0.68s drift）。
    # rejects preview 傳 acodec="aac"（preview 唔 care priming，慳體積）。
    a_args = ["-c:a", acodec] + (["-b:a", abr] if acodec == "aac" else [])
    tag_args = BT709_TAG_ARGS if vf_prefix else []
    r = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{start:.3f}", "-i", src,
             "-t", f"{dur:.3f}", *amap_args, "-vf", vf, "-af", af,
             *enc, *tag_args, *a_args, "-shortest", str(out)])  # video=audio 等長,防 concat A/V 累積
    if r.returncode != 0:
        sys.exit(f"extract fail {out.name}:\n{r.stderr[-800:]}")


def concat(segs: list[Path], out: Path, workdir: Path) -> None:
    lst = workdir / f"{out.stem}_concat.txt"
    lst.write_text("".join(f"file '{p.resolve()}'\n" for p in segs))
    r = run(["ffmpeg", "-y", "-v", "error", "-f", "concat", "-safe", "0",
             "-i", str(lst), "-c", "copy", str(out)])
    if r.returncode != 0:
        sys.exit(f"concat fail:\n{r.stderr[-800:]}")


def trim_silences(src: str, out: Path, enc: list[str], abr: str, dur: float,
                  segdir: Path, floor: float = 0.12, thresh: float = 0.30,
                  acodec: str = "pcm_s16le", amap: "str | None" = None,
                  audio_only: bool = False, tag_bt709: bool = False) -> dict:
    """Render 後 global silence-trim：detect 全片 silence ≥thresh，每個切到剩 floor。
    Catch split_on_internal_silences 漏咗嘅停頓（EDL range 邊界 / 片頭片尾 / range
    之間 concat gap）— 呢啲唔喺 range 內部，per-segment 常數 trim 唔到。
    Segment-based（-ss/-t 切 keep 段再 concat）→ video+audio 一齊切，A/V frame-accurate
    （select/aselect filter 試過 video/audio 唔同步切，A/V 爆 3.4s，棄）。
    註：src 已係 PCM master（單 audio track），amap 通常 None；保留參數一致性。"""
    pre = ["-map", "0:v:0", "-map", amap] if amap else []
    r = run(["ffmpeg", "-i", src, *pre, "-af",
             f"silencedetect=noise={SIL_NOISE}:d={thresh}", "-f", "null", "-"])
    starts = [float(m) for m in re.findall(r"silence_start: ([\d.]+)", r.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: ([\d.]+)", r.stderr)]
    sils = list(zip(starts, ends))
    if not sils:
        run(["ffmpeg", "-y", "-v", "error", "-i", src, "-c", "copy", str(out)])
        return {"trimmed": 0, "saved": 0.0}
    keeps, pos, saved = [], 0.0, 0.0
    for s, e in sils:
        keep_end = min(e, s + floor)          # silence 留 floor 防食字頭
        if keep_end > pos + 0.05:
            keeps.append((pos, keep_end))
        saved += max(0.0, e - keep_end)
        pos = e
    if pos < dur - 0.05:
        keeps.append((pos, dur))
    a_args = ["-c:a", acodec] + (["-b:a", abr] if acodec == "aac" else [])
    tsegs = []
    for i, (ks, ke) in enumerate(keeps):
        if ke - ks < 0.05:
            continue
        if audio_only:
            seg = segdir / f"trim_{i:03d}.wav"
            rr = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ks:.3f}", "-i", src,
                      "-t", f"{ke - ks:.3f}", "-vn", "-c:a", acodec, str(seg)])
        else:
            seg = segdir / f"trim_{i:03d}.mov"
            rr = run(["ffmpeg", "-y", "-v", "error", "-ss", f"{ks:.3f}", "-i", src,
                      "-t", f"{ke - ks:.3f}", "-vf", "fps=60,format=yuv420p",
                      *enc, *(BT709_TAG_ARGS if tag_bt709 else []),
                      *a_args, "-shortest", str(seg)])  # video=audio 等長
        if rr.returncode != 0:
            sys.exit(f"trim seg fail:\n{rr.stderr[-600:]}")
        tsegs.append(seg)
    concat(tsegs, out, segdir.parent)
    return {"trimmed": len(sils), "saved": round(saved, 2)}


def fmt_tc(t: float) -> str:
    return f"{int(t // 60):02d}:{t % 60:04.1f}"


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("edl")
    ap.add_argument("--out", required=True, help="final mp4 path")
    ap.add_argument("--speed", type=float, default=1.05)
    ap.add_argument("--rejects", action="store_true", help="出 NG 段串燒 preview")
    ap.add_argument("--tighten", type=float, default=0.0,
                    help="明確 opt-in：range 內部 silence ≥ 呢個秒數先壓縮（default 0 = off）")
    ap.add_argument("--global-trim", action="store_true",
                    help="明確 opt-in：自動壓短全片 silence；default off，避免誤食低聲粵語尾音")
    ap.add_argument("--keep-master", action="store_true")
    ap.add_argument("--encoder", choices=["videotoolbox", "libx264"], default="videotoolbox")
    ap.add_argument("--quality", choices=["preview", "rough"], default="preview",
                    help="rough = 近無損 H.265（seg 80M→final 50M）+ aac 256k 俾 CapCut 後製；preview = h264 12M")
    ap.add_argument("--audio-only", action="store_true",
                    help="proof render：只出 audio wav（秒級），刀位/snap/tighten/trim 同真 render 一致，俾殘留掃驗")
    punch_group = ap.add_mutually_exclusive_group()
    punch_group.add_argument("--punch", dest="punch", action="store_true", default=None,
                             help="交替 range 輕微放大（預設開）")
    punch_group.add_argument("--no-punch", dest="punch", action="store_false",
                             help="關閉交替放大")
    a = ap.parse_args()

    edl_path = Path(a.edl).expanduser()
    workdir = edl_path.parent
    segdir = workdir / "segments"
    segdir.mkdir(exist_ok=True)
    edl = json.loads(edl_path.read_text())
    src = list(edl["sources"].values())[0]
    src_dur = ffprobe_duration(src)
    src_width, src_height = ffprobe_size(src)
    amap = pick_audio_map(src)  # iPhone spatial audio 多 track → 揀可 decode 嘅 aac stream
    if amap:
        print(f"audio stream: {amap}（多 audio track，已避開 spatial/unknown）")
    lint(edl, src_dur)
    quality = a.quality if a.quality == "rough" else ("libx264" if a.encoder == "libx264" else "preview")
    seg_enc = encoder_args(quality, "seg")
    final_enc = encoder_args(quality, "final")
    abr = audio_bitrate(quality)
    warnings: list[str] = []
    edge_log: list[dict] = []
    tighten_log: list[dict] = []
    punch_cfg = CONFIG.get("punch", {})
    punch_enabled = bool(punch_cfg.get("enabled", True)) if a.punch is None else a.punch
    try:
        punch_zoom = float(punch_cfg.get("zoom", 1.15))
    except (TypeError, ValueError):
        sys.exit("config punch.zoom 要係數字")
    if punch_zoom < 1.0:
        sys.exit("config punch.zoom 唔可以細過 1.0")
    punch_active = (punch_enabled and punch_zoom > 1.0
                    and len(edl["ranges"]) > 1 and not a.audio_only)
    tone_map_prefix, source_color_classification, color_warnings = (
        ("", "audio_lane", []) if a.audio_only else source_visual_filter(src)
    )
    warnings.extend(color_warnings)
    if tone_map_prefix:
        warnings.append("HDR source 已用 canonical chain 轉 BT.709 一次；交付前仍要抽 2–3 格人眼睇膚色")

    print("detecting silences（只報告，唔自動落刀）…")
    sils = detect_silences(src, amap)
    print(f"{len(sils)} silence intervals（{SIL_NOISE}/{SIL_MIN}s）")

    # 逐段：只跟 EDL boundary + pad；silencedetect 永遠唔會靜靜改刀。
    segs: list[Path] = []
    cut_rows: list[dict] = []
    for i, r in enumerate(edl["ranges"], 1):
        # per-range pad override（NG 零唞氣硬切位用 pad 0）。
        pb, pa = r.get("pad_before", PAD_BEFORE), r.get("pad_after", PAD_AFTER)
        raw_in, raw_out = r["start"] - pb, r["end"] + pa
        cut_in = max(0.0, raw_in)
        cut_out = min(src_dur, raw_out)
        if cut_out - cut_in < MIN_RANGE:
            sys.exit(f"range {i} 加 pad 後短過 {MIN_RANGE}s — check EDL")
        # dropped 係 EDL 明示刀；tighten 只有 caller 明確 opt-in 先會郁。
        pieces = []
        for ks, ke in subtract_drops(cut_in, cut_out, r.get("dropped", [])):
            pieces += (split_on_internal_silences(ks, ke, sils, a.tighten,
                                                  tighten_log, str(i))
                       if a.tighten > 0 else [(ks, ke)])
        tag = f"（內壓 {len(pieces)-1} 個抖氣位）" if len(pieces) > 1 else ""
        print(f"extract {i}/{len(edl['ranges'])}  {fmt_tc(cut_in)}→{fmt_tc(cut_out)} {tag}")
        range_punch = punch_active and i % 2 == 0
        vf_punch = punch_filter(src_width, src_height, punch_zoom) if range_punch else ""
        for j, (ps, pe) in enumerate(pieces):
            ext = "wav" if a.audio_only else "mov"  # PCM audio → .mov（video）/ .wav（proof）
            seg = segdir / f"seg_{i:03d}_{j}.{ext}"
            extract(src, ps, pe, seg, seg_enc, abr=abr, vf_extra=vf_punch,
                    amap=amap, audio_only=a.audio_only, vf_prefix=tone_map_prefix)
            segs.append(seg)
        edge_log.append({"range": i, "in": [round(raw_in, 3), round(cut_in, 3)],
                         "out": [round(raw_out, 3), round(cut_out, 3)],
                         "source": "edl_plus_pad"})
        cut_rows.append({**r, "n": i, "cut_in": cut_in, "cut_out": cut_out,
                         "dur": sum(pe - ps for ps, pe in pieces),
                         "n_tighten": len(pieces) - 1})

    m_ext = "wav" if a.audio_only else "mov"
    master = workdir / f"cut_master.{m_ext}"  # PCM audio（無 AAC priming 累積）→ A/V 同步
    concat(segs, master, workdir)
    trim_info = {"trimmed": 0, "saved": 0.0}
    if a.global_trim:
        raw_mdur = ffprobe_duration(str(master))
        master_trim = workdir / f"cut_master_trim.{m_ext}"
        trim_info = trim_silences(
            str(master), master_trim, seg_enc, abr, raw_mdur, segdir,
            audio_only=a.audio_only, tag_bt709=bool(tone_map_prefix),
        )
        print(f"silence-trim（opt-in）：切咗 {trim_info['trimmed']} 個停頓, 慳 {trim_info['saved']}s")
        master = master_trim
    else:
        print("silence-trim: OFF（只報告；任何刪減先寫入 EDL）")
    master_dur = ffprobe_duration(str(master))

    # final pass：變速 + faststart（audio-only：直接 copy wav，proof 唔使變速）
    final = Path(a.out).expanduser()
    if a.audio_only:
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(master), "-c", "copy", str(final)])
    elif abs(a.speed - 1.0) < 1e-6:
        # master PCM .mov → video copy + audio aac + shortest 切齊（冇 silence-trim 嘅片
        # master 唔經 trim re-encode pass，video/audio 可能差 ~100ms，shortest 統一校正到 <30ms）
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(master),
                 "-c:v", "copy", "-c:a", "aac", "-b:a", abr,
                 "-shortest", "-movflags", "+faststart", str(final)])
    else:
        r = run(["ffmpeg", "-y", "-v", "error", "-i", str(master),
                 "-vf", f"setpts=PTS/{a.speed},fps=60", "-af", f"atempo={a.speed}",
                 *final_enc, *(BT709_TAG_ARGS if tone_map_prefix else []),
                 "-c:a", "aac", "-b:a", abr,
                 "-movflags", "+faststart", str(final)])
    if r.returncode != 0:
        sys.exit(f"final pass fail:\n{r.stderr[-800:]}")
    final_dur = ffprobe_duration(str(final))

    # rejects 串燒（complementary ranges，480p/30fps，burn source TC label）
    rejects_path = None
    if a.rejects and not a.audio_only:   # proof render 唔使 rejects（真 render 先出）
        bounds = [0.0] + [t for row in cut_rows for t in (row["cut_in"], row["cut_out"])] + [src_dur]
        gaps = [(bounds[j], bounds[j + 1]) for j in range(0, len(bounds), 2)
                if bounds[j + 1] - bounds[j] >= 0.4]
        rsegs = []
        for j, (gs, ge) in enumerate(gaps, 1):
            seg = segdir / f"rej_{j:03d}.mp4"
            extract(src, gs, ge, seg,
                    (["-c:v", "h264_videotoolbox", "-b:v", "2M"] if _MAC_VT
                     else ["-c:v", "libx264", "-crf", "30", "-preset", "ultrafast"]),
                    vf_extra="scale=480:854", acodec="aac",
                    label=f"REJ {j:02d} | src {fmt_tc(gs)}", amap=amap,
                    vf_prefix=tone_map_prefix)
            rsegs.append(seg)
        if rsegs:
            rejects_path = workdir / "rejects_preview.mp4"
            concat(rsegs, rejects_path, workdir)

    # QC + cut list
    expected_master = sum(row["dur"] for row in cut_rows)
    expected_final = expected_master / a.speed
    qc = {"sum_ranges_s": round(expected_master, 2),
          "master_s": round(master_dur, 2),
          "final_s": round(final_dur, 2),
          "expected_final_s": round(expected_final, 2),
          "master_delta_s": round(master_dur - expected_master, 2),
          "final_delta_s": round(final_dur - expected_final, 2),
          "speed": a.speed, "encoder": a.encoder,
          "punch": punch_active, "punch_zoom": punch_zoom,
          "source_color_classification": source_color_classification,
          "tone_map_applied": bool(tone_map_prefix),
          "tone_map_stage_count": 1 if tone_map_prefix else 0,
          "automatic_global_trim": bool(a.global_trim),
          "tighten_threshold": a.tighten,
          "tighten_saved_s": round(sum(t["saved_s"] for t in tighten_log), 2),
          "tighten_log": tighten_log,
          "edge_log": edge_log,
          "reported_silence_intervals": [[round(s, 3), round(e, 3)] for s, e in sils],
          "warnings": warnings}
    (workdir / "qc.json").write_text(json.dumps(qc, ensure_ascii=False, indent=1))

    lines = ["# Cut List", "",
             f"Source: `{src}`（{fmt_tc(src_dur)}）", "",
             "| # | Keep (source TC) | 長度 | Take | 內容 | 剪走 | ⚠ |",
             "|---|---|---|---|---|---|---|"]
    for row in cut_rows:
        dropped = "、".join(fmt_tc(d[0]) for d in row.get("dropped", [])) or "—"
        flag = row.get("note", "") if row.get("flag") else ""
        quote = row.get("quote", "")[:30]
        lines.append(f"| {row['n']} | {fmt_tc(row['cut_in'])}→{fmt_tc(row['cut_out'])} "
                     f"| {row['dur']:.1f}s | {row.get('take', '')} | {quote} | {dropped} | {flag} |")
    drop_total = src_dur - expected_master
    n_t = sum(row.get("n_tighten", 0) for row in cut_rows)
    saved = sum(t["saved_s"] for t in tighten_log)
    lines += ["", f"**原片 {fmt_tc(src_dur)} → 剪後 {fmt_tc(master_dur)} → "
              f"{a.speed}x 後 {fmt_tc(final_dur)}**（剪走 {fmt_tc(drop_total)}"
              f"{f'；內壓 {n_t} 個抖氣位慳 {saved:.1f}s' if n_t else ''}）", ""]
    if warnings:
        lines += ["## Warnings", *[f"- {w}" for w in warnings], ""]
    (workdir / "cut_list.md").write_text("\n".join(lines))

    if not a.keep_master:
        pass  # master 留喺 workdir（gitignored），janitor 30 日清

    print(f"\nfinal:   {final}（{fmt_tc(final_dur)}）")
    print(f"master:  {master}（{fmt_tc(master_dur)}）")
    if rejects_path:
        print(f"rejects: {rejects_path}")
    print(f"cutlist: {workdir / 'cut_list.md'}\nqc:      {workdir / 'qc.json'}")
    if warnings:
        print(f"\n⚠ {len(warnings)} warnings — 睇 qc.json")


if __name__ == "__main__":
    main()
