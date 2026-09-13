# GuitarScribe 現階段分析問題整理

更新日期：2026-09-13  
狀態：依目前 Web UI 實測、5.5 分鐘 Live 錄音診斷結果與既有 Roadmap 彙整

## 1. 摘要

目前系統已能完成音訊上傳、拍點、和弦、旋律、Tab 與多種格式匯出，和弦名稱也大致能辨識出來；但「成功產生資料」不等於「產生可用樂譜」。目前尚未通過人工聽感驗收的核心問題如下：

| 優先級 | 領域 | 現況 | 影響 |
| --- | --- | --- | --- |
| P0 | 主旋律 | 播放後無法辨認原曲，且 Vocal 模式遺漏樂器主奏 | M4 尚不能視為通過 |
| P0 | 拍點／小節 | BPM 可能合理，但 downbeat、小節起點及部分和弦切換點令人疑惑 | 和弦看似正確，演奏時仍無法自然跟歌 |
| P1 | 和弦行進 | UI 顯示逐段辨識結果，但沒有表達調性功能、段落及重複規律 | 使用者看不出編曲邏輯，難以當作市售簡譜使用 |
| P1 | 和弦模型 | Chromagram fallback 僅支援大小三和弦，低信心時仍可能誤判根音或和弦性質 | 七和弦、sus、add、slash chord 與轉位資訊遺失 |
| P1 | 長時間分析 UX | Vocal isolation 在 CPU 上耗時很長；舊版曾阻塞 API 並顯示 `Failed to fetch` | 使用者容易誤以為工作失敗並重複提交 |
| P2 | 結果頁密度 | 長歌曲仍會產生大量小節與和弦卡片 | 頁面需要大量上下捲動，整體結構不易閱讀 |

## 2. P0：主旋律無法辨認原曲

### 使用者觀察

- 合成播放的旋律聽不出是哪一首歌，不只是少數音符不準。
- 主旋律不只存在於人聲；前奏、間奏、尾奏及樂器 hook 也可能承擔歌曲主旋律。
- 開啟 Vocal isolation 後雖能得到較乾淨的單音線，仍不代表該單音線是正確旋律。

### 實測結果

- 完整 Live 錄音的 Vocal isolation 分析已成功完成。
- 使用 `pyin_vocal`，並以 Basic Pitch 在隔離人聲上交叉驗證。
- 最終保留 269 個旋律音符。
- 45 秒診斷片段從 143 個 Basic Pitch 候選收斂到 40 個交叉驗證音符，音域 G3–C5、信心中位數約 0.56。
- 上述數字只能證明結果較稀疏、音域較集中，不能證明旋律可辨認；目前人工聽感驗收仍為失敗。

### 已知原因

1. **分析目標不完整**：Vocal 模式只追蹤人聲，會刻意排除樂器主奏。
2. **Mix 模式不是可靠的主旋律分離器**：它從多音候選中挑選單音，容易選到伴奏、和聲或泛音。
3. **基頻不等於樂譜旋律**：pYIN 會忠實反映滑音、顫音、尾音與音高抖動，但這些需要轉換成較穩定的樂譜音符。
4. **Live 錄音更困難**：觀眾聲、殘響、雙主唱、即興、疊唱與樂器串音都可能殘留在人聲 stem。
5. **目前的交叉驗證偏局部**：只檢查兩套 extractor 在時間與音高上是否相近，尚未檢查整句旋律的節奏、音程輪廓與樂句合理性。
6. **量化可能改變辨識感**：音符被吸附到拍點／半拍後，若 beat grid 本身偏移，旋律節奏也會跟著變形。

### 目前可用但不足的措施

- Vocal isolation + pYIN。
- 移除低信心、過短、極端音域與孤立大跳音。
- Basic Pitch 交叉驗證。
- 使用者可手動執行 `Simplify melody` 並 Undo。

這些措施主要在「減少雜音」，尚未解決「選中真正主旋律」的問題。

### 建議修正方向

1. 建立 **Hybrid lead melody**：有人聲時用 vocal stem；人聲空白區只在偵測到明顯單音主奏時補入樂器旋律。
2. 將 Demucs 的 vocals／other stem 暴露為可播放的診斷音軌，提供「原曲／隔離人聲／偵測旋律」A/B/C 對照。
3. 增加樂句級候選選擇，以音程連續性、重複動機、調內音、和弦音／經過音及節奏位置評分，而非逐音貪婪選擇。
4. 合併顫音與滑音造成的碎片，處理常見八度錯誤；量化強度應依信心調整。
5. 允許將前奏／主歌／副歌／間奏標記成 Vocal、Instrumental lead 或 No melody。
6. 在有可信標註資料前，低信心區應留白，不用伴奏音符填滿。

### 驗收標準

