# reel-auto-cut

廣東話口播 IG reel 自動剪輯 kit。抌一段 raw 口播片入嚟，你個 AI agent 幫你**自動剪走 NG / 重複 take**（同一句講咗幾次淨留最後一個完整版本）、整字幕、出成品。剪嗰啲嘢全部留低俾你 review，唔信揿開睇 30 秒。

> 由 Ronald Tse（[@ronald.tcf](https://www.instagram.com/ronald.tcf/)）自己日日用嘅剪片 pipeline generic 化開源。

---

## 核心功能

- **自動揀 take + 剪 NG** —— 每句只留最後一個完整 take，口誤 / false start / 重讀全部剪走
- **兩級 retake-detection（招牌）** —— whisper 轉文字 + Gemini 用耳聽 raw audio 捉返 whisper 漏咗嘅重複。單靠語音轉文字一定漏（佢會自動「執靚」重複位），兩級夾擊先夠乾淨
- **收緊抖氣 + 音畫同步硬化** —— 停頓壓緊湊、A/V 對齊
- **字幕 audio-first** —— 跟你實際講嘅，唔係跟稿（即興改咗稿都對得返）
- **一鍵成品** —— 字幕燒入 + keyword highlight（加 `--ship`）
- **跨平台** —— Apple Silicon Mac 用 mlx 加速 / Windows·Linux 用 faster-whisper，自動揀
- **純 ffmpeg headless** —— 唔使裝 CapCut、唔使 AI 操控你個畫面

---

## 開始之前，講清楚（唔想呃你入嚟先發現裝唔到）

呢個 kit **唔係 app，係俾 AI agent 跑嘅 pipeline**。你要有以下嘢 —— **跟住裝就得**，唔難：

- **行 terminal**（Mac 嘅「終端機」/ Windows 嘅 PowerShell）。唔使識寫 code，但要肯打幾行指令。
- **Mac 或者 Windows / Linux 都得**（跨平台，下面有講分別）。
- **裝 Python 環境 + ffmpeg**（一次過裝，之後唔使再搞）。
- **一個免費 Gemini key**（[Google AI Studio](https://aistudio.google.com/apikey) 開，唔使綁卡）。

**點解一定要 Gemini key？** whisper（聽寫引擎）有個盲點：你 NG 完重講同一句，佢成日只聽到一次，捉唔到你重複咗。Gemini 識真係**聽返條 audio** 捉返晒啲 retake —— 呢個係成個 kit 嘅靈魂，Claude 自己冇耳仔代替唔到。冇 key 都跑得，但淨係識剪靜音停頓，**明明白白話你聽：唔推薦**。

每一步點裝，全部喺 [`SETUP.md`](SETUP.md)，跟住做就掂。

---

## 快速開始

```bash
git clone https://github.com/ronaldtsecf/reel-auto-cut.git
cd reel-auto-cut
```

1. **跟 [`SETUP.md`](SETUP.md) 裝環境**（Python venv + ffmpeg + Gemini key，一次過）。
2. **開你個 AI agent**（Claude Code 喺 `reel-auto-cut/` 入面開），同佢講：

   > 我有條口播片喺 `~/Desktop/my_reel_raw.mp4`，幫我用 reel-auto-cut 剪。

   個 agent 會自己讀 [`INSTRUCTIONS.md`](INSTRUCTIONS.md) 跟住跑。**第一次抌片唔會問你任何嘢**，全部用 default 跑；淨係撞到真係要你決定先停低問（例如同一句你講咗兩個唔同版本，唔知你要邊個）。你改過嘅設定會沉澱入 `config.json`，下次自動變 default。

唔使填問卷，唔使睇文檔，抌條片俾佢就得。

---

## 冇 Claude Code？用 ChatGPT / Codex 都得

唔使裝 Claude Code 都玩得。將成個 `reel-auto-cut` 資料夾（或者 GitHub repo link）丟俾 Claude、ChatGPT 或者 Codex，講一句：

> 呢個 repo 係廣東話 reel 自動剪輯 kit。讀 `INSTRUCTIONS.md`，同我一齊一步步跑 —— 由我抌條 raw 片開始。

佢就會跟住 `INSTRUCTIONS.md` 帶你行完成條 pipeline。

---

## 佢點 work

你抌條 raw 片，個 agent 由頭跑到尾：

```
raw 口播片
  → 聽寫（whisper：Mac 用 mlx 加速 / Win·Linux 用 faster-whisper）
  → Gemini 聽 audio 捉返 whisper 漏咗嘅重複 take
  → agent 睇晒 transcript，每句揀最後一個完整 take、剷走 NG
  → render rough cut（剪好嘅片）
  → 對住剪好嘅片重新聽寫 → 出字幕 → Gemini 清潔字幕做返正字
  → 自動 review 一次，踢走 AI 認錯嘅嘢
  → 一鍵打包：rough cut + 字幕 + briefing + 「我剷走咗乜」嘅 rejects 片
```

EDL（剪輯決定）確認之後，下面一條命令跑晒 Step 4 到打包：

```bash
bash reel_finish.sh <work_dir>           # 出素材包（rough cut + SRT，落 CapCut 微調）
bash reel_finish.sh <work_dir> --ship    # 多出一條字幕燒咗入去嘅成品，直接出街
```

### 跨平台

| 平台 | 聽寫引擎 | 裝法 |
|------|---------|------|
| **Apple Silicon Mac**（M1/M2/M3…） | **mlx**（Metal 加速，快好多） | `requirements.txt` + `requirements-mac.txt` |
| **Windows / Linux / Intel Mac** | **faster-whisper**（CPU / CUDA 都跑） | 淨 `requirements.txt` 就夠 |

`transcribe.py` 自己睇你部機揀引擎，揀完出嚟嘅嘢一模一樣，後面所有步驟唔使理你用邊個。Mac 唔裝 mlx 都跑得，會自動跌返落 faster-whisper。

---

## 點配置

唔改都跑（zero-config）。想改 brand 色、字幕字體、強調詞、廣東話詞彙表、輸出位置：

```bash
cp config.example.json config.json
```

全部欄位都有 default，淨改你想改嗰幾個就得。詳情睇 [`SETUP.md`](SETUP.md)。

---

## 文檔

- [`SETUP.md`](SETUP.md) — 由零裝環境（ffmpeg / Python / whisper / Gemini key）
- [`INSTRUCTIONS.md`](INSTRUCTIONS.md) — AI agent 跑 pipeline 嘅完整流程
- [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md) — 撞板搵呢度

---

## License

[MIT](LICENSE) —— 隨便用、改、商用，保留版權聲明就得。

英文版睇 [`README.en.md`](README.en.md)。覺得有用 star 一下。
