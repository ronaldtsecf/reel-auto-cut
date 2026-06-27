#!/usr/bin/env python3
"""self-eval auto-filter — 用 final 剪好片 transcript 自動分流 Gemini self-eval findings。

Background（LEARNINGS 反覆 5 次 EP2-6）：Gemini self-eval 對剪好片嚴重 over-segment，
findings 大量係「X｜X」(同句顯示兩次) 或「前半句｜全句」hallucination
（EP3 33 個全假、EP6 14/15 假）。人手逐個 word-timing 核好嘥時間 + 易被帶偏。

呢個 script 將「逐個核」自動化（LEARNINGS 鐵則入 code）：
  finding heard 講有重複 → 去 final 剪好片 transcript 數呢句真實出現次數
    - 連續出現 ≥2 次  → real（真重複殘留，要核 EDL）
    - 得一次          → reject（Gemini over-segment 幻覺，剪好片只講一次）
    - 搵唔到/黑洞      → needs_micro（唔敢自動判，要顯微聽）

關鍵：**by 內容核，唔 by 秒**。self-eval approx 秒係 Gemini 聽 cut_master + 餵
source packed 報，同 final_stt（trim silence 後）timeline 對唔上（ep3 報到 141s
但 final 得 96.9s）→ 時間窗口必錯。改用 signature 喺 final 全片數出現次數，
timeline 無關（反正問題就係「剪好片呢句殘唔殘留重複」）。

保守原則：唔確定一律 surface（漏 NG = 出街災難；多核幾個 = 嘥少少時間）。
reject 只發生喺「final 清楚得一次」嘅高信心 case。
Advisory only — 唔自動改 EDL，淨係將 noise 分流，慳人核時間 + 唔淹冇真嫌疑。

Usage:
    filter_selfeval.py <work_dir>                       # 自動揾 gemini_selfeval.json + final_stt/transcript.json
    filter_selfeval.py <selfeval.json> <transcript.json>
"""
import json
import re
import sys
from pathlib import Path

SIG_LEN = 6        # signature = keep_last 開頭 N 個 CJK/alnum char
SHORT_SIG = 4      # signature 短過此 → 唔夠 unique 自動判，保守 surface
PROXIMITY = 8.0    # 兩次出現相距 < 此秒 → 當連續重複（真 NG）；遠 → 可能同詞巧合
COV_EXISTS = 0.7   # signature exact miss 時，keep_last bigram 命中率 ≥ 此 → 句確存在 final（措辭飄），非真漏


CJK_RUN = re.compile(r"[一-鿿]+")


def norm(s: str) -> str:
    """去標點/空格 + lowercase，淨留 CJK + alnum。"""
    return re.sub(r"[^\w一-鿿]", "", (s or "").lower())


def split_takes(heard: str) -> list:
    return [p.strip() for p in re.split(r"[｜|]", heard or "") if p.strip()]


def signature(keep_last: str, takes: list) -> str:
    """取 keep_last 最長純中文 run 頭 N 字做 signature。

    避開英文專名/數字（Claude→clock、Anthropic、AI agent）— whisper drift 最勁
    嗰啲位，撞落 signature 會令本應 confident-reject 嘅變搵唔到。純中文 run drift 細好多。
    """
    base = keep_last or (takes[-1] if takes else "")
    runs = [r for r in CJK_RUN.findall(base) if len(r) >= SHORT_SIG]
    if runs:
        return max(runs, key=len)[:SIG_LEN]
    return norm(base)[:SIG_LEN]  # 冇長中文 run → fallback 含英數（多數會落 short→needs_micro）


def build_index(words: list):
    """串接全片 normalized text + 每個 char 對應 word 嘅 start 秒（content→time map）。"""
    text, char_t = [], []
    for w in words:
        t = norm(w.get("text", ""))
        text.append(t)
        char_t.extend([w.get("start", 0.0)] * len(t))
    return "".join(text), char_t


def occur_times(full_text: str, char_t: list, sig: str) -> list:
    """signature 喺全片每次出現嘅 start 秒。"""
    out, i = [], full_text.find(sig)
    while i != -1:
        out.append(char_t[i] if i < len(char_t) else 0.0)
        i = full_text.find(sig, i + 1)
    return out


