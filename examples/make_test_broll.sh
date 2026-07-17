#!/usr/bin/env bash
# 合成 3 條 4 秒 B-roll + 1 張相，離線試配對同疊片。
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
OUT="${1:-$HERE/broll_sample}"
mkdir -p "$OUT"

ffmpeg -y -v error -f lavfi -i "color=c=#D94B4B:s=1280x720:r=30:d=4" \
    -vf "drawtext=text='LANDSCAPE':fontcolor=white:fontsize=84:x=(w-text_w)/2:y=(h-text_h)/2" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$OUT/landscape.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=#3976D9:s=720x1280:r=30:d=4" \
    -vf "drawtext=text='PORTRAIT':fontcolor=white:fontsize=72:x=(w-text_w)/2:y=(h-text_h)/2" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$OUT/portrait.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=#3BA66B:s=900x900:r=30:d=4" \
    -vf "drawtext=text='SQUARE':fontcolor=white:fontsize=76:x=(w-text_w)/2:y=(h-text_h)/2" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p "$OUT/square.mp4"
ffmpeg -y -v error -f lavfi -i "color=c=#E8B84A:s=1080x1920" \
    -vf "drawtext=text='STILL':fontcolor=black:fontsize=90:x=(w-text_w)/2:y=(h-text_h)/2" \
    -frames:v 1 -update 1 "$OUT/still.png"

echo "合成咗 3 條 B-roll 同 1 張相 → $OUT"
