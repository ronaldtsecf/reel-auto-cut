#!/usr/bin/env bash
# 合成一條 10 秒測試片（唔使你有真片）— 驗 ffmpeg + whisper engine 裝好未。
set -e
OUT="${1:-test_clip.mp4}"
ffmpeg -y -v error \
    -f lavfi -i "testsrc=duration=10:size=1080x1920:rate=30" \
    -f lavfi -i "sine=frequency=440:duration=10" \
    -c:v libx264 -preset ultrafast -pix_fmt yuv420p -c:a aac "$OUT"
echo "合成咗 $OUT（10 秒 testsrc + tone）"
echo ""
echo "驗 engine（合成片冇真語音，文字會空/亂，純驗 whisper + ffmpeg chain 跑得通）："
echo "  python scripts/transcribe.py $OUT --out-dir /tmp/jyut-test"
