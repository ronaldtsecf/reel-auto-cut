#!/usr/bin/env bash
# reel_finish.sh — 一命令完成剪輯 → 素材包（EDL 確認後跑）
#
# Usage: reel_finish.sh <work_dir> [--ship] [--broll <broll_plan.json>]
# Requires: $WORK/edl.json（Step 3 出）+ raw video（edl sources 指向）
# Env:
#   GEMINI_API_KEY / GOOGLE_API_KEY  字幕清潔 + self-eval（舊 GOOGLE_AI_API_KEY 仍兼容）
#   JYUT_PY            指定 python（default：kit .venv 或 python3）
#   JYUT_PACK_DIR      素材包輸出 root（default：$WORK）
#   REEL_SPEED         變速（default 1.0）｜REEL_SHIP=1 出埋成品
# Output: $WORK/<slug>_pack/（rough cut + SRT + briefing + rejects[ + *_final if --ship]）

set -euo pipefail

WORK=$(realpath "${1:?Usage: reel_finish.sh <work_dir> [--ship] [--broll <plan.json>]}")
shift
SPEED="${REEL_SPEED:-1.0}"
SHIP="${REEL_SHIP:-0}"
BROLL_PLAN=""
while [ "$#" -gt 0 ]; do
    case "$1" in
        --ship|ship) SHIP=1; shift ;;
        --broll)
            [ "$#" -ge 2 ] || { echo "ERROR: --broll 後面要跟 broll_plan.json"; exit 1; }
            BROLL_PLAN="$2"; shift 2 ;;
        *) echo "ERROR: 唔識呢個 option: $1"; exit 1 ;;
    esac
done

# ── Paths（self-locate，唔 hardcode）──
KIT="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SK="$KIT/scripts"
if [ -n "${JYUT_PY:-}" ]; then PY="$JYUT_PY"
elif [ -x "$KIT/.venv/bin/python" ]; then PY="$KIT/.venv/bin/python"
else PY="python3"; fi
slug=$(basename "$WORK")
EDL="$WORK/edl.json"
GEMINI_KEY="${GOOGLE_API_KEY:-${GEMINI_API_KEY:-${GOOGLE_AI_API_KEY:-}}}"

[ -f "$EDL" ] || { echo "ERROR: $EDL not found（先寫 edl.json，Step 3）"; exit 1; }
[ -z "$BROLL_PLAN" ] || [ -f "$BROLL_PLAN" ] || {
    echo "ERROR: 搵唔到 B-roll plan: $BROLL_PLAN"; exit 1;
}

"$PY" "$SK/preflight.py"
"$PY" "$SK/proof_receipt.py" check "$WORK"

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
"$PY" "$SK/render_edl.py" "$EDL" --out "$ROUGHCUT" --quality rough --speed "$SPEED" --rejects
echo "   $(basename "$ROUGHCUT")"

if [ -n "$BROLL_PLAN" ]; then
    echo ""; echo "Step 4b · 疊 B-roll..."
    BROLLCUT="${ROUGHCUT%.mp4}_broll.mp4"
    BROLL_QC="${BROLLCUT%.mp4}_qc.json"
    TALKINGHEAD="${ROUGHCUT%.mp4}_talkinghead.mp4"
    "$PY" "$SK/render_broll.py" "$ROUGHCUT" "$BROLL_PLAN" -o "$BROLLCUT"
    mv -f "$ROUGHCUT" "$TALKINGHEAD"
    mv -f "$BROLLCUT" "$ROUGHCUT"
    [ -f "$BROLL_QC" ] || { echo "ERROR: B-roll QC receipt missing"; exit 2; }
    mv -f "$BROLL_QC" "$WORK/broll_qc.json"
    echo "   $(basename "$ROUGHCUT")（已疊 B-roll）"
fi

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
if [ -n "$GEMINI_KEY" ]; then
    "$PY" "$SK/clean_subtitle.py" "$WORK/final_stt" 2>&1 | grep -E "Glossary|Mode|Matched|Output|刪除|修正|篡改" || true
    CLEANED="$WORK/final_stt/${slug}_cleaned.srt"
    if [ -f "$CLEANED" ]; then
        cp "$CLEANED" "$WORK/${slug}_subtitles.srt"; echo "   cleaned → ${slug}_subtitles.srt"
    else
        echo "   cleaned 冇出 → 用 DRAFT"; cp "$WORK/${slug}_subtitles_DRAFT.srt" "$WORK/${slug}_subtitles.srt"
    fi
else
    echo "   冇 Gemini API key → 用 DRAFT（字幕未清潔；配 key 叻好多）"
    cp "$WORK/${slug}_subtitles_DRAFT.srt" "$WORK/${slug}_subtitles.srt"
fi

# ── Step 5f: self-eval + auto-filter（內部收斂）──
echo ""; echo "Step 5f · self-eval + auto-filter..."
CUTM=""
for c in "$WORK"/cut_master_trim.mov "$WORK"/cut_master.mov "$WORK"/cut_master.mp4; do
    [ -f "$c" ] && { CUTM="$c"; break; }
done
if [ -n "$GEMINI_KEY" ] && [ -n "$CUTM" ] && [ -f "$WORK/takes_packed.md" ]; then
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
CONFIG_PACK_ROOT=$(PYTHONPATH="$KIT/lib" "$PY" -c \
    'from pathlib import Path; from kit_config import CONFIG; v=CONFIG.get("output_dir"); print(Path(v).expanduser() if v else "")')
PACK_ROOT="${JYUT_PACK_DIR:-${CONFIG_PACK_ROOT:-$WORK}}"
PACK_DIR="$PACK_ROOT/${slug}_pack"
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
[ -f "$WORK/broll_qc.json" ] && cp "$WORK/broll_qc.json" "$PACK_DIR/" && echo "   broll_qc.json"

# ── Step 8（--ship）: 字幕燒入成品 ──
if [ "$SHIP" = "1" ]; then
    echo ""; echo "Step 8 · --ship 字幕燒入成品..."
    "$PY" "$SK/reel_render_final.py" "$WORK" --roughcut "$ROUGHCUT" --srt "$SRT_FOR_BRIEF" || {
        echo "   FINAL FAIL：成品規格未過，今次唔會報完成"
        exit 2
    }
    FINAL="${ROUGHCUT%_roughcut.mp4}_final.mp4"
    [ -f "$FINAL" ] || { echo "   FINAL FAIL：搵唔到 *_final.mp4"; exit 2; }
    FINAL_QC="${FINAL%.mp4}_qc.json"
    [ -f "$FINAL_QC" ] || { echo "   FINAL FAIL：搵唔到 *_final_qc.json"; exit 2; }
    cp "$FINAL" "$PACK_DIR/" && echo "   $(basename "$FINAL") 入素材包"
    cp "$FINAL_QC" "$PACK_DIR/" && echo "   $(basename "$FINAL_QC") 入素材包"
fi

echo ""
echo "=== 素材包 ready: $PACK_DIR ==="
if [ "$SHIP" = "1" ]; then
    echo "成品 *_final.mp4 技術 QC 已過；出街前仍要完整睇一次畫面、字幕同聲畫同步。"
else
    echo "CapCut import rough cut + SRT → 疊 B-roll；要一鍵成品 → reel_finish … --ship"
fi
