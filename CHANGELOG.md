# Changelog

## 0.2.0 — Production-safety refresh

### Added

- HLG／PQ source detection and exactly-one HDR→BT.709 conversion.
- `scripts/preflight.py` for Python, FFmpeg, model packages, HDR filters, subtitle font, Gemini key, and disk checks.
- Digest-bound `proof_pass.json`; any EDL, source, proof-audio, or proof-transcript change invalidates the old pass.
- Final-output receipt verifying 1080×1920, 60fps, 8-bit BT.709, and one audio stream.
- B-roll colour routing and `broll_qc.json`, including HDR→BT.709 checks for each selected asset.
- Regression tests for colour routing, cache identity, proof invalidation, per-segment fades, and final specs.

### Changed

- Transcription cache identity now uses source-content SHA-256 instead of path／size／mtime.
- B-roll visual-index cache also uses content SHA-256; old size／mtime entries refresh once.
- Silence detection is report-only by default. It no longer moves EDL boundaries or removes low-volume speech automatically.
- Traditional-Chinese subtitle defaults now use PingFang TC／Microsoft JhengHei／Noto Sans CJK TC by platform.
- Setup now includes exact clone, update, reinstall, and strict preflight commands.
- New installs use the documented `GEMINI_API_KEY`／`GOOGLE_API_KEY`; the old `GOOGLE_AI_API_KEY` remains compatible.

### Upgrade note

Run `git pull --ff-only`, update the Python requirements, then run
`python scripts/preflight.py --strict`. Existing projects must rerun
`proof_check.sh` once to create the new bound proof receipt.
