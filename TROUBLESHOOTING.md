# 撞板自救（常見問題）

> ⭐ 小白友善｜揾到對應條目跟住做就得｜Mac / Windows / Linux

呢度收晒最常見嘅情況。每條都係：**你見到咩 → 點解會咁 → 點搞掂**。揾唔到你嗰個情況？開個 issue（GitHub 上面報問題嘅地方）貼返 terminal（終端機，打指令嗰個黑色視窗）嘅 error，唔使客氣。

---

## 📋 1. transcribe 行得超慢（Windows / 冇顯卡）

**你見到咩**
跑到 transcribe（聽寫，將把聲轉做文字嗰步）卡住成幾分鐘甚至更耐，terminal 顯示類似 `engine: faster-whisper (large-v3, cpu/int8)`，CPU 100%、把風扇狂響。

**點解會咁**
唔係 Mac（Apple Silicon）就會用 `faster-whisper`（一個喺普通電腦都行到嘅聽寫引擎），淨靠 CPU 行最大嗰個 `large-v3` model。呢個 model 又大又準，但冇顯卡淨用 CPU 跑就好食力。一段一兩分鐘嘅口播，喺普通 Windows 手提電腦可能要等幾分鐘。**呢個係正常**，唔係壞咗。

**點搞掂**（揀一樣）

- **想快啲：用細啲嘅 model。** 開跑之前設個環境變數（environment variable，臨時話俾程式知用咩設定嘅一句指令），叫佢用 `medium`（細一半左右，快好多，準確度跌少少，口播一般夠用）：
  ```bash
  # Mac / Linux
  export JYUT_WHISPER_MODEL=medium

  # Windows PowerShell
  $env:JYUT_WHISPER_MODEL = "medium"
  ```
  仲想再快可以試 `small`（再細，準確度再低啲，趕時間先用）。設完之後再跑返條 pipeline（成條剪片流程）。
- **有 NVIDIA 顯卡：行返 GPU。** 裝咗 CUDA 版 PyTorch（俾顯卡加速嘅版本）嘅話，pipeline 會自動偵測到顯卡用 GPU，快幾倍。想強制指定可以 `export JYUT_WHISPER_DEVICE=cuda`。
- **唔趕得切就耐心等。** 行得慢唔代表行錯，泡杯嘢飲等佢搞掂。
- **手上有部 Apple Silicon Mac（M1/M2/M3…）就喺嗰度跑。** Mac 會自動行 `mlx-whisper`（食 Metal 加速嘅 Mac 專用聽寫引擎），同樣段片快好多。

> 細 model 換嚟嘅速度，係用準確度補返。如果出嚟啲字明顯亂咗、漏咗，調返 `large-v3`（即係唔設 `JYUT_WHISPER_MODEL`，跟返 default）。

---

## ✨ 2. Windows 成品冇咗字幕 / 字體變樣

**你見到咩**
你跑咗 `--ship`（出最終成品嗰個指令）出成品，但燒入去嘅字幕字體唔對路 —— 變成怪怪哋嘅 fallback（搵唔到正字款時自動補返嘅替代字款），或者根本見唔到中文字。

**點解會咁**
字幕係用一隻指定嘅字體去燒。**冇喺 `config.json`（放你個人設定嘅檔案）揀字體**嘅時候，程式 default 揀 `Hiragino Sans GB`（蘋果系統先有嘅字款）。Windows 冇隻字，搵唔到就會跌返去個亂嚟嘅替代字。

**點搞掂**
喺 `config.json`（冇就 `cp config.example.json config.json` 複製一份範本）寫返一隻**你部機真係有**嘅中文字體，例如 Windows 內建嘅微軟雅黑：

```json
{
  "brand": {
    "subtitle_font": "Microsoft YaHei"
  }
}
```

其他常見可揀嘅：
- Windows：`Microsoft YaHei`、`Microsoft JhengHei`（正體）、`SimHei`
- Mac：`Hiragino Sans GB`、`PingFang HK`、`PingFang TC`
- 跨平台最穩陣：`Arial`（`config.example.json` default 就係佢，英數冇問題，但中文可能要靠系統補字）

寫嘅名要同**系統字體簿（Font Book / 字體設定）入面顯示嗰個英文名一模一樣**，大小階、空格都要啱。改完重新 `--ship` 出多次就得。

> 凈出 rough cut（粗剪片）+ SRT（字幕檔）（唔加 `--ship`）嘅話，字幕係獨立一個 `.srt` 檔，字體由你之後喺 CapCut / 剪片軟件自己揀，呢個問題唔關事。

---

## ⚠️ 3. Gemini 撞限額（429 / quota exceeded）

**你見到咩**
跑到字幕清潔或者 self-eval（AI 自己檢查剪得啱唔啱嗰步）嗰步，terminal 彈 `429`、`RESOURCE_EXHAUSTED` 或者 `quota` 字眼，之後可能見到 `gemini-2.5-flash` 接力再試。

**點解會咁**
Gemini（Google 出嘅 AI，喺呢個 kit 負責用耳仔聽返條片捉重複 take）免費額度（free tier）有**每分鐘 / 每日請求上限**。pipeline 用緊 `gemini-2.5-pro`（聽力最準），撞到限額會自動退去 `gemini-2.5-flash`（細啲、快啲嘅版本）再試一次；連 flash 都撞晒就會報錯。一條片連環跑幾步、或者你短時間內跑幾條片，就容易撞。

**點搞掂**