- 使用者只聽 melody track，能在主歌或副歌數秒內辨認歌曲。
- 人聲樂句的主要音高輪廓、停頓與節奏重音可辨認。
- 前奏／間奏若有明確主奏，能顯示相應旋律；純伴奏段可以留白。
- 可分別聽到來源 stem 與輸出旋律，以定位分離錯誤或轉譜錯誤。
- 使用至少數首具人工旋律標註的歌曲評估 note onset、pitch 與 melody contour，不以音符數量作為品質代理。

## 3. P0：拍點、downbeat 與小節對齊令人疑惑

### 使用者觀察

- 和弦名稱大致有出來，但和弦發生的拍點有時不自然。
- 小節分組看似整齊，實際跟著原曲播放時仍可能感到錯位。

### 已知原因

1. Librosa beat tracker 主要估計 pulse，不是真正的 downbeat／bar tracker。
2. 系統過去直接把第一個偵測拍視為第 1 拍；若它其實是弱起或第 2–4 拍，整首小節都會錯一個固定相位。
3. 現場演奏可能有自由速度、pickup、停頓、rubato、half-time／double-time 感知差異。
4. 和弦現在雖聚合到 beat slot，仍完全依賴 beat grid；錯誤拍點會同步影響和弦邊界、旋律量化、Tab 及歌詞對時。
5. 第一個 chord 可能被 snap 到第一個偵測 beat，導致音訊開頭至首拍之間沒有明確歸屬；這也曾造成 MusicXML measure lookup 的邊界錯誤。

### 已完成能力

- 全曲 beat grid ±100 ms。
- 局部 1／2／4 小節範圍平移。
- 單拍拖曳與播放頭設點。
- Half-time／double-time 修正。
- 可指定第一個偵測拍為小節內第 1–4 拍，重排全曲 beat／measure，並支援 Undo。
- Chromagram 已改為 beat-synchronous chord decoding。

### 仍缺少的能力

- 真正的 downbeat／meter estimation。
- 播放時清楚可見的拍號尺、強拍標記與 chord boundary overlay。
- 讓使用者用 tap 或少量錨點校正全曲 tempo map。
- 對變速歌曲使用非等距 tempo map，而非只用單一 BPM 摘要。
- 自動偵測 pickup measure、不完整首小節與休止小節。

### 建議修正方向

1. 導入 downbeat model，並保留人工「第一拍」指定作為最終覆寫。
2. 增加 beat/downbeat audition：只播放節拍器與原曲，強拍使用不同音色。
3. 在 waveform 上同時畫出 beat、bar、chord boundary，讓錯位可以被直接看見。
4. 支援兩個以上 timing anchors，於錨點間重新插值 beat grid。
5. 將 chord snap、melody quantization、lyrics timing 共用同一版可修訂 tempo map。

### 驗收標準

- 強拍 click 在連續 16 小節內能自然落在歌曲第 1 拍。
- 和弦切換能落在實際 harmonic change 附近，不因首拍相位錯誤整首偏移。
- 使用者最多設定首拍與 1–2 個錨點，即可修正一般固定速度歌曲。
- 修正 beat grid 後，和弦、旋律、Tab、歌詞與匯出檔同步更新。

## 4. P1：看不出編曲與和弦行進規則

### 使用者觀察

- UI 目前呈現「每個時間點模型認為是什麼和弦」，但沒有回答：
  - 這首歌在哪個調？
  - 和弦是第幾級？
  - 哪些小節構成同一個樂句？
  - 主歌與副歌是否重複相同 progression？
  - 某個短暫和弦是有意義的 passing chord，還是模型抖動？

### 現有改善

- 和弦證據先聚合到每一拍，再形成 chord event。
- 低信心、只有一拍的 A–B–A 假跳動會合併。
- 調性估算改為依和弦持續時間及大小調相容度評分。
- 低信心的平行大小調抖動會依推定調性正規化，例如 C minor 中的 `Bb–Bbm–Bb` 可整理為 `Bb`。

### 目前限制

1. Chromagram fallback 只有 12 個 major + 12 個 minor triads。
2. 無法可靠表示 7、maj7、m7、sus2、sus4、add9、dim、aug、slash chord 及轉位。
3. 調性估算仍是全曲單一 key；轉調、借用和弦與 secondary dominant 可能被當成錯誤。
4. 沒有 Roman numeral／Nashville Number 標示，也沒有 cadence 或 tonic／predominant／dominant 功能說明。
5. 沒有 song-section segmentation，因此重複主歌／副歌仍逐小節平鋪。
6. 「符合調性」只能作為弱先驗，不能強制所有和弦都 diatonic，否則會刪除真實編曲色彩。

### 建議的市售簡譜式呈現

- 每行固定 4 或 8 小節，而非每小節一張大型卡片。
- 每小節顯示拍位，例如 `| C . G . | Am . . . | F . G . | C . . . |`。
- 和弦延續使用 `%`、`—` 或空拍記號，避免重複卡片。
- 顯示 section label：Intro、Verse、Pre-Chorus、Chorus、Bridge、Solo、Outro。
- 顯示重複記號或 `×2`，不要把完全相同段落全部展開。
- 可切換實際和弦與級數，例如 `C–G–Am–F`／`I–V–vi–IV`。
- 對非調內和弦標示「借用／secondary dominant／待確認」，不要直接自動改掉高信心結果。

