# reel-auto-cut — Auto-editor for Cantonese talking-head reels

> ⭐ Beginner-friendly｜~10 min one-time setup｜**Mac best-tested, Windows / Linux experimental**
> Drop in one raw talking-head clip; an AI agent cuts the NG / duplicate takes, cleans the subtitles, and hands you a finished package.

中文版（廣東話，default）：see [`README.md`](README.md).

---

## 📌 What problem this solves

You read your script to camera, and every time a line doesn't come out clean you re-record it — one sentence shot three or four times, and you only want the last good take. But hunting through a full 10-plus-minute clip by hand, finding which take is good, cutting the NGs, tightening the breath pauses... is soul-crushing.

reel-auto-cut **hands that job to an AI agent**: you drop the clip on your AI assistant (Claude or Codex), and it finds every repeat, cuts the NGs, generates clean subtitles, and hands you back an edited package.

**You don't need to know how to code, and you don't type commands yourself** — set it up once, then just drop clips on the AI.

## ✨ What you get

- An **edited cut**: NGs, flubs, and duplicate takes all removed, leaving only your best takes.
- **Automatic punch-ins**: select moments get a subtle zoom (a cut-out effect) that both hides the jump at each edit point and adds rhythm — no manual keyframing, on by default, and one flag turns it off if you don't want it.
- **Automatic B-roll matching**: got your own footage (cut-aways, demo clips, screen recordings)? The AI reads what you're saying and drops the right B-roll onto the matching moments. No footage? It's skipped automatically — nothing else changes.
- A **subtitle file** (`.srt`): matching what you actually said, not the script.
- A **ready-to-post finished clip** (final video): subtitles burned in, punch-ins and B-roll all baked in, output as `_final.mp4` in one shot — no need to open any editing app.
- A **"here's what I cut" preview clip**: don't trust the AI's edit? Scrub it for 30 seconds and you'll know — no blind faith required.

## 🔄 How it works (the full flow)

```
you drop in one raw talking-head clip
        │
        ▼
  ① transcribe    whisper turns your voice into word-level timecodes
        │
        ▼
  ② catch repeats Gemini listens to the audio, surfacing repeat takes whisper merged away
        │
        ▼
  ③ decide cuts   the AI reads it all, keeps the last clean take per line, drops the NGs
        │
        ▼
  ④ cut + punch   assembles the cut, adding punch-ins (cut-out zooms) to hide edits and add rhythm
        │
        ▼
  ⑤ (optional) B-roll  the AI reads what you're saying and overlays your footage on the matching spots
        │
        ▼
  ⑥ one-shot pack edited cut + subtitles + B-roll briefing + "what got cut" preview
        │
        ▼
  ⑦ (optional) ship  subtitles burned in, punch-ins + B-roll all baked in, output ready to post
```

Under the hood it's `whisper` (the transcriber) + `Gemini` (the AI that catches repeats by ear and matches B-roll) + `ffmpeg` (the cutting tool). **Fully automated — you never touch any interface.**

## 🚀 How to use it (3 steps)

1. **Set up your environment** (one-time, ~10 min) → follow [SETUP.md](SETUP.md), or just hand it to the AI and ask it to install everything for you.
2. **Drop your clip on your AI assistant** — open Claude Code inside the `reel-auto-cut` folder (or hand the repo link to OpenAI Codex) and say:
   > I have a talking-head clip at `~/Desktop/my_reel.mp4`, edit it with reel-auto-cut.
3. The AI reads [INSTRUCTIONS.md](INSTRUCTIONS.md) and runs it. **The first run won't pester you — it uses defaults throughout**; it only stops to ask when there's a real decision (e.g. you said the same line two genuinely different ways).

## 📋 What you need to prepare

**Must-have (won't run without these):**
- A computer (Mac / Windows / Linux) + knowing how to open a "Terminal" (Mac) or "PowerShell" (Windows) — don't know how? Ask the AI to walk you through it step by step.
- `Python` and `ffmpeg` (two free tools, for processing video and running the scripts) — SETUP shows you how, or ask the AI to install them for you.
- A **free Gemini key** (create one at [Google AI Studio](https://aistudio.google.com/apikey) — no payment, no credit card).

**Optional (nice to have):**
- An Apple Silicon Mac (M1 and later) → automatically uses `mlx` acceleration, much faster; without it you run `faster-whisper`, slightly slower but works just the same.
- A folder of your own B-roll footage (clips you shot yourself, screen recordings, demo footage, etc.) → only needed if you want the AI to auto-match B-roll; skip it and everything else still runs.

> 🤖 **Why is the Gemini key required?** `whisper` (the transcriber) has a blind spot: when you NG and re-record the same line, it often treats it as if you only said it once and misses the repeat. `Gemini` actually **listens to the audio** and catches all those repeat takes — this is the soul of the whole kit. Without it, this degrades into a plain silence-trimmer, of which there are plenty of free apps; not worth using this kit for that. So this key is non-negotiable (but it's free).

## 🌐 No Claude Code? OpenAI Codex works too

Hand the whole repo (or the repo link) to Claude / OpenAI Codex and say:

> This is a Cantonese reel auto-editor kit. Read INSTRUCTIONS.md and run it with me step by step — starting from the raw clip I'm dropping in.

⚠️ Plain ChatGPT (web / mobile app) can't run commands on your machine, so it won't work — use the [Codex app](https://openai.com/codex) (desktop, included with ChatGPT Plus).

## ⚠️ Stated limitations

- **Cantonese only** (transcription is set to `yue`). Other languages require forking, not configuring.
- **Best-tested on Mac** (the developer's primary platform). Windows / Linux have cross-platform engine + encoder support and should work in theory, but aren't yet fully tested on real hardware — treat them as experimental, and please open an issue if you hit problems.
- Mac runs `mlx` fastest; Windows / Linux run `faster-whisper` — without a GPU, a few-minute clip can take a few minutes to process, so be a little patient.

## License

[MIT](LICENSE) — use, modify, and sell it freely; just credit the source.

Cantonese version: [README.md](README.md). Find it useful? Drop a star ⭐
