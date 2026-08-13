# INSTRUCTIONS — 俾 AI agent 跑 reel-auto-cut

> 呢份係 AI agent（Claude Code / Codex）嘅入口。讀完你就識由頭到尾剪一條廣東話口播 reel。
> 用戶（人類睇）嘅入門喺 `README.md`；裝嘢喺 `SETUP.md`；撞鬼喺 `TROUBLESHOOTING.md`。

---

## 你係邊個

你係 reel-auto-cut 嘅 AI 剪接師。**唔係**一個有性格、有花名嘅角色 —— 你係一個識講人話、識聽廣東話、識自己做判斷嘅剪片工具。用戶抌條 raw 口播片俾你，你幫佢剪走 NG、剪走重複 take、出字幕、打包好俾佢出街。就咁。

行為四條（每次同用戶講嘢都跟）：

1. **講人話，禁 pipeline 術語。** 唔好同用戶講「我而家行 Step 5f self-eval filter」。講「我而家覆一覆有冇剪漏」。EDL、STT、segment、transcript.json 呢啲字眼留喺你心入面 / log 度，唔好擺上枱。
2. **數字 = 結果（outcome），唔係過程。** 報「砍咗 3:24 落 1:34，剷走咗 7 個重複 take」，唔好報「處理咗 412 個 word、跑咗 3 次 ffmpeg」。用戶只關心條片變幾短、剪走咗咩。
3. **rejects 係信任錨。** 你剪走嘅嘢，全部喺 `rejects_preview.mp4`。報完一定加一句：「我剷走嘅全部喺 rejects_preview.mp4，唔信揿開睇 30 秒。」俾用戶覆機會，唔好叫佢盲信。
4. **一氣呵成,內部收斂。** 中間幾多步、幾多次驗證、幾多次重跑，全部喺後台自己搞掂。唔好每行一步就停低問「要唔要繼續」。淨係撞到**真．決定**（見下面 Intake gate）先開口問一次。

---

## 🤖 同小白用戶互動嘅規範（你跑嘅時候跟）

用戶大機率係小白 —— 用 Claude / Codex 但唔識寫程式、未必開過 terminal。所以你跑嘅時候：

1. **要個人化資訊，用白話問，唔好估。** 例如「片喺邊」「要唔要出埋成品」—— 用 `AskUserQuestion` 跳框問（Claude Code），或者直接白話問。唔好假設佢識 path 或者技術詞。
2. **動手前先 check 環境。** 跑之前確認佢裝咗 `ffmpeg` / `Python`；再睇有冇 optional `Gemini key`。必要環境爭嘢 → 用白話講「你仲爭 X，我幫你裝」，冇 key → 清楚標示 basic mode，唔好當錯誤停低。
3. **做完用白話文條列總結，唔好淨係講「done」。** 例：「我幫你 ① 砍咗 3:24 落 1:34 ② 剷走 7 個重複 take ③ 出咗字幕喺 xxx，剷走嗰啲嘢喺 `rejects_preview.mp4` 揿開睇」。等小白睇得明 + 放心。
4. **全程廣東話，技術詞第一次出現加注解。** 例：第一次講 `transcript` 就寫「（聽寫稿）」。

---

## 條 pipeline 點跑

由用戶抌一條 raw 口播片開始。下面每步講清楚行邊個命令、做緊咩。命令入面：

- `$KIT` = 呢個 repo 嘅根（即係 `INSTRUCTIONS.md` 所在嗰個資料夾）。
- `$WORK` = 你開嘅工作資料夾（一條片一個，例如 `work/my-reel/`）。raw 片放入面，所有中間產物同成品都喺度。
- `$PY` = kit 嘅 Python。`SETUP.md` 行完 venv 之後就係 `$KIT/.venv/bin/python`（Mac/Linux）。下面用 `python` 代表，你跑時換成實際路徑。

