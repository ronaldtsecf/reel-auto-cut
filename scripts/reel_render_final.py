#!/usr/bin/env python3
"""reel_render_final.py — Phase 2: 素材包 → 字幕燒入成品。

reel_finish.sh --ship 調用，或單獨跑。固化 RT66（2026-06-26）手砌嘅 video build：
  讀 WORK: *_roughcut.mp4 + *_subtitles.srt + selections.json（library slots）+ script.md（glossary）
  → SRT 轉 ASS（RT style + keyword 自動標色 heuristic）
  → ffmpeg: library B-roll cutaway 疊 + 字幕燒入
  → <stem>_完整版.mp4

Keyword heuristic（每句最多 1 個，避免濫）：① 強調詞 orange ② glossary 專名 cyan ③ 數字 cyan。
B-roll：只疊 selected-broll/ 已 copy 嘅 library slot（gap slot 留俾人手 / CapCut）。

Usage: reel_render_final.py <work_dir> [RT|TC]
"""
import sys
import re
import json
import platform
import subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from kit_config import CONFIG


def hex_to_ass(h, fallback="&H00FFFFFF&"):
    """#RRGGBB → ASS &H00BBGGRR&。"""
    h = (h or "").lstrip("#")
    if len(h) != 6:
        return fallback
    r, g, b = h[0:2], h[2:4], h[4:6]
    return f"&H00{b}{g}{r}&".upper()


def pick_vcodec():
    """Mac videotoolbox（快）/ 其他 libx264（跨平台）。"""
    if platform.system() == "Darwin":
        r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"], capture_output=True, text=True)
        if "h264_videotoolbox" in r.stdout:
            return ["-c:v", "h264_videotoolbox", "-b:v", "12M", "-tag:v", "avc1"]
    return ["-c:v", "libx264", "-preset", "medium", "-crf", "18", "-pix_fmt", "yuv420p"]


def _platform_font() -> str:
    """各平台預設中文 font（廣東話字幕要中文 font，唔可以用 Arial）。"""
    s = platform.system()
    if s == "Darwin":
        return "Hiragino Sans GB"
    if s == "Windows":
        return "Microsoft YaHei"
    return "Noto Sans CJK SC"


FONT = CONFIG["brand"].get("subtitle_font") or _platform_font()
CYAN = hex_to_ass(CONFIG["brand"].get("accent1"), "&H00FFE500&")    # neutral 白 → 唔標
ORANGE = hex_to_ass(CONFIG["brand"].get("accent2"), "&H000067FF&")
WHITE = "&H00FFFFFF&"
EMPHASIS = CONFIG["brand"].get("emphasis_words", [])               # 空 = 唔自動標 keyword


def ts_to_cs(t):  # "00:00:01,060" -> "0:00:01.06"
    h, m, rest = t.split(":")
    s, ms = rest.split(",")
    return f"{int(h)}:{m}:{s}.{ms[:2]}"


def mmss_to_sec(t):  # "00:09" or "01:27" -> seconds
    parts = t.split(":")
    if len(parts) == 2:
        return int(parts[0]) * 60 + int(parts[1])
    if len(parts) == 3:
        return int(parts[0]) * 3600 + int(parts[1]) * 60 + int(parts[2])
    return float(t)


def parse_srt(p):
    blocks = re.split(r"\n\n+", Path(p).read_text(encoding="utf-8").strip())
    out = []
    for b in blocks:
        ls = b.strip().split("\n")
        if len(ls) < 3:
            continue
        a, e = ls[1].split(" --> ")
        out.append({"start": a.strip(), "end": e.strip(), "text": " ".join(ls[2:]).strip()})
    return out


def extract_glossary(script_text):
    if not script_text:
        return []
    SW = {"the", "and", "for", "you", "not", "ground", "truth", "with",
          "this", "that", "script", "glossary"}
    toks = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[ .\-][A-Za-z0-9]+)*", script_text)
    seen = []
    for t in toks:
        t = t.strip()
        if len(t) < 2 or t.lower() in SW:
            continue
        if t not in seen:
            seen.append(t)
    return seen


def auto_keywords(text, glossary):
    """每句標最多 1 個 keyword。① 強調詞 orange ② glossary 專名 cyan ③ 數字 cyan。"""
    for pat in EMPHASIS:
        if pat in text:
            return [(pat, ORANGE)]
    for g in sorted(glossary, key=len, reverse=True):
        if g in text and len(g) >= 2:
            return [(g, CYAN)]
    m = re.search(r"\d+", text)
    if m:
        return [(m.group(), CYAN)]
    return []


