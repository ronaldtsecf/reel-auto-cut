# 裝機 guide（SETUP）

> ⭐ 小白友善｜裝一次約 10 分鐘（行裝嘅時間不計）｜Mac / Windows / Linux 都得

reel-auto-cut（粵剪）係一個識講人話嘅剪片工具：你抌一條廣東話口播片入嚟，佢幫你剪走 NG / 重複嗰啲 take，出 rough cut（即係初剪好嘅片）+ 字幕 + 素材包。

呢份係由零裝好佢嘅步驟。**逐步跟住做就得**，唔需要識寫 code。每一步都係 copy 一行去 terminal（即係 Mac 嘅「終端機」/ Windows 嘅 PowerShell —— 一個打指令俾部機聽嘅黑色窗）撳 enter。

裝一次，之後就一直用。

---

## 🤖 唔想自己逐步裝？掉俾你個 AI 幫你裝

如果你完全唔想掂 terminal，最簡單做法：**喺 `reel-auto-cut` 資料夾開你個 AI 助手（Claude Code 或者 Codex），將呢份 `SETUP.md` 掉俾佢，講一句：**

> 跟住 SETUP.md 幫我由零裝好 reel-auto-cut，逐步幫我行，撞到要我做嘅嘢（例如去攞 Gemini key）先停低話我知。

AI 會自己 copy 命令落 terminal、check 每步成功、撞到要你親手做嘅（例如登入 Google 攞 key）先停低教你。你淨係跟住佢講做就得。

下面係**逐步詳解**，想自己跟 / 想睇 AI 幫你做緊咩，都睇得明。

---

## 📋 你需要乜（前置）

裝之前確保部機有齊三樣嘢。下面每樣都有教點裝，唔使驚。

1. **Python 3.10 或以上** — 跑個工具嘅引擎（Python 係一種程式語言，呢個 kit 用佢寫）。
2. **ffmpeg** — 處理影片同聲音嘅底層工具（一個業界標準、免費嘅命令列工具）。
3. **一個 Gemini free key** — Google 嘅免費 AI key（key 即係一串密碼，俾個工具同 Google 個 AI 溝通用），用嚟「聽」你把聲捉返 whisper（聽寫工具）漏咗嘅重複 take。**唔使綁信用卡。** 呢個 key 係個工具嘅靈魂，唔好慳（下面第 5 步教攞）。

行呢行 check 下 Python 裝咗未、夠唔夠新：

```bash
python3 --version
```

