# reel-auto-cut — 廣東話口播片自動剪輯

> ⭐ 小白友善｜裝一次約 10 分鐘｜**Mac 最穩，Windows / Linux 實驗性**
> 抌一條 raw 口播片，AI 幫你自動剪走 NG 同重複 take、執好字幕、出成品。

> **v0.2 production-safety refresh**：iPhone HLG／PQ HDR 自動安全轉 BT.709、
> cache 改用內容 SHA-256、proof 綁死 exact EDL／原片、`--ship` 成品固定
> 1080×1920／60fps／BT.709。舊用戶睇 [更新／重新安裝](SETUP.md#-已經裝過點更新重新安裝)。

---

## 🤖 用 Claude／Codex 一鍵安裝（Copy 呢段）

用 **Claude Code** 或 **Codex App** 開一個有本機 terminal／檔案權限嘅對話，將下面成段 copy 落去。AI 會由下載開始，逐步裝到驗證成功：

```text
幫我由零安裝並驗證 reel-auto-cut：
https://github.com/ronaldtsecf/reel-auto-cut

請用你嘅本機 terminal 同檔案權限直接執行，唔好淨係列步驟俾我自己做：
1. 如果本機未有 repo，clone 最新 main 去 ~/reel-auto-cut；如果已經有，先檢查本機改動，唔好覆蓋，再安全更新。
2. 完整讀 AGENTS.md、SETUP.md 同 INSTRUCTIONS.md，跟足 repo 寫明嘅流程。
3. 自動判斷我用 macOS、Windows 定 Linux，逐步安裝／檢查 Python、ffmpeg、venv、requirements 同 config。
4. Gemini 係 optional：預設先裝唔使 key 嘅 basic mode，唔好因為冇 key 停低。如果我揀完整 AI mode，教我喺本機設定 key，永遠唔好叫我將 key 貼入對話。
5. 安全、可回復嘅步驟直接做；只喺需要系統權限、登入或我作實質選擇時先停低，一次過用白話講我要做咩。
6. 跑 python scripts/preflight.py；如果失敗，診斷同修正後再跑，直至見到 PREFLIGHT PASS。只做安裝，唔好修改 repo 嘅 tracked files。
7. 完成後用白話報告：安裝位置、basic／完整 mode、驗證結果，同我之後點樣開始剪第一條片。
```

> 第一次裝系統工具時，Claude／Codex 可能會叫你撳一次權限批准，呢個係正常安全保護。普通網頁／手機聊天冇本機 terminal 權限，請改用 Claude Code 或 [Codex App](https://openai.com/codex)。想自己逐步裝就睇 [SETUP.md](SETUP.md)。

---

## 📌 呢個解決咩問題

你對住鏡頭跟稿讀片，每句讀唔順就重讀 —— 一句拍咗三四次，淨係要最後一個 OK 嗰個。但人手喺成條十幾分鐘嘅片入面，逐個揾返邊個 take 好、剪走 NG、收緊抖氣位⋯⋯做到想死。

reel-auto-cut 將呢件事**交俾 AI 做**：你抌條片俾你個 AI 助手（Claude 或者 Codex），佢幫你揾晒邊度重複、剪走 NG、出好字幕，交一份剪好嘅嘢俾你。

**你唔使識寫程式，唔使自己打指令** —— 跟住裝一次，之後抌片俾 AI 就得。

## ✨ 用完你會得到

- 一條**剪好嘅片**：NG、口誤、重複 take 全部剪走，淨返你最 OK 嗰啲
- **自動 punch 放大**：一啲一啲位輕微放大鏡頭（cut-out 效果），一嚟遮住剪接位嘅跳格，二嚟做啲節奏感 —— 唔使你手動 keyframe，開盒即有，唔想要一個掣關得
- **B-roll 自動配對**：你有自己嘅片段素材（cut-away 片、示範片段、screen record 等）？AI 睇你講緊咩，自動揀合適嗰條 b-roll 疊上去對應位置。冇素材就自動跳過，唔影響其他嘢
- 一份**字幕**（`.srt` 檔）：跟你實際講嘅，唔係跟稿
- 一條**字幕燒咗入去嘅成品片**：punch + B-roll 全部落埋，一條龍出 `_final.mp4`；完整睇一次後就可以出街
- 一條**「我剷走咗咩」嘅預覽片**：唔信 AI 剪錯？揿開掃 30 秒就知，唔使盲信
- 一份**成品規格收據**：`--ship` 後會驗 1080×1920／60fps／BT.709，唔合格唔會扮完成

## 🔄 佢點 work（成個流程）

```
你抌一條 raw 口播片
        │
        ▼
  ① 聽寫        whisper 將你把聲轉做逐字時間碼
        │
        ▼
  ②（有 key）捉重複  Gemini 用耳聽返條 audio，揾返 whisper 漏咗嘅重複 take
        │
        ▼
  ③ 決定剪邊度   AI 睇晒，每句揀最後一個完整 take、剪走 NG
        │
        ▼
  ④ 快速驗聲     proof 綁 exact 原片 + EDL；改過刀位就必須重驗
        │
        ▼
  ⑤ 剪 + 放大    剪出成條片，順手落 punch（cut-out 放大）遮剪接位、加節奏
        │
        ▼
  ⑥（可選）配 B-roll  AI 睇你講緊咩，自動揀你嘅素材疊上去對應位置
        │
        ▼
  ⑦ 一鍵打包     剪好嘅片 + 字幕 + 後製指引 + 「剷走咗咩」預覽片
        │
        ▼
  ⑧（可選）成品  字幕燒入 + 規格驗證，再交人眼睇一次
```

技術上係 `whisper`（聽寫工具）+ `ffmpeg`（剪片工具），再按需要加 `Gemini`（可選 AI，負責用耳捉重複、清字幕同揀 B-roll）。冇 Gemini key 都可以行基本剪片；有 key 就會開埋完整 AI 功能。

## 🚀 點用（三步）

1. **裝環境**（一次過，約 10 分鐘）→ 睇 [SETUP.md](SETUP.md) 跟住做，或者直接掉俾 AI 叫佢幫你裝。
2. **抌片俾你個 AI 助手** —— 喺 `reel-auto-cut` 資料夾開 Claude Code（或者將 repo 連結掉俾 OpenAI Codex），講一句：
   > 我有條口播片喺 `~/Desktop/my_reel.mp4`，幫我用 reel-auto-cut 剪。
3. AI 自己讀 [INSTRUCTIONS.md](INSTRUCTIONS.md) 跟住跑。**第一次唔會問你嘢，全部用預設跑**；淨係撞到真係要你揀（例如同一句你講咗兩個唔同版本）先停低問。

GitHub link：<https://github.com/ronaldtsecf/reel-auto-cut>

## 📋 你要準備啲咩

**死要求（冇就跑唔到）：**
- 一部電腦（Mac / Windows / Linux 都得）+ 識開「終端機」（Mac）或者「PowerShell」（Windows）—— 唔識開？叫 AI 一步步教你。
- `Python` 同 `ffmpeg`（兩個免費工具，處理影片同跑程式用）—— SETUP 教你裝，或者叫 AI 幫你。

**可選（有就更好）：**
- 一個 **Gemini API key**（喺 [Google AI Studio](https://aistudio.google.com/apikey) 開）→ 開啟捉漏網重複、字幕清潔同 B-roll 配對；冇 key 基本剪片、punch、HDR、proof 同 final QC 照用得。部分 model 有有限額 Free Tier，實際條件見 [官方 billing 頁](https://ai.google.dev/gemini-api/docs/billing)。
- Apple Silicon Mac（M1 之後嗰啲）→ 自動行 `mlx` 加速，快好多；冇就行 `faster-whisper`，慢少少但一樣得。
- 一個裝住你自己 B-roll 素材嘅資料夾（自己拍嘅片段、screen record、示範片等）→ 想 AI 幫你自動配 B-roll 先要；冇就跳過呢步，其餘功能照跑。

> 🤖 **Gemini key 加咗啲咩？** `whisper`（聽寫工具）有個盲點：你 NG 完重講同一句，佢成日只當你講咗一次，捉唔到你重複咗。`Gemini` 識真係**聽返條 audio** 捉漏網 take，亦會清字幕同睇素材做 B-roll 配對。冇 key 會自動行 basic mode，唔會扮做咗呢三步。

## 🌐 冇 Claude Code？用 OpenAI Codex 都得

將成個 repo（或者 repo 連結）掉俾 Claude / OpenAI Codex，講一句：

> 呢個係廣東話 reel 自動剪輯 kit，讀 INSTRUCTIONS.md，同我一步步跑 —— 由我抌條 raw 片開始。

⚠️ 普通 ChatGPT 網頁 / 手機 app 執行唔到你部機嘅指令，唔得 —— 要用 [Codex app](https://openai.com/codex)（桌面版，ChatGPT Plus 已包）。

## ⚠️ 講明嘅限制

- **淨支援廣東話**（聽寫設定咗 `yue`）。其他語言要自己改。
- **目前 Mac 上驗證最齊**（開發者主力平台）。Windows / Linux 跨平台 engine + encoder 都做咗，理論行得到，但暫時未喺真機完整實測，當實驗性 —— 撞到問題歡迎開 issue。
- Mac 行 `mlx` 最快；Windows / Linux 行 `faster-whisper`，冇 GPU 嘅話一條幾分鐘片可能要跑幾分鐘，要有啲耐性。
- AI 剪接唔係人眼簽收：出街前要睇一次成品，並掃一次 `rejects_preview.mp4`；工具唔會用 silencedetect 靜靜落刀食走低聲句尾。
- HDR 自動轉色要 FFmpeg 有 `zscale`／`tonemap`；`python scripts/preflight.py --strict` 會預先 check。

## License

[MIT](LICENSE) —— 隨便用、改、商用，標返出處就得。

英文版睇 [README.en.md](README.en.md)。覺得有用 star 一下 ⭐

版本記錄：[CHANGELOG.md](CHANGELOG.md)