def coverage(keep_last: str, full_text: str) -> float:
    """keep_last 嘅 char-bigram 幾多 % 喺 final 全片出現 — 量度「句存唔存在」（容措辭飄）。"""
    s = norm(keep_last)
    bg = {s[i:i + 2] for i in range(len(s) - 1)}
    return sum(1 for b in bg if b in full_text) / len(bg) if bg else 0.0


def classify(f: dict, full_text: str, char_t: list):
    takes = split_takes(f.get("heard", ""))
    sig = signature(f.get("keep_last", ""), takes)
    kind = f.get("kind", "")

    if len(sig) < SHORT_SIG:
        return "needs_micro", f"signature 太短（「{sig}」）唔夠 unique，要聽"

    hits = occur_times(full_text, char_t, sig)
    cnt = len(hits)

    if cnt >= 2:
        consec = any(b - a < PROXIMITY for a, b in zip(sorted(hits), sorted(hits)[1:]))
        if consec:
            return "real", f"final 連續講咗 {cnt} 次「{sig}…」→ 真重複殘留"
        return "needs_micro", f"「{sig}…」全片出現 {cnt} 次但分散，可能同詞巧合 → 核下"
    if cnt == 1:
        return "reject", f"final 清楚得一次「{sig}…」，Gemini over-segment 幻覺"
    # cnt == 0：signature exact miss。可能 (a) 措辭飄但句存在 (b) 真黑洞/漏。
    # 用 bigram coverage 區分：句存在 final + 無連續重複（cnt 已 0）→ 乾淨，安全 reject。
    cov = coverage(f.get("keep_last", ""), full_text)
    if cov >= COV_EXISTS:
        return "reject", f"final 有呢句（{cov:.0%} 命中）但無連續重複 → 乾淨，over-segment 幻覺"
    if kind == "missing-from-whisper":
        return "needs_micro", f"Gemini 話 whisper 漏咗「{sig}…」，final {cov:.0%} 命中 → 顯微聽"
    return "needs_micro", f"final 搵唔到「{sig}…」（{cov:.0%} 命中，疑黑洞/漏）→ 顯微核"


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    p = Path(sys.argv[1]).expanduser()
    if p.is_dir():
        se, ft, out_dir = p / "gemini_selfeval.json", p / "final_stt" / "transcript.json", p
    else:
        se, ft, out_dir = p, Path(sys.argv[2]).expanduser(), p.parent

    if not se.exists():
        sys.exit(f"selfeval 唔存在：{se}")
    if not ft.exists():
        sys.exit(f"final transcript 唔存在：{ft}（reel_finish Step 5a 應該出咗）")

    d = json.load(open(se))
    findings = d["findings"] if isinstance(d, dict) else d
    words = json.load(open(ft)).get("words", [])
    full_text, char_t = build_index(words)

    buckets = {"real": [], "reject": [], "needs_micro": []}
    for f in findings:
        verdict, why = classify(f, full_text, char_t)
        buckets[verdict].append((f, why))

    nr, nx, nm = len(buckets["real"]), len(buckets["reject"]), len(buckets["needs_micro"])
    print(f"self-eval auto-filter — {len(findings)} findings 核晒（對 final 剪好片內容）")
    print(f"  真重複 {nr} ｜ 自動踢走幻覺 {nx} ｜ 要你顯微 {nm}")

    if buckets["real"]:
        print("\n要改 EDL（final 真係有連續重複殘留）：")
        for f, why in buckets["real"]:
            print(f"  {why}")
            print(f"     heard: {str(f.get('heard'))[:74]}")
            print(f"     keep:  {str(f.get('keep_last'))[:60]}")

    if buckets["needs_micro"]:
        print("\n要你顯微聽（唔敢自動判）：")
        for f, why in buckets["needs_micro"]:
            print(f"  {why}")

    if buckets["reject"]:
        print(f"\n自動踢走 {nx} 個 over-segment 幻覺（已核 final 各只講一次，唔使理）。")

    if nr == 0 and nm == 0 and findings:
        print("\n全部係幻覺 → 條片乾淨，可以收貨。")

    out = out_dir / "selfeval_filtered.json"
    json.dump(
        {k: [{**f, "_why": w} for f, w in v] for k, v in buckets.items()},
        open(out, "w"), ensure_ascii=False, indent=1,
    )
    print(f"\n→ {out}")


if __name__ == "__main__":
    main()