見到 `Python 3.10.x` 或更高（3.11 / 3.12 都得）就 OK。如果話 `command not found`（即係搵唔到 Python）或者版本細過 3.10，去 [python.org](https://www.python.org/downloads/) 下載最新版裝（Windows 裝嗰陣記得剔 **Add Python to PATH**）。

---

## 📌 Step 1 — 攞個 reel-auto-cut 落本機

如果你識用 `git`（一個管理 code 版本嘅工具）：

```bash
git clone <呢個 repo 嘅 URL>
cd reel-auto-cut
```

如果你唔用 git，喺 GitHub 撳綠色 **Code → Download ZIP**，解壓，再用 terminal `cd`（即係「行入去個資料夾」）入個 folder。

**之後所有命令都喺呢個 `reel-auto-cut` folder 入面行。**

---

## 📌 Step 2 — 裝 ffmpeg

揀返你部機嘅系統，copy 對應嗰一行：

**macOS**（要先有 [Homebrew](https://brew.sh) —— Mac 上裝嘢嘅工具）：

```bash
brew install ffmpeg
```

**Linux**（Debian / Ubuntu）：

```bash
sudo apt update && sudo apt install -y ffmpeg
```

**Windows**（要先有 [Chocolatey](https://chocolatey.org/install) —— Windows 上裝嘢嘅工具，PowerShell 用 admin 開）：

```powershell
choco install ffmpeg
```

裝完行呢行 check：

```bash
ffmpeg -version
```

見到一堆版本資訊（唔係 `command not found`）就成功。

---

## 📌 Step 3 — 起一個 Python 環境 + 裝跨平台依賴

「環境」（venv，即係 virtual environment）即係幫呢個工具開一個獨立嘅 sandbox（一個隔開嘅小空間），唔會搞亂你部機其他 Python 嘢。三行搞掂：

**macOS / Linux：**

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

**Windows（PowerShell）：**

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

裝嗰陣會見到一堆字碌過，正常。裝好之後你個 terminal 行頭應該見到 `(.venv)` — 即係 sandbox 已經啟動。

> **記住：** 之後每次開新 terminal 嚟用 reel-auto-cut，都要先行返 activate 嗰行（`source .venv/bin/activate` 或 `.venv\Scripts\Activate.ps1`）先用得。見到 `(.venv)` 就啱。

`requirements.txt` 入面係 **faster-whisper**（聽你把聲出文字稿，跨晒平台，Windows / Linux / Mac 都行）同 **google-genai**（同 Gemini 溝通嘅工具）。

---

## 📌 Step 4 —（淨係 Apple Silicon Mac）攞 mlx 加速

呢步 **只有 Apple Silicon Mac**（M1 / M2 / M3 / M4 等等 Apple 自家晶片）先做，攞到把聲轉文字快好多嘅加速。**其他平台直接 skip 去 Step 5** — faster-whisper 已經跨平台行得到，唔做呢步一樣剪到片，只係慢少少。

點知自己係咪 Apple Silicon？行：

```bash
uname -m
```

出 `arm64` = Apple Silicon，做呢步。出其他嘢（`x86_64` 等）= 唔好做，會裝唔到。

```bash
pip install -r requirements-mac.txt
```

裝完唔使做任何設定 — 個工具會自動偵測到 mlx（Apple 自家嘅加速框架）就用佢，偵測唔到自動退返 faster-whisper。**zero config（完全唔使你設定）。**

---

## 📌 Step 5 — 攞 Gemini free key

呢個係個工具嘅核心。Gemini 會用對耳聽返你條片，捉返 whisper 漏咗嘅重複 take（例如你同一句講咗兩次，whisper 通常只會出一次，但 Gemini 聽得返）。

1. 去 [Google AI Studio](https://aistudio.google.com/apikey)（用你個人 Google account 登入就得）。
2. 撳 **Create API key**（或 **Get API key**）。**全程唔使綁信用卡**，free tier（免費額度）夠用。
3. copy 個 key（一串 `AIza...` 開頭嘅字）。

跟住將個 key set 入環境（即係話俾部機知呢串密碼，等個工具搵到佢）。揀返你嘅系統：

**macOS / Linux：**

```bash
export GOOGLE_AI_API_KEY="貼你個key喺度"
```

**Windows（PowerShell）：**

```powershell
$env:GOOGLE_AI_API_KEY="貼你個key喺度"
```

> **注意：** 用 `export` / `$env:` set 嘅 key 只係**呢個 terminal window 有效**，閂咗就冇。想一勞永逸，將上面嗰行加入你嘅 shell 設定檔（Mac / Linux 通常係 `~/.zshrc` 或 `~/.bashrc`；Windows 用「環境變數」設定），之後開新 terminal 就自動有。
>
> **安全：** 呢個 key 等於你個 Google AI 帳號嘅鎖匙，**唔好貼上網、唔好 commit 入 git**（即係唔好連個 key 一齊上傳去 GitHub）。

---

## 📌 Step 6 — 整個 config（可改可唔改）

複製一份 config（設定檔）出嚟：

**macOS / Linux：**

```bash
cp config.example.json config.json
```

**Windows（PowerShell）：**

```powershell
copy config.example.json config.json
```

`config.json` 入面係你嘅品牌設定（字幕字款、accent 顏色、要強調嘅字眼、專名 glossary（即係專有名詞對照表，等字幕唔會認錯）、output 資料夾）。**全部有 default（預設值），唔改都跑得到** — 真係 zero config。

之後你用得多，撞到想 fine-tune（微調，例如字幕成日認錯某個專有名詞，或者想轉字款），先返嚟改呢個檔。第一次唔使理佢。

---

## ✅ Step 7 — Smoke test（確認裝好）

Smoke test 即係「開機通電試一試」，確認頭先裝嘅嘢全部 work。最快嘅做法：攞**一條短嘅廣東話口播片**（半分鐘到一分鐘就夠，手機橫掂拍都得），放入一個 work 資料夾，跑文字稿嗰步。呢步同時驗到 ffmpeg、Python 環境、whisper engine 三樣係咪都正常。

```bash
mkdir -p ~/jyut-test
cp 你條片.mp4 ~/jyut-test/raw.mp4
python scripts/transcribe.py ~/jyut-test/raw.mp4 --out-dir ~/jyut-test/stt
```

跑緊嗰陣留意 terminal 會印一行 engine（引擎）資訊：

- Apple Silicon Mac 有裝 mlx → `engine: mlx (...)`
- 其他平台 → `engine: faster-whisper (large-v3, cpu/int8)`

> **第一次跑會慢：** whisper 要下載 model（一個 AI 模型檔，幾百 MB），下載一次之後 cache 住（即係存喺本機，下次唔使再載），第二次就快。下載期間 terminal 好似冇郁係正常，等佢。

跑完見到類似 `wrote .../transcript.json — N words / N segments / Xs`，再行：

```bash
cat ~/jyut-test/stt/transcript.json | head
```

見到你條片講嘅嘢變咗文字（檔案入面有 `words` / `segments`）就代表 **whisper + ffmpeg 全部裝好**。

最後驗 Gemini key 通唔通（呢步要 Step 5 set 咗 key）：

```bash
python -c "import os; from google import genai; genai.Client(api_key=os.environ['GOOGLE_AI_API_KEY']).models.generate_content(model='gemini-2.5-flash', contents='讲一个字'); print('Gemini OK')"
```

見到 `Gemini OK` 就代表個 free key 通咗，全套裝好，可以開始剪片。

> 之後真正剪片，唔使你逐個 script 手動跑 — 你個 AI agent（Claude Code 或 Codex）會幫你跑成條 pipeline（即係由聽寫到打包成品嘅整條流程），最後一命令 `bash reel_finish.sh <work_dir>` 打包。詳細用法睇 `README` / `INSTRUCTIONS`。

---

## ⚠️ 冇 Gemini key 嘅 degraded mode（唔推薦）

**短講：冇 key 都跑得到，但會失去個工具最核心嘅能力，唔建議。**（degraded mode 即係「閹割版」，少咗最重要嗰部分）

冇 set `GOOGLE_AI_API_KEY` 嗰陣，pipeline 唔會 crash（即係唔會死機停低），但有兩樣嘢冧咗：

1. **捉唔返漏網 take。** Gemini 嗰步係用對耳聽你條 raw 片，捉返 whisper 平滑化漏咗嘅重複（同一句講兩次、講到一半 false start（講錯咗從頭嚟過）、窒咗倒返轉頭嗰啲）。冇咗呢個，個工具淨係靠 whisper 嘅文字稿剪，whisper 漏咗嘅就剪唔到 — 即係你成品入面可能仲殘留住重複 take。**呢個正正係 reel-auto-cut 同普通 silence-trim（淨係剪靜音）工具嘅分別，亦都係佢存在嘅理由。**
2. **字幕清潔變返手動。** 字幕嗰步本身都係 Gemini audio-first 清潔（對返你把聲執啱啲字），冇 key 就只出未清潔嘅 draft 字幕（草稿，檔名帶 `_DRAFT`），要你自己手執文字。

冇 key 嗰陣個工具實際淨返做：whisper 文字稿 + 收緊停頓 / silence-trim + 出 rough cut + draft 字幕。係一個普通自動剪片，**唔係** reel-auto-cut 想俾你嘅嘢。

Gemini free key 真係免費、唔使綁卡（[上面 Step 5](#-step-5--攞-gemini-free-key) 兩分鐘攞到），**強烈建議補返先用**。
