#!/usr/bin/env python3
"""draft_edl.py — EDL 自動初稿（P1，2026-07-02）：mechanical dedup 由 code 做，editorial 判斷留俾 Opus。

食 takes_packed.md（phrase + gap 結構）→ 相鄰 phrase 內容重疊 → retake cluster →
每 cluster 留最後 take → draft_edl.json（render_edl schema + _draft debug 欄）。

淨做 mechanical：
  - char-bigram Jaccard + 頭綴 match 認 cluster（容忍 whisper 簡繁/粵書 drift 靠較低 threshold + flag）
  - keep 最後 member；唔對稱位淨 flag 唔自決（partial retake / 最後 take 特別短 / 句內自我重複 / 大 gap 黑洞嫌疑）

Usage:
    draft_edl.py <takes_packed.md> --source-id EP1 --source-path /abs/raw.mp4 -o draft_edl.json
"""
import argparse
import json
import re
import sys
from pathlib import Path

SIM_CLUSTER = 0.45      # bigram Jaccard ≥ 此值 → 同 cluster（偏鬆：寧 false-merge 俾人拆，好過漏 retake）
SIM_CONFIDENT = 0.65    # ≥ 此值 cluster 先算高信心；0.45-0.65 flag 人手核
PREFIX_LEN = 5          # 頭 N 字相同 → 認 cluster（捉「早排我同一個」×5 碎 take）
SHORT_LAST = 0.6        # cluster 最後 member 長度 < max member × 此值 → flag「最後 take 可能唔完整」
BLACKHOLE_GAP = 8.0     # phrase 前 gap ≥ 此值 → flag「黑洞嫌疑：gap 內可能有 whisper 漏咗嘅 take」
SELF_REPEAT = 0.5       # phrase 前半 vs 後半 bigram 相似 ≥ 此值 → flag「句內自我重複」
WINDOW = 2              # 同 cluster tail 隔幾多個 phrase 內仍可歸隊（raw-a 有隔一個 phrase 嘅 retake）

PHRASE_RE = re.compile(r"^\[(\d+\.\d+)-(\d+\.\d+)\]\s*(.+)$")
GAP_RE = re.compile(r"^⏸ gap ([\d.]+)s")


def norm(text: str) -> str:
    return re.sub(r"[\s,，。.?？!！、:：;；「」『』()（）]", "", text)


def bigrams(text: str) -> set:
    t = norm(text)
    if len(t) < 2:
        return {t} if t else set()
    return {t[i:i + 2] for i in range(len(t) - 1)}


def jaccard(a: str, b: str) -> float:
    ba, bb = bigrams(a), bigrams(b)
    if not ba or not bb:
        return 0.0
    return len(ba & bb) / len(ba | bb)


def containment(a: str, b: str) -> float:
    """a 嘅 bigram 有幾多比例出現喺 b — 捉「短 retake 係長句一部分」（Jaccard 對長短懸殊句偏低）。"""
    ba, bb = bigrams(a), bigrams(b)
    if not ba:
        return 0.0
    return len(ba & bb) / len(ba)


def same_take(prev: dict, cur: dict) -> tuple[bool, float]:
    j = jaccard(prev["text"], cur["text"])
    c = max(containment(cur["text"], prev["text"]), containment(prev["text"], cur["text"]))
    sim = max(j, c)
    if sim >= SIM_CLUSTER:
        return True, sim
    if norm(prev["text"])[:PREFIX_LEN] and norm(prev["text"])[:PREFIX_LEN] == norm(cur["text"])[:PREFIX_LEN]:
        return True, max(sim, SIM_CLUSTER)
    return False, sim


def self_repeat(text: str) -> bool:
    """句內有 5-gram 非重疊再現 → internal retake（「AB AB C」pattern；前半 vs 後半比較會走甩）。"""
    t = norm(text)
    if len(t) < 12:
        return False
    seen = {}
    for i in range(len(t) - 4):
        g = t[i:i + 5]
        if g in seen and i - seen[g] >= 5:
            return True
        if g not in seen:
            seen[g] = i
    return False