def srt_to_ass(entries, glossary, ass_path):
    ev = []
    n_kw = 0
    for e in entries:
        txt = e["text"]
        for kw, col in auto_keywords(txt, glossary):
            if kw in txt:
                txt = txt.replace(kw, f"{{\\c{col}}}{kw}{{\\c{WHITE}}}", 1)
                n_kw += 1
        ev.append(f"Dialogue: 0,{ts_to_cs(e['start'])},{ts_to_cs(e['end'])},Default,,0,0,0,,{txt}")
    ass = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 2
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{FONT},72,&H00FFFFFF,&H00FFFFFF,&H00000000,&H64000000,-1,0,0,0,100,100,0.5,0,1,5,3,2,90,90,320,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
""" + "\n".join(ev)
    Path(ass_path).write_text(ass, encoding="utf-8")
    return len(ev), n_kw


def main():
    if len(sys.argv) < 2:
        print("Usage: reel_render_final.py <work_dir>")
        sys.exit(1)
    work = Path(sys.argv[1]).resolve()
    slug = work.name

    roughcut = next(iter(work.glob("*_roughcut.mp4")), None)
    if not roughcut:
        print("ERROR: 冇 *_roughcut.mp4 — 先跑 reel_finish")
        sys.exit(1)
    srt = work / f"{slug}_subtitles.srt"
    if not srt.exists():
        srt = next(iter(work.glob("*_subtitles.srt")), None)
    if not srt or not srt.exists():
        print("ERROR: 冇 *_subtitles.srt")
        sys.exit(1)

    script_text = (work / "script.md").read_text(encoding="utf-8").strip() if (work / "script.md").exists() else ""
    glossary = extract_glossary(script_text)
    selections = json.loads((work / "selections.json").read_text()) if (work / "selections.json").exists() else []

    print(f"roughcut: {roughcut.name}")
    print(f"SRT: {srt.name}  glossary: {len(glossary)} 個")

    # 1. SRT → ASS（keyword auto-highlight）
    ass_path = work / "_final.ass"
    n_ev, n_kw = srt_to_ass(parse_srt(srt), glossary, ass_path)
    print(f"ASS: {n_ev} 句, {n_kw} 個 keyword highlight")

    # 2. library B-roll slots（selected-broll/ 已 copy）→ cutaway overlay
    broll_dir = work / "selected-broll"
    lib_slots = []
    if broll_dir.exists():
        for s in selections:
            if s.get("mode") == "library":
                f = next(iter(broll_dir.glob(f"{s['slot_num']:03d}_*")), None)
                if f:
                    lib_slots.append((f, mmss_to_sec(s["timestamp"])))
    print(f"B-roll cutaway: {len(lib_slots)} 個 library slot（gap slot 留 CapCut）")

    # 3. ffmpeg filter_complex（cwd=work，ass 用相對 path 避開冒號跳脫）
    inputs = ["-i", roughcut.name]
    filters = []
    last = "0:v"
    for i, (f, start) in enumerate(lib_slots):
        inputs += ["-i", str(f)]
        end = start + 3.0
        idx = i + 1
        filters.append(
            f"[{idx}:v]trim=0:3.2,setpts=PTS-STARTPTS+{start}/TB,"
            f"scale=1080:1920:force_original_aspect_ratio=increase,crop=1080:1920[bl{i}]"
        )
        filters.append(f"[{last}][bl{i}]overlay=enable='between(t,{start},{end})':eof_action=pass[ov{i}]")
        last = f"ov{i}"
    filters.append(f"[{last}]subtitles=_final.ass[v]")
    filter_complex = ";".join(filters)

    stem = re.sub(r"_roughcut$", "", roughcut.stem)
    out = work / f"{stem}_final.mp4"
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs,
           "-filter_complex", filter_complex,
           "-map", "[v]", "-map", "0:a",
           *pick_vcodec(),
           "-c:a", "aac", "-b:a", "192k", out.name]
    print(f"render → {out.name} ...")
    r = subprocess.run(cmd, cwd=str(work), capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR ffmpeg:\n{r.stderr[-800:]}")
        sys.exit(1)
    print(f"done: {out.name}")
    print(str(out))


if __name__ == "__main__":
    main()