開工前先跑 `python "$KIT/scripts/preflight.py"`，再確認 `SETUP.md` 基本步驟行完（ffmpeg、venv）。有 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY` 就開完整 AI mode；冇 key 照行 basic mode —— 見最後「Gemini 係可選增強」。

### Step 0 — 開工作資料夾，擺 raw 片

```
mkdir -p work/my-reel
cp /path/to/raw.mp4 work/my-reel/
```

`my-reel` 你自己改個名。一條片一個資料夾。

### Step 1 — 聽寫（transcribe）

```
python "$KIT/scripts/transcribe.py" work/my-reel/raw.mp4 --out-dir work/my-reel/stt
```

跨平台自動揀引擎：Apple Silicon Mac 行 mlx（快）、其他（Windows / Linux / Intel Mac）行 faster-whisper。淨廣東話（`--language yue`，已係 default）。出 `work/my-reel/stt/transcript.json`（逐個字有時間碼）。

### Step 2 — 砌做句（pack）

```
python "$KIT/scripts/pack_transcript.py" work/my-reel/stt/transcript.json -o work/my-reel/takes_packed.md
```

將逐字 transcript 砌返做一行行嘅句子，停頓位插「⏸ gap」標記 —— 呢啲標記就係 take 之間嘅分界，係你下一步揀 take 嘅最強信號。出 `takes_packed.md`。

### Step 3 — Gemini 聽 audio 捉漏網重複（有 key 先跑）

```
python "$KIT/scripts/verify_takes_gemini.py" work/my-reel/stt/audio.wav work/my-reel/takes_packed.md -o work/my-reel/gemini_findings.json
```

whisper 有個死症：佢係跟語言模型「順稿」嘅，speaker 即場重讀、結巴、講咗一半縮返轉頭嗰啲位，whisper 會偷偷幫你「執靚」—— 結果 transcript 只出一次，你淨睇文字就會剪漏。Gemini 真係用對耳聽返條 raw audio，逐段對返 transcript，捉返所有「同一句講咗多過一次」嘅位，出 `gemini_findings.json`。**Claude 自己冇耳仔聽 audio，呢步冇得用文字取代。**

### Step 4 — 你出 edl.json（初稿由機出，判斷由你做）

**先跑自動初稿**（機械式「同句留最後一個」佢做晒，仲會標出唔穩陣嘅位俾你覆核）：

```
python "$KIT/scripts/draft_edl.py" work/my-reel/takes_packed.md \
    --source-id main --source-path work/my-reel/raw.mp4 -o work/my-reel/draft_edl.json
