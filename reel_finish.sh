#!/usr/bin/env bash
# reel_finish.sh — 一命令完成剪輯 → 素材包（EDL 確認後跑）
#
# Usage: reel_finish.sh <work_dir> [--ship]
# Requires: $WORK/edl.json（Step 3 出）+ raw video（edl sources 指向）
# Env:
#   GOOGLE_AI_API_KEY  字幕清潔 + self-eval（free key，唔設就 degraded）
#   JYUT_PY            指定 python（default：kit .venv 或 python3）
#   JYUT_PACK_DIR      素材包輸出 root（default：$WORK）
#   REEL_SPEED         變速（default 1.0）｜REEL_SHIP=1 出埋成品
# Output: $WORK/<slug>_pack/（rough cut + SRT + briefing + rejects[ + *_final if --ship]）

set -euo pipefail

WORK=$(realpath "${1:?Usage: reel_finish.sh <work_dir> [--ship]}")
SPEED="${REEL_SPEED:-1.0}"
SHIP="${REEL_SHIP:-0}"
case "${2:-}" in --ship|ship) SHIP=1 ;; esac

# ── Paths（self-locate，唔 hardcode）──
KIT="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SK="$KIT/scripts"
if [ -n "${JYUT_PY:-}" ]; then PY="$JYUT_PY"
elif [ -x "$KIT/.venv/bin/python" ]; then PY="$KIT/.venv/bin/python"
else PY="python3"; fi
slug=$(basename "$WORK")
EDL="$WORK/edl.json"

[ -f "$EDL" ] || { echo "ERROR: $EDL not found（先寫 edl.json，Step 3）"; exit 1; }

echo ""
echo "=== jyut-cut · $slug ==="

# ── output path from EDL sources ──
ROUGHCUT=$(WORK="$WORK" "$PY" - "$EDL" << 'PYEOF'
import json, re, sys, os
from pathlib import Path
edl = json.load(open(sys.argv[1]))
src = next(iter(edl.get("sources", {}).values()), "")
work = os.environ["WORK"]
if src:
    p = Path(src)
    stem = re.sub(r"[_-]*raw$", "", p.stem, flags=re.IGNORECASE).rstrip(" —-")
    print(os.path.join(work, f"{stem}_roughcut.mp4"))
else:
    print(os.path.join(work, "roughcut.mp4"))
PYEOF
)

# ── Step 4: Render rough cut ──
echo ""; echo "Step 4 · Render rough cut..."
"$PY" "$SK/render_edl.py" "$EDL" --out "$ROUGHCUT" --quality rough --speed "$SPEED" --rejects --tighten 0.20
echo "   $(basename "$ROUGHCUT")"

PAUSE_N=$(ffmpeg -hide_banner -i "$ROUGHCUT" -af silencedetect=noise=-30dB:d=0.3 -f null - 2>&1 | grep -c silence_start || true)
echo "   QC · >0.3s 停頓 ${PAUSE_N} 個（理想 ≤3）"

# ── Step 5a: Re-transcribe final（timing 對真片）──
echo ""; echo "Step 5a · Re-transcribe final video..."
"$PY" "$SK/transcribe.py" "$ROUGHCUT" --out-dir "$WORK/final_stt"

# ── Step 5b-c: captions + draft SRT ──
echo ""; echo "Step 5b-c · captions + draft SRT..."
"$PY" "$SK/gen_captions.py" "$WORK/final_stt/transcript.json" -o "$WORK/captions.json"
"$PY" "$SK/gen_srt.py" "$WORK/captions.json" --speed 1.0 -o "$WORK/${slug}_subtitles_DRAFT.srt"

# ── Step 5d: extract mp3（字幕清潔用）──
ffmpeg -y -v error -i "$ROUGHCUT" -vn -c:a libmp3lame -q:a 4 "$WORK/final_stt/audio.mp3"
cp "$WORK/${slug}_subtitles_DRAFT.srt" "$WORK/final_stt/${slug}.srt"

# ── Step 5e: 字幕清潔（audio-first，要 Gemini key）──
echo ""; echo "Step 5e · 字幕清潔..."
if [ -n "${GOOGLE_AI_API_KEY:-}" ]; then
    "$PY" "$SK/clean_subtitle.py" "$WORK/final_stt" 2>&1 | grep -E "Glossary|Mode|Matched|Output|刪除|修正|篡改" || true
    CLEANED="$WORK/final_stt/${slug}_cleaned.srt"
    if [ -f "$CLEANED" ]; then
        cp "$CLEANED" "$WORK/${slug}_subtitles.srt"; echo "   cleaned → ${slug}_subtitles.srt"
    else
        echo "   cleaned 冇出 → 用 DRAFT"; cp "$WORK/${slug}_subtitles_DRAFT.srt" "$WORK/${slug}_subtitles.srt"
    fi