- **等一陣再跑。** Free tier 限額係滾動式，per-minute 嗰個通常等一兩分鐘就回滿；per-day 嗰個要等到香港時間第二日先 reset。沖返杯嘢飲再 retry。
- **慢啲跑、唔好連發。** 唔好一次過 batch（一次跑一大堆）幾條片落去。一條搞掂、隔陣先落下一條。
- **撞咗喺邊步，淨重跑嗰步就得。** 例如字幕清潔 fail，唔使由 transcribe 重頭嚟（transcribe 有 cache —— 記低咗上次結果嘅暫存，本身唔會重跑，但都係嘥時間）。直接 `bash reel_finish.sh <work_dir>`（打包成品嗰個指令）再行一次，前面 cache 過嘅唔會重做。
- 真係成日撞 → 喺 [Google AI Studio](https://aistudio.google.com/apikey) 入面睇返你個 key（一條開啟 Gemini 嘅密碼匙）嘅 quota / rate limit 現況，或者升上付費 tier（唔逼你，free 一般夠玩）。

---

## 🤖 4. iPhone「空間音訊」片 transcribe 死（codec unknown / no decoder）

**你見到咩**
用 iPhone 錄嘅片，舊版本可能喺抽音（將條片入面把聲抽出嚟）嗰步爆 `no decoder found` / `codec unknown` 之類嘅 ffmpeg（一個處理影片同聲音嘅免費工具）error。

**點解會咁**
iPhone 開咗「空間音訊（spatial audio）」錄出嚟嘅片，入面有條 ffmpeg 解唔到嘅 codec=unknown（音訊格式認唔出）音軌，排喺正常嗰條前面，傻傻地攞第一條就會死。

**點搞掂**
**已經自動處理咗，你唔使做嘢。** pipeline 入面個 `pick_audio_map`（自動揀啱音軌嘅一段邏輯）會自動跳過解唔到嗰條、揀返第一條正常嘅音軌。照跑就得。

> 萬一仲係死：先確認部機真係裝咗 `ffmpeg`（`ffmpeg -version` 試下行唔行到，行到會印返版本號）。再唔得就開 issue 貼返完整 error，可能撞到罕見 codec。

---

## 🔄 5. 改咗條片，但出返嚟係舊嘢（cache）

**你見到咩**
你 trim 過（剪過）/ 換過條 raw 片（未剪嘅原片），但再跑 transcribe 見到 `cache hit`（中咗暫存），出返嘅字同舊版一模一樣，似冇食你新片。

**點解會咁**
transcribe 有 cache：佢用**檔案路徑 + 大小 + 修改時間（mtime）**砌個指紋（一條代表呢個檔案版本嘅獨有編碼）。指紋冇變就當你冇換片，直接攞返舊 transcript 慳時間。如果你係喺**完全唔郁原檔**嘅情況下「以為換咗片」（例如其實改咗 work_dir 入面另一個檔、或者只係 rename），原 raw 片個指紋冇變，所以照中 cache。

**點搞掂**

- **正路：真係改咗原檔，mtime 自動變,就會自動重跑。** 你 re-export / 覆寫 / 重新導入條 raw 片之後，mtime 一定唔同,下次跑會自動 re-transcribe（連帶 `audio.wav`（抽出嚟嗰條聲音檔）都會重抽，唔會用舊嘅）。
- **想硬逼佢重跑：刪走 cache 檔。** 入去對應 out-dir（輸出資料夾，例如 `<work_dir>/final_stt/`）`rm transcript.json`（刪走嗰個暫存檔），再跑就會由頭嚟。
- 確認你跑緊嗰條片路徑，係咪真係指住你改完嗰個檔（唔好改咗 A 檔但 pipeline 指住 B 檔）。

---

## 🚀 6. 冇配 Gemini key，出嚟啲嘢好弱

**你見到咩**
terminal 出現 `冇 GOOGLE_AI_API_KEY → 用 DRAFT（字幕未清潔；配 free key 叻好多）`、或者 `skip self-eval（缺 key …）`。出嚟嘅字幕又多錯別字又斷句怪、重複 take 又冇剷乾淨。

**點解會咁**
**Gemini 係呢套嘢嘅靈魂，唔係 optional（可有可無）。** 兩樣關鍵工序冇佢做唔到：
1. **捉漏網重複 take** —— whisper（聽寫工具）會自動「平滑化」，把結巴、重讀、false start（讀到一半重講）執走，淨靠 whisper 出嚟嘅稿會漏剪。要 Gemini **用耳仔聽返 raw audio** 先捉得返。AI agent（你個 AI 助手）本身冇耳（讀唔到聲），呢樣冇得代替。
2. **字幕清潔** —— audio-first（以把聲為準）對返把聲逐句執正啲字，廣東話口語先唔會變鬼五馬六。

冇 key 嘅時候 pipeline 唔會死，但會 **degraded（降級，出嚟質素打折）**：字幕只係 whisper 原始 draft（未清潔嘅初稿），self-eval 都 skip 埋。**我哋唔推薦咁用。**

**點搞掂 —— 去配返個 free key（唔使綁卡）**

1. 去 [Google AI Studio](https://aistudio.google.com/apikey) 用 Google account 撳「Create API key」，free tier，**唔使填信用卡**。
2. 設做環境變數：
   ```bash
   # Mac / Linux
   export GOOGLE_AI_API_KEY="你個 key"

   # Windows PowerShell
   $env:GOOGLE_AI_API_KEY = "你個 key"
   ```
   想一勞永逸唔使次次設 → 寫入去 shell 設定檔（開 terminal 時自動讀嘅設定檔；Mac/Linux `~/.zshrc` 或 `~/.bashrc`；Windows 用系統環境變數設定）。
3. 設完重新 `bash reel_finish.sh <work_dir>` 跑一次,前面 cache 過嘅唔會重做,淨係補返 Gemini 嗰幾步。

> 撞到 free tier 限額？睇返上面**第 3 條**。
