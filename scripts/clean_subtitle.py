#!/usr/bin/env python3
"""
Reel Subtitle Cleaner v6 — Gemini text-only correction with structured output.
Keeps original SRT timestamps exactly as-is. Gemini only corrects text.
Uses JSON schema enforcement, system instructions, few-shot examples,
inline audio, and post-processing filler regex.
"""

import sys
import os
import re
import json
import base64
from pathlib import Path
from google import genai
from google.genai.types import GenerateContentConfig

# --- Config ---
GEMINI_MODEL = "gemini-2.5-flash"

# --- Filler regex patterns (post-Gemini safety net) ---
FILLER_PATTERNS = [
    # 句首 fillers
    (r"^嗱[，,]?\s*", ""),
    (r"^噉[，,]?\s*", ""),
    (r"^噉啦[，,]?\s*", ""),
    (r"^其實嗱[，,]?\s*", ""),
    (r"^即係嗱[，,]?\s*", ""),
    (r"^咁樣嘅[，,]?\s*", ""),
    # 句尾 fillers
    (r"[，,]?\s*咧$", ""),
    (r"[，,]?\s*嘅話咧$", ""),
    (r"[，,]?\s*嘅話$", ""),
    (r"[，,]?\s*㗎喇$", ""),
    (r"[，,]?\s*囉$", ""),
    # 猶豫 fillers
    (r"\s*呃\s*", ""),
    (r"\s*嗯\s*", ""),
    (r"\b[Uu]m\b\s*", ""),
    (r"\b[Ee]r\b\s*", ""),
    # 重複
    (r"等等等等+", "等等"),
]

# --- 用戶 glossary 修正（由 config.json 嘅 glossary_fixes 讀，generic）---
# 你成日講嘅品牌 / 英文專名，STT 成日聽錯，擺入 config glossary_fixes 自動修返。
# 格式：[["STT 聽錯嘅字", "正確寫法"], ...]。唔填 = no-op（純 string replace）。
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "lib"))
from kit_config import CONFIG as _CFG
GLOSSARY_FIXES = [p for p in _CFG.get("glossary_fixes", [])
                  if isinstance(p, (list, tuple)) and len(p) == 2]


def post_clean_fillers(text):
    """Apply rule-based filler removal after Gemini correction."""
    for pattern, replacement in FILLER_PATTERNS:
        text = re.sub(pattern, replacement, text)
    return text.strip()


def apply_brand_fixes(text):
    """用戶 glossary 修正（config glossary_fixes，simple string replace；唔填 = no-op）。"""
    for find, repl in GLOSSARY_FIXES:
        text = text.replace(find, repl)
    return text


def parse_srt(filepath):
    """Parse SRT file into list of entries."""
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    entries = []
    blocks = re.split(r"\n\n+", content.strip())
    for block in blocks:
        lines = block.strip().split("\n")
        if len(lines) >= 3:
            try:
                idx = int(lines[0])
            except ValueError:
                continue
            time_match = re.match(
                r"(\d{2}:\d{2}:\d{2},\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2},\d{3})",
                lines[1],
            )
            if time_match:
                text = " ".join(lines[2:])
                entries.append(
                    {
                        "idx": idx,
                        "start": time_match.group(1),
                        "end": time_match.group(2),
                        "text": text,
                    }
                )
    return entries


def count_chars(text):
    """Count display characters (CJK=1, short EN=1, medium EN=2, long EN=3)."""
    count = 0
    i = 0
    while i < len(text):
        ch = text[i]
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf":
            count += 1
            i += 1
        elif ch.isascii() and ch.isalpha():
            word = ""
            while i < len(text) and text[i].isascii() and (text[i].isalpha() or text[i] == "'"):
                word += text[i]
                i += 1
            if len(word) <= 3:
                count += 1
            elif len(word) <= 6:
                count += 2
            else:
                count += 3
        elif ch in "，。！？、：；「」『』《》（）…—":
            count += 1
            i += 1
        else:
            i += 1
    return count


