# reel-auto-cut — 廣東話口播片自動剪輯

> ⭐ 小白友善｜裝一次約 10 分鐘｜**Mac 最穩，Windows / Linux 實驗性**
> 抌一條 raw 口播片，AI 幫你自動剪走 NG 同重複 take、執好字幕、出成品。

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
- 一條**可以直接出街嘅成品片**（final video）：字幕燒入 + punch + B-roll 全部落埋，一條龍出 `_final.mp4`，唔使再入任何剪片 app
- 一條**「我剷走咗咩」嘅預覽片**：唔信 AI 剪錯？揿開掃 30 秒就知，唔使盲信

## 🔄 佢點 work（成個流程）

```
你抌一條 raw 口播片
        │
        ▼
  ① 聽寫        whisper 將你把聲轉做逐字時間碼
        │
        ▼
  ② 捉重複      Gemini 用耳聽返條 audio，揾返 whisper 漏咗嘅重複 take
        │
        ▼
  ③ 決定剪邊度   AI 睇晒，每句揀最後一個完整 take、剪走 NG
        │
        ▼
  ④ 剪 + 放大    剪出成條片，順手落 punch（cut-out 放大）遮剪接位、加節奏
        │
        ▼
  ⑤（可選）配 B-roll  AI 睇你講緊咩，自動揀你嘅素材疊上去對應位置
        │
        ▼
  ⑥ 一鍵打包     剪好嘅片 + 字幕 + 後製指引 + 「剷走咗咩」預覽片
        │
        ▼
  ⑦（可選）成品  字幕燒入 + punch + B-roll 全部落埋，出 final 直接出街
```

技術上係 `whisper`（聽寫工具）+ `Gemini`（AI，負責用耳捉重複、揀 B-roll）+ `ffmpeg`（剪片工具），**全自動，唔使你掂任何介面**。

## 🚀 點用（三步）

1. **裝環境**（一次過，約 10 分鐘）→ 睇 [SETUP.md](SETUP.md) 跟住做，或者直接掉俾 AI 叫佢幫你裝。
2. **抌片俾你個 AI 助手** —— 喺 `reel-auto-cut` 資料夾開 Claude Code（或者將 repo 連結掉俾 OpenAI Codex），講一句：
   > 我有條口播片喺 `~/Desktop/my_reel.mp4`，幫我用 reel-auto-cut 剪。
3. AI 自己讀 [INSTRUCTIONS.md](INSTRUCTIONS.md) 跟住跑。**第一次唔會問你嘢，全部用預設跑**；淨係撞到真係要你揀（例如同一句你講咗兩個唔同版本）先停低問。

## 📋 你要準備啲咩

**死要求（冇就跑唔到）：**
- 一部電腦（Mac / Windows / Linux 都得）+ 識開「終端機」（Mac）或者「PowerShell」（Windows）—— 唔識開？叫 AI 一步步教你。
- `Python` 同 `ffmpeg`（兩個免費工具，處理影片同跑程式用）—— SETUP 教你裝，或者叫 AI 幫你。
- 一個**免費 Gemini key**（喺 [Google AI Studio](https://aistudio.google.com/apikey) 開，唔使俾錢、唔使綁卡）。

**可選（有就更好）：**
- Apple Silicon Mac（M1 之後嗰啲）→ 自動行 `mlx` 加速，快好多；冇就行 `faster-whisper`，慢少少但一樣得。
- 一個裝住你自己 B-roll 素材嘅資料夾（自己拍嘅片段、screen record、示範片等）→ 想 AI 幫你自動配 B-roll 先要；冇就跳過呢步，其餘功能照跑。

> 🤖 **點解一定要 Gemini key？** `whisper`（聽寫工具）有個盲點：你 NG 完重講同一句，佢成日只當你講咗一次，捉唔到你重複咗。`Gemini` 識真係**聽返條 audio** 捉返晒啲重複 take —— 呢個係成個 kit 嘅靈魂。冇佢就退化成普通剪靜音，市面免費 app 一大堆，唔值得用呢個 kit。所以呢個 key 唔慳得（但係免費）。

## 🌐 冇 Claude Code？用 OpenAI Codex 都得

將成個 repo（或者 repo 連結）掉俾 Claude / OpenAI Codex，講一句：

> 呢個係廣東話 reel 自動剪輯 kit，讀 INSTRUCTIONS.md，同我一步步跑 —— 由我抌條 raw 片開始。

⚠️ 普通 ChatGPT 網頁 / 手機 app 執行唔到你部機嘅指令，唔得 —— 要用 [Codex app](https://openai.com/codex)（桌面版，ChatGPT Plus 已包）。

## ⚠️ 講明嘅限制

- **淨支援廣東話**（聽寫設定咗 `yue`）。其他語言要自己改。
- **目前 Mac 上驗證最齊**（開發者主力平台）。Windows / Linux 跨平台 engine + encoder 都做咗，理論行得到，但暫時未喺真機完整實測，當實驗性 —— 撞到問題歡迎開 issue。
- Mac 行 `mlx` 最快；Windows / Linux 行 `faster-whisper`，冇 GPU 嘅話一條幾分鐘片可能要跑幾分鐘，要有啲耐性。

## License

[MIT](LICENSE) —— 隨便用、改、商用，標返出處就得。

英文版睇 [README.en.md](README.en.md)。覺得有用 star 一下 ⭐
