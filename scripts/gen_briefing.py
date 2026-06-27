#!/usr/bin/env python3
"""
Generate 後製 briefing.md — CapCut 後製指引。

Input:
  edl.json            — rough cut duration + source slug
  --selections <path> — B-roll 選取（library / gap modes）
  --srt <path>        — 字幕數 count（optional）
  --identity RT|TC    — RT design system vs TC（default RT）

Output: briefing.md with:
  - 素材包 table
  - B-roll placement timeline table（含 gap 標注）
  - Library gap sourcing section
  - Effects cheat sheet（RT design system）
  - 後製 tips

Usage:
    gen_briefing.py <edl.json> [--selections <path>] [--srt <path>] [-o briefing.md]
"""

import argparse
import json
import re
from datetime import datetime
from pathlib import Path


def fmt_ts(seconds: float) -> str:
    """Float seconds → MM:SS."""
    m = int(seconds // 60)
    s = int(seconds % 60)
    return f"{m:02d}:{s:02d}"


def safe_label(label: str) -> str:
    """Label → 安全檔名（去標點/空格，保留中英數）。"""
    return re.sub(r"[^\w一-鿿㐀-䶿-]", "", label.replace(" ", "-"))


def infer_effect(label: str, beat: str, slot_num: int) -> str:
    """Heuristic: 由 label/beat 推 CapCut 特效建議。"""
    combined = (label + " " + beat).lower()
    if any(c.isdigit() for c in (label + beat)[:15]) or "%" in combined:
        return "kinetic 數字彈大"
    if slot_num == 1 or "hook" in combined:
        return "punch-in 1.25x"
    if "介面" in combined or "demo" in combined or "screen" in combined or "claude" in combined or "app" in combined:
        return "inset（手機框）"
    if "stage" in combined or "演講" in combined or "ceo" in combined or "舞台" in combined:
        return "inset 氛圍"
    if "office" in combined or "專注" in combined or "做嘢" in combined:
        return "inset 低調"
    return "inset 彈入"


def count_srt(srt_path) -> int:
    if not srt_path:
        return 0
    p = Path(srt_path)
    if not p.exists():
        return 0
    text = p.read_text(encoding="utf-8")
    return len([x for x in text.split("\n\n") if x.strip() and x.strip()[0].isdigit()])


def get_durations(edl: dict, edl_path: Path, speed: float) -> tuple[float, float]:
    """Return (pre_speed_master_s, post_speed_final_s).

    優先讀 render 出嘅 qc.json（真實 duration，已含 pad/snap/tighten）；
    冇就 fallback EDL ranges sum（粗估，會偏短 ~2s 因唔計 pad）。
    """
    qc = edl_path.parent / "qc.json"
    if qc.exists():
        try:
            d = json.loads(qc.read_text())
            master = d.get("master_s")
            final = d.get("final_s")
            if master and final:
                return float(master), float(final)
        except Exception:
            pass
    total = sum(float(r["end"]) - float(r["start"]) for r in edl.get("ranges", []))
    return total, total / speed


def get_rough_cut_name(edl: dict) -> str:
    """Derive roughcut filename from EDL source path."""
    sources = edl.get("sources", {})
    src = next(iter(sources.values()), "")
    if not src:
        return "roughcut.mp4"
    stem = Path(src).stem
    stem = re.sub(r"[_-]*raw$", "", stem, flags=re.IGNORECASE)
    stem = stem.rstrip(" —-")
    return f"{stem}_roughcut.mp4"


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("edl", help="edl.json path")
    ap.add_argument("--selections", default=None, help="selections.json path")
    ap.add_argument("--srt", default=None, help="SRT file for subtitle count")
    ap.add_argument("-o", "--output", default=None, help="output briefing.md path")
    args = ap.parse_args()

    edl_path = Path(args.edl)
    edl = json.loads(edl_path.read_text())
    slug = edl_path.parent.name

    # Duration & timing — 真實 qc.json 優先
    SPEED = 1.0   # 變速 default off（align reel_finish REEL_SPEED default；qc.json 有真 duration 時唔靠呢個）
    cut_dur, speed_dur = get_durations(edl, edl_path, SPEED)
    n_ranges = len(edl.get("ranges", []))

    # SRT
    srt_count = count_srt(args.srt)

    # Selections
    selections = []
    if args.selections and Path(args.selections).exists():
        selections = json.loads(Path(args.selections).read_text())
        selections.sort(key=lambda s: s.get("slot_num", 0))

    # Output filenames
    roughcut_name = get_rough_cut_name(edl)
    srt_name = f"{slug}_subtitles.srt"
    briefing_name = f"{slug}_briefing.md"

    n_library = sum(1 for s in selections if s.get("mode", "library") not in ("gap", "higgsfield"))
    n_higgsfield = sum(1 for s in selections if "higgsfield" in s.get("mode", ""))
    n_gap = sum(1 for s in selections if s.get("mode") == "gap")
    n_broll = n_library + n_higgsfield

    # Brand accent from config（neutral 白 default，唔自動標品牌色）
    import sys as _sys
    _sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
    from kit_config import CONFIG
    accent1 = CONFIG["brand"]["accent1"]
    accent2 = CONFIG["brand"]["accent2"]

    # ── Build B-roll timeline rows ──
    broll_rows = []
    gap_details = []

    for sel in selections:
        ts = sel.get("timestamp", "??:??")
        slot_num = sel.get("slot_num", 0)
        label = sel.get("label", "")
        beat = sel.get("_beat", label)
        mode = sel.get("mode", "library")
        src_ext = Path(sel.get("source_path", "")).suffix if sel.get("source_path") else ".mp4"

        if mode == "gap":
            desired = sel.get("desired", "未知")
            broll_rows.append(f"| **{ts}** | **{beat}** | **缺 — 需補** | — |")
            gap_details.append({
                "slot_num": slot_num,
                "timestamp": ts,
                "desired": desired,
                "search": sel.get("search", ""),
            })
        elif "higgsfield" in mode:
            fname = f"`{slot_num:03d}_{ts.replace(':','-')}_GEN.mp4`（待 Higgsfield 生成）"
            broll_rows.append(f"| {ts} | {beat} | {fname} | {infer_effect(label, beat, slot_num)} |")
        else:
            fname_stem = safe_label(label) if label else f"slot{slot_num:03d}"
            fname = f"`{slot_num:03d}_{ts.replace(':','-')}_{fname_stem}{src_ext}`"
            broll_rows.append(f"| {ts} | {beat} | {fname} | {infer_effect(label, beat, slot_num)} |")

    # ── Assemble markdown ──
    cta_start = fmt_ts(max(0, speed_dur - 15))
    title = slug.upper()

    lines = [
        f"# {title} 後製 Briefing",
        "",
        f"> reel-cut 做晒粗重功夫，呢份係你（或剪片 TA）喺 **CapCut / 剪映** 落手後製嘅指引。",
        f"> Rough cut 已經劈走 NG/重複 take + 收緊抖氣位（{n_ranges} 段 → {fmt_ts(speed_dur)}），乾淨緊湊。",
        f"> 你淨係要：疊 B-roll + 加字幕 + 加特效，就出得街。",
        "",
        "## 素材包（全部喺呢個 folder）",
        "",
        "| # | 檔案 | 用途 |",
        "|---|------|------|",
        f"| 1 | `{roughcut_name}` | 主片（HEVC 50Mbps 近無損 · 1080×1920 · {fmt_ts(speed_dur)}）— import 做底 |",
        f"| 2 | `{srt_name}` | 字幕（{srt_count if srt_count else '?'} 句，timing 已對 rough cut）— import 即對位 |",
        f"| 3 | `selected-broll/` ×{n_broll} | B-roll，**檔名 = 時間碼 + 內容描述**（睇得明邊條打邊條）|",
        f"| 4 | `{briefing_name}` | 呢份 |",
        "",
        "## 後製流程（3 步）",
        "",
        "1. **Import** rough cut + SRT → CapCut 自動上字幕（timing 已啱）",
        "2. **疊 B-roll** → 跟下面 table，B-roll 放 overlay track（建議 inset 細框 PIP，唔好全蓋你講嘢）",
        "3. **加特效** → 跟特效 cheat sheet（克制先專業）",
        "",
    ]

    # B-roll timeline table
    broll_header = f"## B-roll 放置 Timeline（{n_broll} 條"
    if n_gap:
        broll_header += f" + {n_gap} 個缺口"
    broll_header += "）"
    lines.append(broll_header)
    lines.append("")
    lines.append("> 全部 B-roll 唔重複，檔名自帶時間碼 + 描述。inset 建議圓角細白邊。")
    lines.append("")
    lines.append("| 時間碼 | 講緊咩 | B-roll | 特效 |")
    lines.append("|--------|--------|-----------|--------|")
    lines.append(f"| 00:00–00:06 | Hook 開場 | — | 字幕關鍵詞放大變 {accent1.split(' ')[0]} |")

    lines.extend(broll_rows)

    lines.append(f"| {cta_start}–{fmt_ts(speed_dur)} | CTA 收尾 | — | **保持 talking head**（CTA 唔好 B-roll 搶）|")
    lines.append("")

    # Gap section
    if gap_details:
        lines.append("## B-roll 缺口（library 冇，要補）")
        lines.append("")
        lines.append("| Slot | 要嘅題材 | 補片選項 |")
        lines.append("|------|---------|---------|")
        for g in gap_details:
            search_hint = f'Pexels 搜「{g["search"]}」' if g.get("search") else "上網 stock（Pexels/Pixabay）"
            desired_short = g["desired"][:40] + ("…" if len(g["desired"]) > 40 else "")
            lines.append(
                f"| {g['timestamp']} | {desired_short} "
                f"| ① {search_hint} ② 補錄 screen recording ③ 重用現有素材 |"
            )
        lines.append("")
        lines.append(
            "> 下次一條龍自動：library 揀唔到 → 上網搵真 stock（唔用 AI 生成，跟 no-AI rule）。"
        )
        lines.append("")

    if not selections:
        lines.append("> **B-roll 待揀**：跑 `/broll-match` 後重新 generate briefing（`reel_finish.sh`）。")
        lines.append("")

    # Effects cheat sheet (static, RT-tuned)
    lines.extend([
        "## 特效 cheat sheet（CapCut 點做）",
        "",
        "研究咗知識型口播高質做法，**top 3 最抵做**（其餘留白，唔好濫）：",
        "",
        f"1. **Kinetic keyword highlight**（最高 ROI）— 字幕關鍵詞放大 + 變 RT 色（{accent1} / {accent2}）。CapCut：揀該詞 → 加大字號 + 改色。",
        "2. **Punch-in zoom**（節奏）— 重點句畫面放大 1.25–1.3x。CapCut：scale keyframe，cut 點即跳。",
        "3. **Easing 紀律**（業餘↔專業分水嶺）— 入場用緩出（ease-out），唔好預設 linear / 乜都彈跳。",
        "",
        "可選：數字 count-up · 手繪圈/箭咀 · 輕 film grain。",
        "",
        "## 整體節奏 tips",
        "",
        "- B-roll 克制：educational talking head 為主，點綴關鍵 beat",
        "- CTA 段唔放 B-roll，留你個樣建立信任",
        "- B-roll inset 圓角 + 細白邊 + 輕陰影會 polish 啲",
        f"- 最強 B-roll 係最貼題材嗰條 — 「{selections[0].get('label', '揀好嘅') if selections else '揀好嘅'}」類放夠耐",
        "- **BGM 揀位**：揀 BGM 由副歌/drop 高光段起播，唔好由前奏 0:00 — 短片得 15–60 秒，頭段鋪陳 = 嘥黃金秒數",
        "- **截圖入片前過隱私**：若片有截圖/螢幕畫面，先裁走工具列/分頁/通知，掃 email / 個資 / API key（一句判斷：「呢格直接公開，我會唔會後悔？」）",
        "",
        "---",
        f"*reel-cut + broll-match 自動生成 · {datetime.now().strftime('%Y-%m-%d')}*",
    ])

    out = Path(args.output) if args.output else Path(args.edl).parent / "briefing.md"
    out.write_text("\n".join(lines), encoding="utf-8")
    print(f"wrote {out} — {n_broll} B-roll slots, {n_gap} gaps, {fmt_ts(speed_dur)} output duration")


if __name__ == "__main__":
    main()