def extract_glossary(script_text):
    """從 script.md 抽英文/專名 token 做「串法表」（NOT 內容對稿）。
    audio-first：只幫 Gemini 串啱專名，唔餵稿內容（2026-06-26 痛點 A）。"""
    if not script_text:
        return []
    STOPWORDS = {"the", "and", "for", "you", "not", "are", "was", "ground",
                 "truth", "with", "this", "that", "your", "script", "glossary"}
    tokens = re.findall(r"[A-Za-z][A-Za-z0-9]*(?:[ .\-][A-Za-z0-9]+)*", script_text)
    seen = []
    for t in tokens:
        t = t.strip()
        if len(t) < 2 or t.lower() in STOPWORDS:
            continue
        if t not in seen:
            seen.append(t)
    return seen


def char_overlap_ratio(orig, corrected):
    """原 whisper 句 vs Gemini 改句嘅 CJK 字符重疊率（防篡改 flag）。
    低重疊 = Gemini 可能換咗內容（痛點 A：九成功力→AI全部），report 俾人核。
    註：簡轉繁 + 口語化會壓低 ratio，所以閾值設保守（< 0.4 先 flag）。"""
    def cjk(t):
        return set(ch for ch in t if "一" <= ch <= "鿿")
    o, c = cjk(orig), cjk(corrected)
    if not o:
        return 1.0
    return len(o & c) / len(o)