### 驗收標準

- 使用者能從一個畫面讀出 8–16 小節和弦走向。
- 可辨識常見 progression、重複段落與 section 結構。
- 低信心短暫和弦不會造成視覺噪音；高信心非調內和弦仍保留。
- 和弦切換位置同時顯示小節與拍號，而不只顯示秒數。

## 5. P1：長時間 Vocal isolation 的工作流程

### 已發生問題

- 舊版使用同步 `subprocess.run()` 執行 Demucs，阻塞 FastAPI event loop。
- UI 輪詢因此顯示 `Failed to fetch`。
- 若使用者在暫時失聯時重新整理，舊前端會刪除 localStorage 的 job ID，結果完成後顯示 `No song loaded yet`。
- 完整歌曲在 CPU 上可能需要 15–25 分鐘，但 UI 曾長時間固定顯示 66%。

### 已修正

- Demucs 改為非阻塞子程序；取消或 timeout 會終止子程序。
- CPU full-song timeout 從 15 分鐘提高到 30 分鐘。
- 暫時輪詢失敗會自動重試，不再立即視為永久分析錯誤。
- 恢復分析時不再因一次 fetch 失敗刪除 job ID。
- 支援 `?job=<job-id>` 的可恢復結果連結。
- UI 會提示 Vocal isolation 在 CPU 上可能長時間停留於 66%。

### 仍需改善

- Demucs 本身沒有細部百分比；應提供經過時間、CPU/GPU 模式及估計剩餘時間。
- pYIN、Basic Pitch、Chromagram 與 beat analysis 仍含 CPU 密集同步工作；應逐步移出 API event loop 或交給獨立 worker process。
- 應讓分析工作跨後端重啟真正續跑，而非只能保留已完成結果。

## 6. P2：UI 頁面仍偏長

### 已完成改善

- 和弦依小節顯示並使用 adaptive grid，不再強制每個和弦獨佔整行。
- 旋律時間軸、五線式預覽、alphaTab、Playable Tab、歌詞與合成播放改為預設收合。
- 手機摘要使用緊湊雙欄。

### 剩餘問題

- 長歌仍將所有小節完整展開，數十至上百小節需要大量捲動。
- 每個 measure card 仍比傳統 lead sheet 佔用更多高度。
- 編輯面板與主要閱讀區分離，選取遠端小節時容易失去上下文。
- 缺少 overview／section navigation／目前播放段落自動聚焦。

### 建議修正方向

1. 預設使用 4 或 8 小節一行的 compact lead-sheet view。
2. 另保留現有 cards 作為 detail edit view。
3. 以 section 收合重複段落，提供 Intro／Verse／Chorus 快速導覽。
4. 使用虛擬列表或只渲染可見區域，避免長歌 DOM 過大。
5. 將播放、拍點與顯示模式控制做成 sticky toolbar。

## 7. 其他已知限制

- Rhythm suggestion 仍是保守規則與模板選擇，尚未充分使用 onset strength、鼓組 pattern 與段落資訊。
- alphaTab 能顯示標準譜與 Tab，但 engraving 與複雜節奏仍需人工校對。
- Fretboard mapping 是可彈性啟發式，不代表最佳指法；自訂調弦與全曲換把最佳化仍有限。
- 尚無 Major／Minor 人工模式切換。
- 曾觀察到 MusicXML 在 chord 早於第一個 measure 起點時發生 measure lookup 錯誤；雖後續請求可成功，仍應加入明確的邊界回歸測試。
- Chordino 安裝不穩定時會使用能力較弱的 Chromagram fallback，部署環境與實際 analyzer 應在 UI 清楚顯示。

## 8. 建議執行順序

1. **建立旋律 A/B/C 診斷播放器**：先確認錯在人聲分離、pitch tracking 或後處理。
2. **Hybrid lead melody 原型與人工標註測試集**：以可辨認度為驗收核心。
3. **Downbeat audition + waveform timing overlay**：讓拍點問題可以快速定位與修正。
4. **Compact lead-sheet view + Roman numeral／section 分析**：呈現編曲與 progression 規則。
5. **背景 worker 化所有 CPU 分析器**：確保長工作期間 API、取消與進度永遠可用。
6. **擴充 chord vocabulary 或穩定 Chordino**：在 timing 與結構可靠後，再增加和弦細節。

## 9. 驗收原則

- 自動測試通過只代表資料結構與程式行為正確，不代表音樂內容正確。
- M4 主旋律必須通過人工「可辨認歌曲」聽感測試。
- 拍點與和弦必須以原曲同步播放驗收，不能只看 JSON 時間排序。
- 樂理先驗應用於排序、提示與低信心修正，不應覆蓋高信心的真實非調內編曲。
- 系統應清楚區分 `Detected`、`Inferred`、`Suggested` 與 `User edited`，避免把推測呈現成確定事實。