else
    echo "   冇 GOOGLE_AI_API_KEY → 用 DRAFT（字幕未清潔；配 free key 叻好多）"
    cp "$WORK/${slug}_subtitles_DRAFT.srt" "$WORK/${slug}_subtitles.srt"
fi

# ── Step 5f: self-eval + auto-filter（內部收斂）──
echo ""; echo "Step 5f · self-eval + auto-filter..."
CUTM=""
for c in "$WORK"/cut_master_trim.mov "$WORK"/cut_master.mov "$WORK"/cut_master.mp4; do
    [ -f "$c" ] && { CUTM="$c"; break; }
done
if [ -n "${GOOGLE_AI_API_KEY:-}" ] && [ -n "$CUTM" ] && [ -f "$WORK/takes_packed.md" ]; then
    if "$PY" "$SK/verify_takes_gemini.py" "$CUTM" "$WORK/takes_packed.md" -o "$WORK/gemini_selfeval.json" >/dev/null 2>&1; then
        "$PY" "$SK/filter_selfeval.py" "$WORK" || true
        echo "   （real → 改 edl 重跑｜needs_micro → 顯微｜reject → 無視）"
    else
        echo "   self-eval Gemini 失敗（quota？）→ 手動補"
    fi
else
    echo "   skip self-eval（缺 key / cut_master / takes_packed.md）"
fi

# ── Step 6: briefing + QC ──
echo ""; echo "Step 6 · briefing..."
SRT_FOR_BRIEF="$WORK/${slug}_subtitles.srt"
[ -f "$SRT_FOR_BRIEF" ] || SRT_FOR_BRIEF="$WORK/${slug}_subtitles_DRAFT.srt"
"$PY" "$SK/gen_briefing.py" "$EDL" --srt "$SRT_FOR_BRIEF" -o "$WORK/${slug}_briefing.md"

echo ""; echo "Step 6c · 自動 QC..."
"$PY" "$SK/qc_check.py" "$WORK" || true

# ── Step 7: 素材包 ──
PACK_DIR="${JYUT_PACK_DIR:-$WORK}/${slug}_pack"
mkdir -p "$PACK_DIR"
echo ""; echo "Step 7 · 素材包 → $PACK_DIR"
[ -f "$ROUGHCUT" ] && cp "$ROUGHCUT" "$PACK_DIR/" && echo "   $(basename "$ROUGHCUT")"
if [ -f "$WORK/${slug}_subtitles.srt" ]; then
    cp "$WORK/${slug}_subtitles.srt" "$PACK_DIR/" && echo "   ${slug}_subtitles.srt"
elif [ -f "$WORK/${slug}_subtitles_DRAFT.srt" ]; then
    cp "$WORK/${slug}_subtitles_DRAFT.srt" "$PACK_DIR/" && echo "   ${slug}_subtitles_DRAFT.srt（文字待修）"
fi
[ -f "$WORK/${slug}_briefing.md" ] && cp "$WORK/${slug}_briefing.md" "$PACK_DIR/" && echo "   ${slug}_briefing.md"
[ -f "$WORK/rejects_preview.mp4" ] && cp "$WORK/rejects_preview.mp4" "$PACK_DIR/" && echo "   rejects_preview.mp4（NG 確認用）"

# ── Step 8（--ship）: 字幕燒入成品 ──
if [ "$SHIP" = "1" ]; then
    echo ""; echo "Step 8 · --ship 字幕燒入成品..."
    if "$PY" "$SK/reel_render_final.py" "$WORK"; then
        FINAL=$(ls "$WORK"/*_final.mp4 2>/dev/null | head -1)
        [ -f "$FINAL" ] && cp "$FINAL" "$PACK_DIR/" && echo "   $(basename "$FINAL") 入素材包"
    else
        echo "   reel_render_final 失敗，素材包照出"
    fi
fi

echo ""
echo "=== 素材包 ready: $PACK_DIR ==="
if [ "$SHIP" = "1" ]; then
    echo "成品 *_final.mp4 已出（字幕燒入）。可直接出街或 CapCut 微調。"
else
    echo "CapCut import rough cut + SRT → 疊 B-roll；要一鍵成品 → reel_finish … --ship"
fi