def gemini_correct(mp3_path, srt_entries, glossary=None):
    """Use Gemini to correct SRT text only via structured JSON output。
    glossary = 專名/英文詞 list（只對串法，NOT 內容對稿）。
    AUDIO-FIRST（2026-06-26 痛點 A fix）：字幕內容 100% 跟音頻實際講嘅，
    唔再餵口播稿做 ground truth —— 即興改稿嘅片，Gemini 會信稿改返你實際講嘅 take
    （「AI 九成功力大錯特錯」變返稿「AI 全部」），字幕同片對唔上。改用 audio-first +
    純串法 glossary。"""
    api_key = os.environ.get("GOOGLE_AI_API_KEY")
    if not api_key:
        print("ERROR: GOOGLE_AI_API_KEY not set")
        sys.exit(1)
    client = genai.Client(api_key=api_key, http_options={"timeout": 120_000})

    n = len(srt_entries)

    # Build numbered list of original entries
    numbered_lines = "\n".join(
        [f"{i+1}: {e['text']}" for i, e in enumerate(srt_entries)]
    )

    # 專名表（只對串法，NOT 內容對稿）—— audio-first 防篡改
    glossary_block = ""
    if glossary:
        glossary_block = f"""

專名串法表（以下詞語聽到就照呢個串法寫；呢個係「串法表」唔係內容稿）：
{", ".join(glossary)}
⚠️ 呢個表淨係幫你串啱專名，**唔好攞嚟改寫/補/換句**。字幕內容 100% 跟音頻你實際聽到嘅。"""

    # System instruction — structural rules + correction guidelines
    system_instruction = f"""你係一個廣東話字幕校對專家。講者係香港人，用港式粵語口語。{glossary_block}

你嘅任務係逐條修正 STT 字幕文字，保持完全一樣嘅行數（{n} 行）。

🔴 AUDIO-FIRST 鐵則（最重要，凌駕一切）：
- 字幕內容 = 你喺音頻聽到「實際講嘅嘢」，逐字跟。**唔好參考任何外部稿、唔好「執靚」內容、唔好換句式、唔好補你覺得應該有嘅字**。
- 你只准做 3 件事：① 簡轉繁 ② 同音錯字改返啱（聽音頻確認）③ 專名照串法表。其餘照音頻原文。
- 即係：聽到乜寫乜，淨係修錯字。**寧可保留口語原句，都唔好改成「更通順」版本**。

嚴格規則：
- 第 N 行輸出只能修正第 N 行嘅內容
- 絕對唔好將兩行合併成一行，或者將一行嘅內容搬去另一行
- 每行嘅 id 必須同原始編號一致

文字修正：
- 簡體字全部轉繁體
- 同音錯字根據上下文修正（聽音頻確認）
- 品牌名/專有名詞還原正確拼寫（照串法表）
- 保留自然嘅中英夾雜同口語風格
- 英文術語保持英文（例：AI, marketing, copywriting）
- 唔好加標點符號（逗號可以用嚟分隔，但唔好加句號）

刪除原則（以下情況 text 輸出 [DELETE]）：

1. Filler / 口頭禪（aggressive 精簡，盡量移除）：
   - 句首：嗱、噉、噉啦、其實嗱、即係嗱、咁樣嘅、即係、咁、然後
   - 句尾：咧、啦、喇、囉、嘅話咧、嘅話、㗎喇、㗎、純語氣嘅「呢」
   - 中段贅詞：停頓詞「呢」、即係、咁樣、其實、嗰個（指代以外）
   - 猶豫：呃、嗯、um、er、啊
   - ⚠️ 保留實義詞：possessive「嘅」（我嘅嘢）、demonstrative「呢個/呢啲」、實義「咁多/咁樣做」—— 靠 context 判斷，唔好誤刪實詞

2. 零內容行（整行只有以下，冇實質資訊）：
   - 孤立話語標記：okay / OK / 所以 / 但係 / 跟住 / 係咪 / 噉 / 好
   - 純過渡句：我同你講 / 我可以同你講 / 你就get / 呢個就係 / 所以你見到
   - 判斷標準：刪除後上下兩行嘅意思完全唔受影響，就應刪除"""

    # User prompt — data + few-shot examples
    user_prompt = f"""## 示範

輸入：
1: 嗱其实今天系
2: 我想讲一下关于
3: 个AI嘅嘢啦
4: 佢真系好犀利
5: 呃咁样嘅

輸出：
[{{"id": 1, "text": "今日係"}}, {{"id": 2, "text": "我想講一下關於"}}, {{"id": 3, "text": "個AI嘅嘢"}}, {{"id": 4, "text": "佢真係好犀利"}}, {{"id": 5, "text": "[DELETE]"}}]

## 錯誤示範（唔好咁做）

❌ 將兩行合併：
輸入 3: 個AI嘅嘢啦 / 4: 佢真系好犀利
錯誤：{{"id": 3, "text": "個AI嘅嘢佢真係好犀利"}} / {{"id": 4, "text": "[DELETE]"}}
✅ 正確：{{"id": 3, "text": "個AI嘅嘢"}} / {{"id": 4, "text": "佢真係好犀利"}}

## 原始字幕（{n} 行）

{numbered_lines}

聽完音頻後，逐條修正以上 {n} 行字幕。"""

    # Read audio as inline base64
    with open(mp3_path, "rb") as f:
        audio_b64 = base64.b64encode(f.read()).decode("utf-8")

    print("Sending audio + SRT to Gemini (inline)...")
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=[
            {"inline_data": {"mime_type": "audio/mpeg", "data": audio_b64}},
            user_prompt,
        ],
        config=GenerateContentConfig(
            system_instruction=system_instruction,
            temperature=0.2,
            response_mime_type="application/json",
            response_schema={
                "type": "ARRAY",
                "items": {
                    "type": "OBJECT",
                    "properties": {
                        "id": {"type": "INTEGER"},
                        "text": {"type": "STRING"},
                    },
                    "required": ["id", "text"],
                },
                "minItems": 1,
            },
        ),
    )

    return response.text


