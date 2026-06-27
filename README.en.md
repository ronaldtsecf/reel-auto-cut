# reel-auto-cut (粵剪)

**An auto-editor for Cantonese talking-head IG reels, driven by an AI coding agent.**

You record yourself talking to camera (and inevitably fluff lines, repeat takes, ramble).
reel-auto-cut transcribes the footage, keeps the last clean take of each line, cuts the NG /
duplicate takes, and hands you a ready-to-import package: a rough cut + clean Cantonese
subtitles + a B-roll briefing. With `--ship` it also burns the subtitles in and renders a
finished file.

It is not a chatbot with a personality. It is a editing tool that happens to speak human:
it tells you the outcome in plain numbers (`3:24 → 1:34, dropped 7 repeat takes`), and
everything it cut goes into `rejects_preview.mp4` so you can verify in 30 seconds.

> 中文版（廣東話，default）：see [`README.md`](README.md).

---

## Who runs this

This kit is meant to be **operated by an AI coding agent**, not by you typing commands.
Two supported entry points:

- **Claude Code** (or any agent that reads files): point it at this folder. It reads
  `INSTRUCTIONS.md`, runs the pipeline, and only stops to ask you when there's a *real*
  decision (e.g. you said the same line two genuinely different ways).
- **Codex / ChatGPT** (upload-repo fallback): zip this repo, upload it, and use one prompt:
  > *"This is reel-auto-cut, a Cantonese reel auto-editor. Read INSTRUCTIONS.md and run the full
  > pipeline on the video I'm uploading. Follow it step by step; only ask me when there's a
  > genuine editing decision."*

You don't write the EDL or run ffmpeg by hand — the agent does. You drop in a video and
review the result.

---

## What you need (honest list)

| Requirement | Why | Notes |
|---|---|---|
| A terminal + this repo on disk | The agent runs scripts here | macOS / Linux / Windows |
| **Python 3.10+** | All scripts are Python | one `venv`, see Quick start |
| **ffmpeg** | cut / encode / extract audio | system install, NOT pip — `brew install ffmpeg` / `apt install ffmpeg` / `choco install ffmpeg` |
| **A free Gemini key** (`GOOGLE_AI_API_KEY`) | catches repeat takes Whisper silently merges, and cleans subtitles | Google AI Studio free tier, **no credit card**. See below — this is not optional in spirit. |
| Whisper engine | speech-to-text | auto-picked: **Apple Silicon Mac → mlx** (fast), **everything else → faster-whisper** (CPU/CUDA, cross-platform). You don't choose. |

### Why the Gemini key is not really optional

Whisper is the transcriber, but it has a blind spot: when you repeat a take, its language
model tends to *smooth the repetition away* — so the duplicate take never shows up in the
transcript, and the editor can't cut what it can't see. Gemini **listens to the audio** and
catches those repeats. Claude / GPT have no ears here; nothing in the agent replaces this.

Without a key the pipeline still runs, but **degraded**: silence-trim only, no take-dedup,
no subtitle cleanup. The kit will say so explicitly. The free tier is enough — get the key.

### Cantonese only

This kit transcribes with `whisper --language yue`. It is tuned for **Cantonese**
talking-head footage only. Mandarin / English / mixed-language footage is out of scope and
will give poor results. (If you want another language, you'd be forking, not configuring.)

---

## Quick start

```bash
# 1. Install Python deps into a local venv
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r requirements.txt    # faster-whisper + google-genai
# Apple Silicon Mac, want the fast path? also:
pip install -r requirements-mac.txt   # mlx-whisper (skip on non-Apple-Silicon)

# 2. Install ffmpeg (system, not pip)
brew install ffmpeg                 # macOS  (Linux: apt install ffmpeg · Windows: choco install ffmpeg)

# 3. Get a free Gemini key (Google AI Studio, no card) and export it
export GOOGLE_AI_API_KEY="your_key_here"

# 4. (Optional) brand / glossary config — defaults work, zero-config
cp config.example.json config.json   # edit accent colors, font, glossary if you want

# 5. Hand the video to your agent
#    Claude Code: open this folder, tell it to "run reel-auto-cut on my-clip.mov"
#    Codex/ChatGPT: upload the repo + the one-line prompt above
```

Then the agent drives the pipeline. After it shows you the EDL (the cut list) and you
confirm, the whole back half is **one command**:

```bash
bash reel_finish.sh <work_dir>          # rough cut + SRT + briefing + rejects
bash reel_finish.sh <work_dir> --ship   # ...plus a finished file with subtitles burned in
```

`config.json` is fully optional — every field has a default, so the **first video runs with
zero config**. Overrides you make (a glossary fix, a brand color) settle into `config.json`
and become your defaults next time.

---

## How it works

```
raw Cantonese footage
  → transcribe          (Whisper: mlx on Apple Silicon, faster-whisper elsewhere · --language yue)
  → pack_transcript     (lay takes out for the agent to read)
  → verify (Gemini)     (listen to audio, surface repeat takes Whisper merged away)
  → EDL                 (the agent picks the last clean take per line, drops NG/dupes → edl.json)
  ──────── you confirm the EDL here ────────
  → render rough cut    (videotoolbox on Mac, libx264 elsewhere · tighten pauses, A/V in sync)
  → re-transcribe the cut   (subtitle timing matches the actual edited video, not the source)
  → captions + draft SRT
  → clean subtitles (Gemini)   (audio-first cleanup into accurate Traditional Cantonese)
  → self-eval (Gemini) + auto-filter   (drops the model's own hallucinated findings)
  → briefing + QC
  → package             (rough cut + SRT + briefing + rejects_preview.mp4)
  → --ship: burn subtitles → finished *_final.mp4
```

Steps after the EDL confirmation all run from `reel_finish.sh` — one command, no babysitting.
The whole thing is designed to converge internally and only interrupt you for a genuine
editing call.

---

## Output

A `<slug>_pack/` folder containing:

- **`*_roughcut.mp4`** — the cut, ready to import into CapCut and layer B-roll on.
- **`*_subtitles.srt`** — clean Cantonese subtitles (cleaned if you had a Gemini key, draft if not).
- **`*_briefing.md`** — a B-roll briefing for the cut.
- **`rejects_preview.mp4`** — everything that got cut, so you can verify the edit in 30 seconds.
- **`*_final.mp4`** — only with `--ship`: subtitles burned in, ready to post or fine-tune.

---

## License / use

A free, public kit. Built by generalizing one creator's personal reel-editing pipeline so
Cantonese AI learners can run it themselves. Bring your own footage and your own free
Gemini key.
