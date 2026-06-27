#!/usr/bin/env python3
"""reel-cut 自動 QC（reel_finish 尾段 call）— catch 三個 recurring pain：
① SRT 黑洞漏句：相鄰 >2.5s gap + 尾段 coverage vs 片長（whisper 喺剪好片可黑洞成句）
② 開頭重複 take：micro_probe 剪好片頭 7s 問第一句次數（retake-dense 開頭黑洞 multi-take，raw02/03 嗰種）
③ 頻閃 / 黑場閃：blackdetect 掃完整版/roughcut（疊 B-roll 接位 / 暗素材 / 爆閃，learn from video-autopilot M93）

Usage: qc_check.py <work_dir>
Advisory only — always exit 0，唔 block reel_finish；有 flag 就 print 出嚟提我核。
"""
import json, os, re, subprocess, sys
from pathlib import Path

GAP_FLAG = 2.5
SK = Path(__file__).resolve().parent          # self-locate，唔 hardcode
PY = sys.executable                            # 當前 python（kit venv）


def ts(h, m, s, ms):
    return int(h) * 3600 + int(m) * 60 + int(s) + int(ms) / 1000


def parse_srt(p):
    t = open(p, encoding="utf-8").read()
    out = []
    for m in re.finditer(
        r"(\d+)\s+(\d\d):(\d\d):(\d\d),(\d\d\d)\s*-->\s*(\d\d):(\d\d):(\d\d),(\d\d\d)\s+(.*?)(?=\n\n|\Z)",
        t, re.S):
        g = m.groups()
        out.append((int(g[0]), ts(*g[1:5]), ts(*g[5:9]), g[9].replace("\n", " ").strip()))
    return out


def main():
    work = Path(sys.argv[1]).expanduser()
    slug = work.name
    issues = 0
    print("═══ reel-cut 自動 QC ═══")

    final_s = None
    qcp = work / "qc.json"
    if qcp.exists():
        try:
            final_s = json.load(open(qcp)).get("final_s")
        except Exception:
            pass

    # ── ① SRT 完整性 ──
    srt = work / f"{slug}_subtitles.srt"
    if not srt.exists():
        c = sorted(work.glob("*_subtitles.srt"))
        srt = c[0] if c else None
    if srt and srt.exists():
        e = parse_srt(srt)
        for i in range(1, len(e)):
            gap = e[i][1] - e[i - 1][2]
            if gap > GAP_FLAG:
                print(f"⚠ SRT 中段 gap {gap:.1f}s：#{e[i-1][0]}「…{e[i-1][3][-10:]}」→ "
                      f"#{e[i][0]}「{e[i][3][:10]}…」→ 可能 whisper 黑洞漏句，對 EDL 聽片補")
                issues += 1
        if final_s and e:
            tail = final_s - e[-1][2]
            if tail > 2.0:
                print(f"⚠ SRT 尾段缺 {tail:.1f}s（尾句收 {e[-1][2]:.1f}s vs 片長 {final_s:.1f}s）→ 結尾可能漏句")
                issues += 1
        if issues == 0:
            print(f"✓ SRT 完整（{len(e)} 句，無 >{GAP_FLAG}s gap，尾段齊）")
    else:
        print("⚠ 搵唔到 SRT")
        issues += 1

    # ── ② 開頭重複 take（micro_probe 剪好片頭 7s）──
    cm = None
    for pat in ("cut_master_trim.mov", "cut_master*.mov", "cut_master*.mp4"):
        c = sorted(work.glob(pat))
        if c:
            cm = c[0]
            break
    key = os.environ.get("GOOGLE_AI_API_KEY")
    mp = SK / "micro_probe.py"
    if cm and key and mp.exists():
        probe = [{"label": "開頭重複", "start": 0.0, "end": 7.0,
                  "question": "呢段剪好片開頭，第一句完整講咗幾多次？多過一次即係有重複 take 殘留。"
                              "答次數(數字)+確信度 high/mid/low。"}]
        pf = work / "_qc_probe.json"
        outf = work / "_qc_probe_out.json"
        json.dump(probe, open(pf, "w"), ensure_ascii=False)
        try:
            subprocess.run([PY, str(mp), str(cm), str(pf), "-o", str(outf)],
                           capture_output=True, timeout=120)
            r = json.load(open(outf))[0]
            n = r.get("takes_heard", 1)
            if isinstance(n, (int, float)) and n > 1:
                print(f"⚠ 開頭重複：第一句聽到講咗 {n} 次（{r.get('confidence')}）→ "
                      f"開頭有黑洞 multi-take 殘留，核 EDL range 1")
                issues += 1
            else:
                print(f"✓ 開頭乾淨（第一句 {n} 次）")
        except Exception as ex:
            print(f"（開頭 probe skip：{str(ex)[:50]}）")
    else:
        print("（開頭 probe skip：無 cut_master / GOOGLE_AI_API_KEY / micro_probe.py）")

    # ── ③ 頻閃 / 黑場閃（blackdetect — 疊 B-roll 接位 / 暗素材 / 爆閃畫面，learn from video-autopilot M93）──
    vid = None
    for pat in (f"{slug}_完整版.mp4", "*_完整版.mp4", f"{slug}_roughcut.mp4", "*_roughcut.mp4"):
        c = sorted(work.glob(pat))
        if c:
            vid = c[0]
            break
    if vid:
        r = subprocess.run(
            ["ffmpeg", "-hide_banner", "-i", str(vid),
             "-vf", "blackdetect=d=0.05:pix_th=0.10", "-an", "-f", "null", "-"],
            capture_output=True, text=True)
        blacks = re.findall(r"black_start:([\d.]+)", r.stderr)
        if blacks:
            print(f"⚠ 頻閃/黑場：{len(blacks)} 個短黑幀（疊 B-roll 接位 / 暗素材 / 爆閃）"
                  f"→ {', '.join(blacks[:5])}s 睇下刺唔刺眼")
            issues += 1
        else:
            print(f"✓ 無黑場閃（{vid.name}）")

    print(f"═══ QC {'✅ PASS' if issues == 0 else f'⚠ {issues} 個 flag — 睇上面核'} ═══")


if __name__ == "__main__":
    main()