def parse_gemini_json(text, expected_count):
    """Parse Gemini's JSON array output into list of corrected texts.

    Returns list of strings, same length as expected_count.
    """
    try:
        entries = json.loads(text)
    except json.JSONDecodeError:
        print("WARNING: Failed to parse JSON, falling back to numbered format")
        return parse_gemini_numbered_fallback(text, expected_count)

    corrections = {}
    for entry in entries:
        idx = entry.get("id")
        t = entry.get("text", "")
        if idx is not None:
            corrections[int(idx)] = t.strip()

    result = []
    for i in range(1, expected_count + 1):
        result.append(corrections.get(i))

    return result


def parse_gemini_numbered_fallback(text, expected_count):
    """Fallback: parse numbered format if JSON fails."""
    corrections = {}
    for line in text.strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        match = re.match(r"(\d+)\s*[:：]\s*(.*)", line)
        if match:
            idx = int(match.group(1))
            corrected = match.group(2).strip()
            corrections[idx] = corrected

    result = []
    for i in range(1, expected_count + 1):
        result.append(corrections.get(i))

    return result


def generate_srt(entries, output_path):
    """Generate SRT file from entries."""
    lines = []
    for i, entry in enumerate(entries, 1):
        lines.append(str(i))
        lines.append(f"{entry['start']} --> {entry['end']}")
        lines.append(entry["text"])
        lines.append("")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))
    return len(entries)


def generate_report(original_entries, corrected_texts, final_entries):
    """Generate a summary report."""
    report = []
    report.append("## 字幕清理報告\n")
    report.append("| 項目 | 數值 |")
    report.append("|------|------|")
    report.append(f"| 原始 entries | {len(original_entries)} |")
    report.append(f"| 清理後 entries | {len(final_entries)} |")

    changed = 0
    deleted = 0
    unchanged = 0
    for i, orig in enumerate(original_entries):
        if i < len(corrected_texts) and corrected_texts[i] is not None:
            ct = corrected_texts[i]
            if ct == "[DELETE]":
                deleted += 1
            elif ct != orig["text"]:
                changed += 1
            else:
                unchanged += 1
        else:
            unchanged += 1

    report.append(f"| 修正咗 | {changed} |")
    report.append(f"| 刪除咗 | {deleted} |")
    report.append(f"| 無改動 | {unchanged} |")

    if changed > 0:
        report.append("\n### 修正內容\n")
        report.append("| # | 原文 | 修正後 |")
        report.append("|---|------|--------|")
        for i, orig in enumerate(original_entries):
            if i < len(corrected_texts) and corrected_texts[i] is not None:
                ct = corrected_texts[i]
                if ct != "[DELETE]" and ct != orig["text"]:
                    report.append(f"| {i+1} | {orig['text']} | {ct} |")

    return "\n".join(report)