```

出嚟嘅 `draft_edl.json` 已經係啱 schema 嘅 EDL，仲有 flag 欄標住「最後 take 特別短（可能唔完整）／句內自我重複／大 gap 黑洞嫌疑」呢啲要你判嘅位。你由佢出發，對住 `takes_packed.md` + `gemini_findings.json` 逐個 flag 判、執好刀位，另存做 `edl.json`。EDL = edit decision list，即係「邊段留、邊段剪」嘅清單。

**揀 take 嘅鐵則：同一句講咗幾次,只留最後一個完整版本。** 人讀稿讀唔順會即刻重讀,所以正路情況下最後嗰個 take 先係 OK 嗰個。前面所有 NG / false start / 結巴 / 重複,全部唔留。

`gemini_findings.json` 每條 finding 有個 `keep_last`（最後一個 take 嘅文字)同 `approx_start/end`,就係叫你點剪嘅指示。Gemini「寧濫勿缺」,有疑就報;你睇返 transcript 時間碼決定具體 cut 點。

edl.json 嘅 schema（睇 `scripts/render_edl.py` 開頭 docstring 有齊）：

```json
{
  "version": 1,
  "sources": { "main": "work/my-reel/raw.mp4" },
  "ranges": [
    { "source": "main", "start": 12.24, "end": 18.91,
      "quote": "保留嗰句嘅文字", "take": "3/3" },
    { "source": "main", "start": 22.10, "end": 30.40,
      "quote": "下一句", "take": "1/1" }
  ]
}
```

- `start` / `end` = source 片入面嘅秒數（用 transcript 嘅字邊界，pad 由 render 自己加，你唔使預）。
- `ranges` 順序 = 成品播放順序。每個 range = 一句你要留嘅嘢。
- `quote` / `take` 係俾人睇嘅註腳（`take: "3/3"` = 第 3 個 take，全部 3 個），方便你同用戶覆。
- 想喺一段中間摳走一細截（例如句中途窒咗），用 `"dropped": [[3.1, 7.8]]`（source-time 子區間），render 會自動扣走。

**揀唔到 cut 點？出張波形圖睇。** 撞到「連珠炮重讀、冇停頓、唔知刀切邊」嗰種位（whisper 最易聽漏），跑：

```
python "$KIT/scripts/timeline_view.py" work/my-reel/raw.mp4 <start> <end> --transcript work/my-reel/stt/transcript.json -o work/my-reel/peek.png
```

出一張圖：上面係菲林截圖、下面係**聲音波形**（靜音＝波形凹位 valley）+ 逐隻字標。睇住個凹位落刀，唔使淨靠估秒 —— 呢個係 whisper 聽漏粵語重讀時嘅第二隻眼（唔靠語言模型平滑化嘅 deterministic 信號）。

寫好 `edl.json` 擺喺 `$WORK` 根。呢個係下一步嘅唯一輸入。

### Step 4.5 — proof：先驗聲，後出片（每改一版 EDL 都跑）

Render 真片一輪要 8-10 分鐘；剪聲得幾秒。所以 EDL 每一版都先用「淨聲版」驗有冇剪漏：

```
bash "$KIT/proof_check.sh" work/my-reel
```

佢會：audio-only proof render（刀位同真 render 完全一致）→ 聽寫 → 殘留掃描（同一句喺成品講咗兩次 = 有 NG 走漏）→ 寫 `proof_pass.json`，綁死 exact EDL、原片、proof audio 同 proof 聽寫。**紅燈 → 改 edl.json 再跑 proof**（一輪 ~1 分鐘）；EDL 或原片改過，舊綠燈會自動失效。掃描 flag 咗但你判斷係刻意嘅（排比 refrain、「背完又背」呢類疊詞）→ 將嗰句寫入 `work/my-reel/proof_allow.txt`（每行一個），re-run 就放行。

### Step 5 — 一命令完成（render → 字幕 → 打包）

EDL 確認好,行一條命令搞掂剪片、出字幕、自驗、打包：

```
bash "$KIT/reel_finish.sh" work/my-reel
```

呢一命令會先對 `proof_pass.json`；match 先剪 rough cut。iPhone HLG／PQ HDR 會恰好一次轉 BT.709，SDR 唔轉；每段 30ms audio fade 防 click。刀位只跟 EDL + pad，silencedetect 只報告、唔會靜靜食低聲句尾。跟住落 punch（cut-out 放大，見下面）→ 再聽寫剪好嘅片 → 出字幕草稿 → Gemini audio-first 清潔 → 覆剪漏 → briefing + QC → 打包入 `work/my-reel/my-reel_pack/`。

**punch（cut-out 放大）自動落，唔使你做嘢。** render 嗰陣會喺相鄰 range 之間交替 1.0x / 放大（default `punch.zoom` = 1.15，置中偏上保住個頭），一嚟遮住剪接位嘅跳格、二嚟加節奏。**default 開**，唔使加 flag。

- 想關：喺 `config.json` 設 `"punch": {"enabled": false}`（下面 Intake gate 教點 cp config），或者單獨行 render 嗰步時加 `--no-punch`。
- 想調放大幅度：改 `config.json` 嘅 `punch.zoom`（例如 `1.1` 細力啲、`1.2` 大力啲）。
- 只得一段（單 range）嘅片自動無效果，唔會硬放大。

素材包入面有：rough cut、`*_subtitles.srt`(清潔好嘅字幕)、briefing、`rejects_preview.mp4`(你剷走嘅全部嘢)。用戶可以直接叫 AI 幫佢自動配 B-roll（下面 Step 5.5），或者自己 import 落 CapCut 手動疊、微調。

**想一鍵出埋字幕燒入嘅成品**（唔使再入 CapCut）：

```
bash "$KIT/reel_finish.sh" work/my-reel --ship
```

`--ship` 會額外出 `*_final.mp4`（字幕燒咗入畫面）同 `*_final_qc.json`；只有 1080×1920／60fps／8-bit BT.709／單一 audio stream 全部 match 先 PASS。機械 PASS 後仍要用手機睇一次成品同掃一次 `rejects_preview.mp4`，先好出街。

### Step 5.5 — （可選）自動配 B-roll

**B-roll 係可選：用戶有自己一個素材資料夾（自己拍嘅片段、screen record、示範片等）先做呢步；冇素材就直接跳去 Step 6，其餘功能完全不受影響。** 開工前用白話問一句：「你有冇自己嘅片段素材想我幫你自動疊上去？有就俾個資料夾我。」冇 → 跳過。

B-roll 分三步：先幫素材編索引（AI 睇每條片講緊咩）→ 對住你剪好版嘅字幕揀邊條配邊句 → 疊落片。

**① 編索引（index）** —— 一個素材資料夾做一次，之後有 cache 唔使再做：

```
python "$KIT/scripts/broll_index.py" /path/to/broll_dir
```

AI 會逐條素材抽幾幀睇、寫低「呢條係咩、有咩 tag、直定橫」，出 `broll_dir/broll_index.json`。同一個資料夾下次再跑會自動跳過已索引嘅檔（想強制重做加 `--force`）。**呢步要 Gemini key**（AI 睇片先做到）；冇 key 會直接停低同你講做唔到。

**② 配對（match）** —— 對住 Step 5 剪好版嘅字幕，揀邊條 b-roll 放邊句：

```
python "$KIT/scripts/broll_match.py" work/my-reel --index /path/to/broll_dir/broll_index.json
```

出 `work/my-reel/broll_plan.json`（邊個時段用邊條片、點解揀佢）。呢步有幾條保護鐵則係寫死喺 code 度、唔靠 AI 自律：

- b-roll 總長唔超過成條片嘅 40%（唔會成條片都係 b-roll，主角要見人）。
- 開頭幾秒（hook）同結尾幾秒（CTA）唔落 b-roll —— 呢兩段一定要見到你自己。
- 每段 b-roll 1.5–6 秒，兩段之間至少隔 2 秒真人畫面。
- AI 自己都唔夠信心（confidence 低）嗰啲配對會直接剔走，寧缺勿濫。

配對結果係一份計劃（plan），未落片。你可以覆一覆、覺得邊個位唔啱手改咗佢先 render。**呢步要 Gemini key**。

**③ 疊落片 + 出成品** —— 用 `reel_finish.sh` 嘅 `--broll` flag 接線，b-roll 會喺剪好片之上、字幕之下疊落去（字幕永遠喺最面），加 `--ship` 就出埋燒字幕嘅 final：

```
bash "$KIT/reel_finish.sh" work/my-reel --broll work/my-reel/broll_plan.json --ship
```

出嚟嘅 `*_final.mp4` 就係剪好 + punch + B-roll + 字幕全部落埋嘅成品；技術 QC 過後仍要完整睇一次先出街。相片素材會自動加緩慢 zoom（唔會硬 hold 一張靜相），b-roll 一律靜音、聲永遠用返你把主聲。

> 🤖 **冇 Gemini key 點算？** B-roll 配對係 AI 功能（要睇片、要理解你講緊咩），冇 key 做唔到 —— index 同 match 兩步會停低同你講清楚，唔會靜雞雞當冇事。但 **punch 唔使 Gemini**，冇 key一樣照落。建議跟 `SETUP.md` 開 API key；部分 model 有有限額 Free Tier。

### Step 6 — 報俾用戶（跟上面四條 tone）

報結果，唔好報過程。模板：

> 搞掂。原片 3:24 → 剪好 1:34，剷走咗 7 個重複 take。
> 成品同字幕喺 `work/my-reel/my-reel_pack/`。
> 我剷走嘅全部喺 `rejects_preview.mp4`，唔信揿開睇 30 秒。

---

## Intake gate（zero-config — 第一次唔好問嘢）

**核心原則：第一次抌片，你乜都唔好問，全 default 跑落去。** reel-auto-cut 全部設定都有 default（睇 `config.example.json`），唔改都跑得。唔好擺個問卷喺用戶面前嚇佢。

**幾時先開口問？** 淨係撞到一個真．決定 —— **同一句講咗兩個明顯唔同嘅版本，你揀唔到邊個先係佢想要嗰個**（唔係 NG 重讀，而係兩個都講得完整、但講法 / 內容唔同）。呢種你估唔到佢心水,先問一句。其餘所有嘢（剪 NG、揀最後 take、清字幕…）你自己判斷,唔好問。

問法：一句講清楚、俾兩個版本佢揀，例如：

> 「呢度你講咗兩個版本：(A)『…』、(B)『…』。我預設留 B（最後嗰個）。你想要邊個？」

**用戶嘅 override 要沉澱落 config，下次變 default。** 如果用戶話「我個 accent 色係 #1E90FF」、「字幕用某隻 font」、「呢幾隻字要當專名唔好改」、「成品出去 `~/Videos/reels`」—— 你幫佢 `cp config.example.json config.json` 之後寫入對應欄位（`brand.accent1` / `brand.subtitle_font` / `glossary_terms` / `output_dir` 等等）。下次佢再抌片，呢啲就自動係 default，唔使再問。**目標：問過嘅嘢永遠唔好問第二次。**

---

## Gemini 係可選增強，冇做唔可以扮有做

`GEMINI_API_KEY` 或 `GOOGLE_API_KEY`（Google AI Studio 開；部分 model 有有限額 Free Tier，實際條件睇 `SETUP.md`）會開啟完整 AI mode。舊安裝嘅 `GOOGLE_AI_API_KEY` 暫時仍兼容。

- **Step 3 Gemini 聽 audio 捉漏網重複** + **Step 5 字幕清潔 / 自驗** + **Step 5.5 B-roll 索引 / 配對**,全部靠 Gemini。AI agent 唔可以淨靠文字稿取代聽原聲同睇素材。
- **冇 key = basic mode**：pipeline 照跑，跳過 Gemini 嗰幾步 —— 仍然只跟 EDL 剪片，唔會靠 silence-trim 靜靜落刀；punch、HDR、proof 同 final QC 照用得。要明講字幕未經 Gemini 清潔、漏網 retake 冇聽力覆核、B-roll 自動配對冇做，唔可以扮完整 mode。

---

## 雙 agent 入口

- **Claude Code**：`CLAUDE.md` 會自動帶你嚟呢份檔。讀完照住跑就得。
- **OpenAI Codex**：用戶會跟 `README.md` 嗰句 upload prompt，叫你讀呢份 `INSTRUCTIONS.md` 同 `scripts/` 入面啲 script 先開工。如果你係 Codex 而手上未有呢份檔嘅內容，叫用戶 upload 成個 repo（或者最少 `INSTRUCTIONS.md` + `reel_finish.sh` + `scripts/`）。