def parse_packed(path: Path) -> list[dict]:
    phrases = []
    for line in path.read_text().splitlines():
        m = PHRASE_RE.match(line.strip())
        if m:
            phrases.append({"start": float(m.group(1)), "end": float(m.group(2)),
                            "text": m.group(3).strip(), "gap_before": 0.0})
            continue
        g = GAP_RE.match(line.strip())
        if g and phrases is not None:
            # gap 行出現喺兩 phrase 之間 → 記做下一個 phrase 嘅 gap_before
            phrases.append({"_pending_gap": float(g.group(1))})
    # 將 pending gap 併入下一個 phrase
    out, pending = [], 0.0
    for p in phrases:
        if "_pending_gap" in p:
            pending = p["_pending_gap"]
            continue
        p["gap_before"] = pending
        pending = 0.0
        out.append(p)
    return out


def cluster_phrases(phrases: list[dict]) -> list[list[int]]:
    clusters, cur = [], [0]
    for i in range(1, len(phrases)):
        matched = False
        for back in range(1, WINDOW + 1):
            if len(cur) >= back:
                tail_idx = cur[-back]
                ok, _ = same_take(phrases[tail_idx], phrases[i])
                if ok:
                    matched = True
                    break
        if matched:
            cur.append(i)
        else:
            clusters.append(cur)
            cur = [i]
    clusters.append(cur)
    return clusters


def build_ranges(phrases: list[dict], clusters: list[list[int]], source_id: str) -> list[dict]:
    ranges = []
    for members in clusters:
        keep_i = members[-1]
        keep = phrases[keep_i]
        n = len(members)
        flags, conf = [], "high"

        if n > 1:
            sims = [same_take(phrases[members[k]], phrases[members[k + 1]])[1] for k in range(n - 1)]
            if min(sims) < SIM_CONFIDENT:
                conf = "low"
                flags.append(f"cluster 相似度弱位 min={min(sims):.2f}（簡繁 drift / false-merge 可能，人手核）")
            max_len = max(len(norm(phrases[m]["text"])) for m in members)
            if len(norm(keep["text"])) < max_len * SHORT_LAST:
                conf = "low"
                flags.append("最後 take 明顯短過 cluster 最長 member — 可能 partial retake（要併前 take 前半？）")
        if keep["gap_before"] >= BLACKHOLE_GAP:
            conf = "low"
            flags.append(f"前有 {keep['gap_before']:.1f}s 大 gap — 黑洞嫌疑，波形/顯微核")
        if self_repeat(keep["text"]):
            conf = "low"
            flags.append("句內自我重複 — whisper 冇斷開嘅 internal retake，可能要 dropped 切")

        ranges.append({
            "source": source_id,
            "start": keep["start"],
            "end": keep["end"],
            "quote": keep["text"][:60],
            "take": f"{n}/{n}",
            "dropped": [],
            "flag": conf == "low",
            "note": "; ".join(flags),
            "_draft": {
                "confidence": conf,
                "members": [{"start": phrases[m]["start"], "text": phrases[m]["text"][:40]}
                            for m in members],
            },
        })
    return ranges


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("packed")
    ap.add_argument("--source-id", required=True)
    ap.add_argument("--source-path", required=True)
    ap.add_argument("-o", "--out", required=True)
    a = ap.parse_args()

    phrases = parse_packed(Path(a.packed))
    if not phrases:
        sys.exit("ERROR: no phrases parsed")
    clusters = cluster_phrases(phrases)
    ranges = build_ranges(phrases, clusters, a.source_id)

    edl = {"version": 1, "sources": {a.source_id: a.source_path}, "ranges": ranges}
    Path(a.out).write_text(json.dumps(edl, ensure_ascii=False, indent=1))

    kept = sum(r["end"] - r["start"] for r in ranges)
    total = phrases[-1]["end"] - phrases[0]["start"]
    n_flag = sum(1 for r in ranges if r["flag"])
    print(f"draft EDL: {len(phrases)} phrases → {len(clusters)} ranges "
          f"({sum(1 for c in clusters if len(c) > 1)} 個有 retake)")
    print(f"draft 長度 ~{kept:.0f}s（source span {total:.0f}s）｜flag {n_flag} 個 range 要人手核：")
    for i, r in enumerate(ranges):
        if r["flag"]:
            print(f"  [{i}] {r['start']:.1f}s 「{r['quote'][:24]}…」 — {r['note']}")


if __name__ == "__main__":
    main()