def main():
    if len(sys.argv) < 2:
        print("Usage: reel_subtitle_gemini.py <directory_path>")
        sys.exit(1)

    base_dir = Path(sys.argv[1])

    srt_files = [f for f in base_dir.glob("*.srt") if "_cleaned" not in f.stem]
    mp3_files = list(base_dir.glob("*.MP3")) + list(base_dir.glob("*.mp3"))

    if not srt_files:
        print("ERROR: No SRT file found")
        sys.exit(1)
    if not mp3_files:
        print("ERROR: No MP3 file found")
        sys.exit(1)

    srt_path = srt_files[0]
    mp3_path = mp3_files[0]

    # 專名串法表：WORK/script.md（final_stt 上一層）→ 只抽英文/專名（NOT 內容對稿）
    # AUDIO-FIRST（2026-06-26 痛點 A）：字幕 100% 跟音頻，script 唔再做 ground truth
    script_path = base_dir.parent / "script.md"
    script_text = script_path.read_text(encoding="utf-8").strip() if script_path.exists() else ""
    glossary = extract_glossary(script_text)

    print(f"SRT: {srt_path.name}")
    print(f"MP3: {mp3_path.name}")
    print(f"Glossary（串法表）: {('✓ ' + str(len(glossary)) + ' 個 — ' + ', '.join(glossary[:12])) if glossary else '✗ 冇'}")
    print("Mode: AUDIO-FIRST（字幕 100% 跟音頻，唔對稿內容）")

    # Step 1: Parse original SRT
    original_entries = parse_srt(str(srt_path))
    print(f"Parsed {len(original_entries)} original entries")

    # Step 2: Gemini text correction (structured JSON output)
    gemini_text = gemini_correct(str(mp3_path), original_entries, glossary)
    print(f"\n--- Gemini Output (first 500 chars) ---\n{gemini_text[:500]}\n---\n")

    # Step 3: Parse JSON output
    corrected_texts = parse_gemini_json(gemini_text, len(original_entries))
    matched = sum(1 for t in corrected_texts if t is not None)
    print(f"Matched {matched}/{len(original_entries)} entries")

    # Step 4: Post-processing — filler regex + brand fixes safety net
    filler_cleaned = 0
    brand_fixed = 0
    for i in range(len(corrected_texts)):
        if corrected_texts[i] and corrected_texts[i] != "[DELETE]":
            cleaned = post_clean_fillers(corrected_texts[i])
            if cleaned != corrected_texts[i]:
                filler_cleaned += 1
            if not cleaned:
                corrected_texts[i] = "[DELETE]"
                continue
            after_brand = apply_brand_fixes(cleaned)
            if after_brand != cleaned:
                brand_fixed += 1
            corrected_texts[i] = after_brand
    if filler_cleaned > 0:
        print(f"Regex filler cleanup: {filler_cleaned} entries")
    if brand_fixed > 0:
        print(f"Brand/term fixes: {brand_fixed} entries")

    # Step 5: Validate — flag 合併（字數）+ 篡改（低 CJK 重疊，痛點 A audio-first 兜底）
    warnings = []
    tamper = []
    for i, orig in enumerate(original_entries):
        if i < len(corrected_texts) and corrected_texts[i] is not None:
            ct = corrected_texts[i]
            if ct == "[DELETE]":
                continue
            orig_chars = count_chars(orig["text"])
            new_chars = count_chars(ct)
            if orig_chars > 0 and new_chars > orig_chars * 1.8:
                warnings.append(f"  Entry {i+1}: 原文 {orig_chars} 字 → 修正 {new_chars} 字（可能合併咗相鄰 entry）")
            # 篡改偵測：CJK 字符重疊太低 = Gemini 可能換咗內容（唔係改錯字）
            ratio = char_overlap_ratio(orig["text"], ct)
            if ratio < 0.4 and orig_chars >= 4:
                tamper.append(f"  Entry {i+1}: 重疊 {ratio:.0%} ｜ 原「{orig['text']}」→ 改「{ct}」")

    if warnings:
        print(f"\n⚠️  疑似合併 entries：")
        for w in warnings:
            print(w)
    if tamper:
        print(f"\n🔴 疑似篡改（CJK 重疊 <40%，可能改咗內容唔係改錯字）—— 人手核：")
        for t in tamper:
            print(t)

    # Step 6: Pair corrected text with original timestamps, remove deleted entries
    final_entries = []
    for i, orig in enumerate(original_entries):
        if i < len(corrected_texts) and corrected_texts[i] is not None:
            ct = corrected_texts[i]
            if ct == "[DELETE]":
                continue
            text = ct
        else:
            text = orig["text"]

        if text.strip():
            final_entries.append({
                "start": orig["start"],
                "end": orig["end"],
                "text": text.strip(),
            })

    # Step 7: Generate output SRT
    output_path = srt_path.parent / f"{srt_path.stem}_cleaned.srt"
    count = generate_srt(final_entries, str(output_path))
    print(f"\nOutput: {output_path}")
    print(f"Total entries: {count}")

    # Step 8: Report
    report = generate_report(original_entries, corrected_texts, final_entries)
    print(f"\n{report}")


if __name__ == "__main__":
    main()
