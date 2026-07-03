#!/usr/bin/env bash
# proof_check.sh — 先驗聲後出片
#
# 出 edl.json 之後、render 真片之前跑：audio-only proof render（秒級）→ 聽寫 →
# 殘留掃描。有殘留就改 edl.json 再 proof（~1 分鐘/輪），全綠先跑 reel_finish
# render 真片（每輪 video render 要 8-10 分鐘 — 剪聲快過剪片幾十倍）。
#
# Usage: proof_check.sh <work_dir>
# 需要:  <work_dir>/edl.json
# 出:    proof.wav + proof_stt/ + proof_pass marker（PASS 先有）
# Exit:  0 = PASS 可 render 真片；2 = 有高危殘留，改 EDL 再 proof
#
# 判過係 intentional 嘅 repeat（排比 refrain／疊詞）→ 寫入 <work_dir>/proof_allow.txt
# （每行一個 substring），re-run 即白名單放行。

set -euo pipefail
WORK=$(realpath "${1:?Usage: proof_check.sh <work_dir>}")
KIT="$(cd "$(dirname "$(realpath "$0")")" && pwd)"
SK="$KIT/scripts"
if [ -n "${JYUT_PY:-}" ]; then PY="$JYUT_PY"
elif [ -x "$KIT/.venv/bin/python" ]; then PY="$KIT/.venv/bin/python"
else PY="python3"; fi

echo "▶ proof render（audio-only，刀位同真 render 一致）..."
"$PY" "$SK/render_edl.py" "$WORK/edl.json" --out "$WORK/proof.wav" \
    --quality rough --tighten 0.20 --audio-only 2>&1 | grep -E "silence-trim|final:" || true

echo "▶ transcribe proof..."
"$PY" "$SK/transcribe.py" "$WORK/proof.wav" --out-dir "$WORK/proof_stt" 2>&1 | tail -1

echo "▶ 殘留掃描（5/4-gram，deterministic）..."
SCAN_RC=0
ALLOW_ARGS=()
[ -f "$WORK/proof_allow.txt" ] && ALLOW_ARGS=(--allow "$WORK/proof_allow.txt")
"$PY" "$SK/repeat_scan.py" "$WORK/proof_stt/transcript.json" "${ALLOW_ARGS[@]}" || SCAN_RC=$?
# 注：proof 階段特登唔跑 Gemini —— 幻覺率高要 by-content 核先信，而 by-content 核
# 就係上面殘留掃本身；Gemini 崗位喺 Step 3（source 驗）+ 真 render 後自驗（照舊）。

echo ""
if [ "$SCAN_RC" = "0" ]; then
    touch "$WORK/proof_pass"
    echo "═══ PROOF PASS — 開綠燈，可以 reel_finish render 真片 ═══"
else
    rm -f "$WORK/proof_pass"
    echo "═══ PROOF 有高危殘留 — 改 edl.json 再跑 proof，唔好 render 住 ═══"
    exit 2
fi
