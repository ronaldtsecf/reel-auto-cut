# examples — zero-asset 試跑

冇真片都試到個 pipeline 裝好未。

## 合成測試片
```
bash examples/make_test_clip.sh
```
出 `test_clip.mp4`（10 秒 testsrc + tone，唔使你有素材）。

## 驗 whisper engine
```
python scripts/transcribe.py test_clip.mp4 --out-dir /tmp/jyut-test
```
跑得通 = whisper engine（Mac mlx / 其他 faster-whisper）裝好。
合成片冇真語音，出嚟文字會空/亂，正常 — 呢步淨係驗 engine load + ffmpeg chain。

## 真正剪你自己條片
睇 `INSTRUCTIONS.md`（AI agent 入口）同 `SETUP.md`（裝機）。
