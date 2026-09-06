# GuitarScribe 開發進度與待辦事項

> 最後更新：2026-09-06  
> 參考規格文件：  
> 1. `GuitarScribe_Web_UI_AI_Handoff.md`（主交接文件）  
> 2. `GuitarScribe_UI_Key_and_Chord_Voicings_Addendum.md`（升降 Key 與和弦指型追加規格）  
> 3. `GuitarScribe_Lyrics_and_Score_Playback_Addendum.md`（歌詞與按譜演奏追加規格）
>  
> 若兩份文件在移調、Capo 或和弦指型上衝突，以追加文件為準。

---

## 整體進度概覽

| 里程碑 | 目標 | 進度 | 狀態 |
|---|---|---|---|
| **M0：技術 Spike** | Docker 內 DSP → JSON | 100% | ✅ 完成 |
| **M1：後端 MVP** | FastAPI、非同步工作、SQLite、OpenAPI | ~91% | ⚠️ 進行中 |
| **M2：Web UI MVP** | 上傳、進度、播放同步、和弦格、匯出 | ~96% | ⚠️ 進行中 |
| **M3：可編輯樂譜** | 和弦編輯、移調、Capo、和弦指型、revision | ~88% | ⚠️ 進行中 |
| **M4：簡化主旋律與 Tab** | 旋律顯示、指板映射、alphaTab、匯出 | ~88% | 🔧 進行中 |
| **M5：品質與部署** | Golden dataset、E2E 測試、可觀測性 | ~71% | 🔧 進行中 |
| **M6：歌詞與按譜演奏** | 歌詞匯入、時間標記、同步播放 | ~70% | 🔧 進行中 |

**目前位置**：M0 完成；M1、M2 已可供本機試用；M3 的核心編輯與指型流程完成；M4 已有量化、Tab、MIDI/MusicXML 與原生旋律預覽；M5、M6 正在收斂。

---

## Milestone 0：技術 Spike

> 主文件 §13 Milestone 0

**目標**：在乾淨 Ubuntu 主機只需 Docker，即可對合法測試音訊產生 JSON 結果。

### ✅ 已完成

- [x] 本機音訊輸入（`LocalAudioSource`，`backend/app/sources/local.py`）
- [x] FFmpeg 標準化（`FFmpegPreprocessor` → 44.1kHz、mono、16-bit PCM WAV）
- [x] BPM／beat 分析（`LibrosaBeatAnalyzer`，使用 librosa）
- [x] 和弦辨識（`ChromagramChordAnalyzer` 主要引擎，`ChordinoChordAnalyzer` 備選）
- [x] 主旋律分析（`BasicPitchMelodyAnalyzer`，使用 Spotify Basic Pitch）
- [x] JSON 輸出（`JsonScoreExporter`，`SongScore` Pydantic model）
- [x] 端對端測試（`test_pipeline_e2e.py`，含合成 4 和弦 fixture）
- [x] Docker build 正常運作（`python:3.10-bookworm` + FFmpeg + Vamp SDK）
- [x] Makefile 提供 `build`、`serve-stack` 指令
- [x] `SongScore` JSON Schema 定義（`contracts/song-score.schema.json`）
- [x] 合成測試音訊 fixture（`fixtures/audio/test_progression.wav`，8 秒）
- [x] 和弦後處理（平滑、吸附拍點、合併、簡化）
- [x] 旋律後處理（移除極短音符、合併重複音符）
- [x] 指板映射（`SimpleFretboardMapper`，貪婪最低琴格）
- [x] 節奏建議（`RhythmSuggester`，目前靜態 8 分音符刷奏型）
- [x] Chordino 自動降級（Vamp 不可用時自動切換到 Chromagram）
- [x] 實際歌曲分析成功（`output/result.json`，340 秒歌曲產生 798 拍點）

---

## Milestone 1：後端 MVP

> 主文件 §13 Milestone 1

**目標**：FastAPI、工作佇列、SQLite、AudioSource 抽象、OpenAPI 文件。

### ✅ 已完成

- [x] FastAPI 應用程式（`backend/app/api.py`，版本 0.1.0）
- [x] `GET /health` 健康檢查端點
- [x] `POST /analyses` 音訊上傳分析端點（multipart form）
- [x] `POST /scores/transpose` 移調端點
- [x] `POST /revisions` 儲存 revision
- [x] `GET /revisions/{revision_id}` 讀取 revision
- [x] AudioSource 抽象（`sources/protocol.py`、`sources/local.py`）
- [x] CORS 設定（允許 localhost:5173）
- [x] CLI 工具（`guitarscribe analyze` 與 `guitarscribe serve`）
- [x] 錯誤處理（400 權利未確認、404 檔案不存在、422 處理失敗）
- [x] 上傳暫存檔清除（finally block 中 unlink）
- [x] Pipeline 設定管理（`core/config.py`，`Settings.from_env()`）
- [x] 測試：API 端點 5 項、移調 3 項、分析器各 1-2 項、後處理 4 項

### ❌ 待完成

- [x] **非同步工作佇列**（主文件 §9 job lifecycle）
  - 目前 `POST /analyses` 同步阻塞；長歌曲會 HTTP timeout
  - 需要：worker process（Redis + RQ/Celery 或 MVP 獨立 worker）
  - 需要：`POST /api/v1/jobs`、`GET /api/v1/jobs/{job_id}`、`POST /api/v1/jobs/{job_id}/cancel`
  - 需要：工作狀態機（`queued → resolving → preprocessing → beat_analysis → chord_analysis → melody_analysis → postprocessing → completed`）
- [x] **SQLite 資料庫**（主文件 §5.1）
  - 目前 revision 只用 filesystem JSON 檔案
  - 需要：scores、jobs、revisions 持久化
- [x] **工作進度回報**（主文件 §4.2）
  - 前端以 polling 顯示各階段、百分比與取消按鈕；日後可升級為 WebSocket。
- [x] **可選 YouTube resolver**（主文件 §3.1）
  - HTTPS `youtube.com`／`youtu.be` 單影片可由 yt-dlp 轉為 job-local WAV，需逐次權利確認。
  - 預設停用；不接受 cookies、帳密、播放清單或任意下載器參數，完成音檔隨 job TTL 清理。
- [ ] **OpenAPI 文件**
  - FastAPI 自動產生基本文件，但需要補充描述與範例
- [x] **歌曲長度限制**（主文件 §12）
  - 需要：檔案大小、duration、取樣率限制
  - 需要：worker CPU/RAM/磁碟限制
- [x] **暫存 TTL**（主文件 §12）
  - 上傳檔案已清除，但工作目錄中的中間產物需要定期清理

---

## Milestone 2：Web UI MVP

> 主文件 §13 Milestone 2

**目標**：URL／上傳首頁、分析選項、工作進度、結果頁、播放器同步、和弦格、匯出。

### ✅ 已完成

- [x] 首頁上傳表單（支援 .wav/.mp3/.flac/.ogg/.m4a）
- [x] 分析選項（旋律模式：Vocal/Guitar/Mix；和弦複雜度：Simple/Standard/Full）
- [x] 權利確認提示（「You should upload only audio you own…」）
- [x] 分析中狀態（按鈕顯示「Analyzing...」）
- [x] 結果摘要卡片（BPM、拍號、和弦數、旋律音符數）
- [x] 和弦格顯示（4 和弦一組，顯示和弦符號、時間範圍、Shape 符號）
- [x] 錯誤訊息顯示（error banner）
- [x] React + TypeScript + Vite 技術棧
- [x] TypeScript 型別定義（`types.ts`，83 行）
- [x] CSS 樣式（`styles.css`，381 行，含深色主題）

### ❌ 待完成

- [x] **音訊播放器**（主文件 §4.3）
  - 缺少 HTML `<audio>` 元素或 Web Audio API
  - 缺少 YouTube 嵌入播放器
  - 缺少波形（waveform）顯示元件（考慮 wavesurfer.js）
- [x] **播放游標同步**（主文件 §4.3）
  - 缺少：播放游標與和弦格同步
  - 缺少：點擊小節或和弦跳到對應時間
  - 缺少：時間軸視覺化（beat grid overlay）
- [x] **分析進度頁**（主文件 §4.2）
  - 需要分階段進度顯示（準備音訊→尋找拍點→辨識和弦→擷取旋律→整理成譜）
  - 需要取消、逾時、頁面重新整理後恢復
  - 依賴 M1 非同步工作佇列
- [x] **和弦格對齊小節**
  - 目前每 4 個和弦一組，不依照 beat 分析的小節邊界
  - 需要依 `beats[].measure` 分組
- [x] **JSON 匯出按鈕**（主文件 §4.4）
  - 後端 `JsonScoreExporter` 已存在，但 UI 無下載按鈕
- [x] **ChordPro 匯出**（主文件 §4.4）
  - 後端尚無 ChordPro 格式化器
  - UI 無匯出按鈕
- [ ] **節奏建議顯示**
  - 後端回傳 rhythm suggestion，但 UI 未渲染刷奏型
- [ ] **行動版適配**（主文件 §4.1 提到可收合工具列）
  - 目前無 responsive layout

---

## Milestone 3：可編輯樂譜

> 主文件 §13 Milestone 3 + 追加文件全文

**目標**：和弦修改、邊界拖曳、拍點修正、revision、移調與 Capo、和弦指法圖、刷奏型。

### ✅ 已完成

#### 移調系統（追加文件 §4, §9）

- [x] `TranspositionService` 完整實作（`services/transposition.py`，149 行）
  - 十二平均律 pitch class 運算
  - 和弦根音移調（含 extension 保留）
  - Slash chord bass note 同步移調
  - Melody MIDI pitch 與音名同步移調
  - Capo → Shape Key 計算
  - 升降記號偏好（Auto / Prefer sharps / Prefer flats）
  - Auto 模式依調性選擇合理拼法
- [x] `POST /scores/transpose` API 端點
- [x] Source Key / Target Key / Shape Key / Sounding Key 四層分離（`KeyContext` model）
- [x] `audio_matches_notation` 標記
- [x] Source Key 不被移調覆寫（追加文件 §4.4 原則）
- [x] `source_symbol` 保存原始和弦（追加文件 §8.3）

#### Key 工具列 UI（追加文件 §4.1, §4.2）

- [x] 常駐 Key 工具列
- [x] 顯示原曲調性（Source Key）
- [x] 顯示編曲目標調性（Target Key）
- [x] 顯示指型調性（Shape Key）
- [x] `−` / `+` 半音升降按鈕
- [x] 半音差顯示（delta chip：`+2`、`-3`）
- [x] 直接選擇十二個 Target Key（下拉選單）
- [x] 「Back to source key」回到原調
- [x] Capo 選擇器（0 ~ 8）
- [x] 升降記號偏好選擇器（Auto / Prefer sharps / Prefer flats）
- [x] 移調與原曲音高不一致時顯示警告 banner（追加文件 §4.6）

#### 和弦編輯

- [x] 選擇和弦卡片（click to select）
- [x] 修改和弦名稱（rename，標記 `origin: user`、`edited: true`）
- [x] 分割和弦（split at midpoint）
- [x] 刪除和弦
- [x] 側欄編輯面板（顯示時間、origin、source/shape symbol）

#### Revision 管理

- [x] 儲存 revision（file-based JSON）
- [x] 讀取 revision
- [x] 儲存狀態提示

#### 資料模型（追加文件 §8）

- [x] `ChordEvent` 追加 `source_symbol`、`shape_symbol`、`voicing_id`、`available_voicings`
- [x] `ChordVoicing` Pydantic model（id、symbol、shape_symbol、frets、fingers、base_fret、capo、difficulty、tags）
- [x] `KeyContext` model（source、target、shape、sounding、transpose_semitones、accidental_preference、audio_matches_notation）
- [x] `MelodyNote` 追加 `source_midi`、`source_note`
- [x] JSON Schema 同步更新（`contracts/song-score.schema.json`）

### ❌ 待完成

#### Capo 建議工具（追加文件 §5）

- [ ] **`CapoAdvisor` 服務**（追加文件 §9）
  - 評估開放和弦數量、大橫按數量、個別難度、手位轉換成本
  - 排名因素：使用者指定最高 Capo、偏好把位、slash chord 限制
  - 回傳多組方案（Capo 格數、指型調性、難度、橫按數）
- [x] **Capo 建議 API**
  - `GET /api/v1/scores/{score_id}/capo-recommendations`（追加文件 §10）
- [x] **Capo 建議 UI**（追加文件 §5.2）
  - 顯示方案列表（Capo、Shape Key、難度、橫按數、推薦標記）
  - 主文件 §4.1 提到「尋找較簡單按法」按鈕

#### 替代和弦按法（追加文件 §6, §7）

- [x] **`ChordVoicingProvider` 服務**（追加文件 §9）
  - 混合來源策略：靜態驗證資料庫 + 動態 fretboard search
  - 必要音與可省略音判斷（根音、三音、五音、七音、延伸音、slash bass）
  - 可演奏性檢查（最高琴格、手位跨度、手指數、橫按範圍）
- [x] **和弦指型資料庫**
  - 常用和弦人工驗證 fixture
  - 每筆記錄來源與版本
- [x] **`SongVoicingOptimizer` 服務**（追加文件 §9）
  - 動態規劃或最短路徑，最小化前後手位轉換成本
  - Voicing 排名公式（intrinsic_difficulty + barre_penalty + transition_cost 等）
- [x] **和弦指型 API**（追加文件 §10）
  - `GET /api/v1/chord-voicings?symbol=G&shape_key=G&tuning=EADGBE&capo=2&max_fret=15`
  - `PUT /api/v1/scores/{score_id}/chords/{chord_id}/voicing`
  - `POST /api/v1/scores/{score_id}/optimize-voicings`
- [x] **和弦按法抽屜 UI**（追加文件 §6）
  - 六弦圖 SVG 渲染（mute/open/fret、手指編號、橫按）
  - 候選排序（容易度、手位距離、Capo 相容、用途、使用者偏好）
  - 套用範圍選擇（occurrence / section / song）
  - 套用前顯示影響數量
  - 合成音短暫試聽（Web Audio）
  - 依難度、把位、是否橫按篩選
- [ ] **轉調後重新計算 voicing**（追加文件 §12）

#### 其他 M3 待辦

- [ ] **和弦邊界拖曳**（主文件 §4.3）
  - 可拖曳和弦區段的起始／結束時間
- [ ] **新增和弦區段**（主文件 §4.3）
  - 目前只能 split，無法在空白處新增
- [ ] **拍點與小節修正**（主文件 §4.3）
  - 可調整小節起點與拍點位置
  - half-time / double-time 切換（主文件 §7.2）
- [x] **Undo / Redo**（追加文件 §11）
  - 至少涵蓋 Key、Capo 與 voicing 變更
- [ ] **刷奏型選擇**（主文件 §2.3）
  - 從 `rhythm-patterns/` 動態載入模板
  - `RhythmSuggester` 需依 onset strength 與時間特徵選擇
  - UI 渲染刷奏型（上刷 / 下刷 / 靜音 圖示）
- [x] **GuitarSettings model**（追加文件 §8.2）
  - tuning、tuning_name、capo、max_capo、max_fret、handedness、difficulty

---

## Milestone 4：簡化主旋律與 Tab

> 主文件 §13 Milestone 4

**目標**：Melody mode、音符清理量化、指板映射、alphaTab、MusicXML/MIDI 匯出。

### ✅ 已完成

- [x] Basic Pitch 旋律推理（`basic_pitch_adapter.py`）
- [x] 旋律後處理（短音符移除、重複合併）
- [x] 指板映射（`SimpleFretboardMapper`，MIDI → string/fret）
- [x] 旋律模式選項（vocal / guitar / mix）
- [x] **可選人聲隔離品質模式**
  - Vocal focus 可逐次分析啟用 Demucs；未安裝時安全退回全混音並明確警告。
  - 實際 Live 音檔驗證：隔離後低於 G3 的可疑低音由 170 降至 11，旋律中位音高由 F#3 提升至 F4。
- [x] `MelodyNote` 資料模型（含 string、fret、source_midi、source_note）

### ❌ 待完成

- [x] **旋律視覺化 UI**
  - 已提供可點擊的 pitch timeline 與小節化五線譜式預覽
  - 已提供六線 Tab 時間軸與逐音 string/fret 卡片
- [x] **alphaTab 整合**（主文件 §5.5）
  - 以既有 MusicXML 匯出渲染標準譜與吉他 Tab，採懶載入避免拖慢上傳頁。
  - 暫時沿用 GuitarScribe 的原曲／合成播放時鐘；alphaTab 自帶播放器不啟用，避免雙時鐘不同步。
- [x] **音符量化**
  - 對齊節奏網格（四分、八分、十六分音符）
- [x] **進階指板映射**
  - 已實作連續音符的手位轉換成本最佳化；尚未提供偏好 UI
  - 使用者偏好：最容易彈 / 低把位 / 單弦 / 最高琴格限制
- [x] **移調後旋律重新映射**（追加文件 §14 M4 影響）
  - Key 或 Capo 改變後 Tab 依新的 sounding pitch 與 capo-relative fret 重新映射，不需重新辨識。
- [x] **MusicXML 匯出**
- [x] **MIDI 匯出**
- [x] **旋律 confidence 與品質提示**（主文件 §7.5）
  - 依音符密度、平均信心與來源是否已分離提供可靠性與可讀警告；原始候選音高 debug 輸出仍待補。

---

## Milestone 5：品質與部署

> 主文件 §13 Milestone 5

**目標**：Golden dataset、失敗案例分類、E2E 測試、資源限制、可觀測性、部署文件。

### ✅ 已完成

- [x] Docker Compose 可一鍵啟動（`make build && make serve-stack`）
- [x] 基本測試套件（20 項測試，涵蓋 API、分析器、後處理、移調）
- [x] 測試 fixture（合成音訊，不含受版權保護內容）
- [x] README 操作指令

### ❌ 待完成

- [x] **Golden dataset**（主文件 §11.1）
  - 已有合成、可合法使用的 golden baseline；擴充至 10～20 個片段仍待完成
  - baseline annotations 與 BPM/chord/melody metrics 已可執行
  - 已加入合成 annotations fixture
- [x] **準確率指標**（主文件 §11.2）
  - BPM 誤差、Beat F-measure、Chord symbol recall、Melody pitch accuracy
- [x] **E2E 測試**（追加文件 §13.4）
  - Playwright 端對端 UI 測試
  - 移調往返回到相同 chord
  - Capo 推薦套用
  - 和弦抽屜操作
  - Undo/Redo
- [ ] **非功能測試**（主文件 §11.3）
  - 不合法 URL、過長影片、無音訊軌、worker 重啟
  - 暫存檔清除驗證
  - API 路徑注入防護
  - 併發工作數與記憶體限制
- [x] **可觀測性**
  - 結構化日誌
  - 效能指標（分析時間、記憶體用量）
- [ ] **資源限制完善**（主文件 §12）
  - [x] Per-client submission rate limiting（預設每小時 5 次，可設定；多 worker 部署仍需 shared limiter）
  - 檔案大小與 duration 硬限制
  - 匯出檔名特殊字元清理
- [ ] **部署文件與備份政策**

---

## 追加文件整合檢查表

> 追加文件 §17

下列項目必須在宣告追加需求已整合前逐項確認：

- [x] 主文件與追加文件都已閱讀
- [x] Source Key 不會被 UI 移調覆寫
- [x] Target Key 是 arrangement 狀態
- [ ] Capo 與 base_fret 沒有混用 — *model 已分離，但尚無實際 voicing 使用 base_fret*
- [x] Shape Key 與 Sounding Key 有獨立欄位
- [x] Slash chord bass 會一起移調
- [x] Melody notes 會一起移調
- [x] ChordEvent 與 ChordVoicing 已分離
- [x] 和弦事件引用 voicing ID
- [ ] 常用指型資料經過驗證 — *尚無指型資料庫*
- [ ] 動態候選經過可演奏性檢查 — *尚未實作*
- [ ] 可選擇套用範圍 — *尚未實作*
- [ ] 全曲最佳化考慮前後手位 — *尚未實作*
- [ ] 轉調後會重新計算 voicing — *尚未實作*
- [x] YouTube 原曲未變調時有警告
- [x] JSON Schema 與 API 已有版本
- [ ] 自動測試涵蓋十二個 pitch class — *目前測試只涵蓋部分 key*
- [ ] 匯出格式保持一致 — *只有 JSON 匯出，尚無 ChordPro/PDF/MusicXML*

---

## 建議優先開發順序

根據使用者價值與依賴關係排序：

### 第一波：完成 M1/M2 核心基礎

1. **非同步工作佇列**（M1） — 長歌曲不再 timeout
2. **音訊播放器 + 播放同步**（M2） — 跟著原曲練習的核心體驗
3. **和弦格依小節分組**（M2） — 正確對齊音樂結構
4. **JSON / ChordPro 匯出按鈕**（M2） — 快速勝利，高使用者價值

### 第二波：完成追加文件的核心功能

5. **ChordVoicingProvider + 指型資料庫**（追加文件 §6, §7） — 替代把位
6. **和弦圖 SVG 元件**（追加文件 §6.2） — 視覺化指型
7. **CapoAdvisor**（追加文件 §5） — Capo 建議
8. **SongVoicingOptimizer**（追加文件 §7.5） — 全曲最佳化

### 第三波：強化編輯與匯出

9. **和弦邊界拖曳 + 新增**（M3）
10. **Undo / Redo**（M3）
11. **節奏型動態選擇與 UI**（M3）
12. **MusicXML / MIDI 匯出**（M4）
13. **alphaTab 整合**（M4）

### 第四波：品質保障

14. **Golden dataset + 指標**（M5）
15. **Playwright E2E 測試**（M5）
16. **移調 12 pitch class 完整測試**（追加文件 §13.1）
17. **SQLite 持久化**（M1）

---

## 已知問題與限制

1. **Melody 分析在全混音上效果不佳** — 已加入模式化候選線與品質警告；Vocal focus 可於單次 job 勾選 Demucs 人聲分離（伺服器需另行啟用），失敗會安全退回全混音並顯示原因。CPU 隔離一首 5 分半 Live 曲約需數分鐘，適合作為較慢但品質較高的選項。
2. **Chordino 安裝不穩定** — Docker build 自動降級為 Chromagram，但 Chromagram 只支援 24 組大小調
3. **RhythmSuggester 為靜態** — 不讀取 `rhythm-patterns/` JSON 檔案，固定回傳 8 分音符型
4. **完整標準譜 engraving 尚未整合** — 目前提供原生小節化旋律預覽、Tab 與 MusicXML 匯出；alphaTab 需在 Vite 相容性處理後導入。
5. **指板映射為貪婪演算法** — 不考慮前後音符的手位轉換成本
6. **無 Major/Minor 模式切換** — 追加文件 §4.2 提到「若功能未實作，UI 不提供模式切換」

---

## Milestone 6：歌詞與按譜演奏

> 依據 `GuitarScribe_Lyrics_and_Score_Playback_Addendum.md` v1.0。需求已確認，尚未實作。

**目標**：使用者可匯入並修正逐行歌詞；原曲或合成樂譜播放時，歌詞、和弦、小節與旋律以同一主時鐘同步高亮。

### 第一階段：資料與歌詞 MVP

- [x] **Lyrics data model 與 schema**
  - 新增 `LyricsTrack`、`LyricLine`、預留 `WordTiming`、source/raw_text/revision/origin/confidence。
  - `SongScore` 與 JSON Schema 納入 lyrics；原始匯入內容與使用者修正版分開保存。
- [ ] **歌詞儲存與 revision API**
  - 先完成 SQLite scores/revisions 持久化，提供 score-based lyrics API。
  - 實作讀取、整體更新、行 PATCH、分割與合併；所有變更可保存 revision。
- [x] **TXT/LRC 匯入與 LRC 匯出**
  - 使用者貼上文字、TXT、LRC；保留重複段落。
  - 依換行/空行建立 lyric lines，解析與輸出逐行 timestamps。
  - 顯示使用權提示；不抓取第三方歌詞網站，也不提交商業歌詞 fixture。
- [x] **歌詞編輯與手動對時 UI**
  - 已提供匯入、逐行 Set start/end、播放高亮與分配 timing；拖曳、重打與 snapping 仍待完成。
  - 播放時高亮目前行與下一行，點擊行可 seek；文字輸入時不攔截快捷鍵。
- [x] **ChordPro lyrics export**
  - 逐行 timing 輸出獨立和弦列並保留 language/source/timing metadata；逐字 timing 將 chord 插入對應 word 前，並跳脫使用者歌詞中的 ChordPro 控制字元。

### 第二階段：播放時鐘與原曲同步

- [ ] **TransportController / master clock abstraction**
  - 原曲模式以 media player 為 master；合成模式以 Web Audio transport 為 master。
  - React render 與 `setInterval` 不得作為音樂時鐘；UI 用 animation frame 讀取 playhead。
- [x] **本機音訊播放器與 score sync**
  - 已提供 Play/Pause/Stop/Seek、前後小節、chord/melody/lyric 高亮；media offset 校正仍待完成。
  - 點擊和弦、小節或歌詞可跳轉；保存 `media_offset_seconds` 並提供 ±0.1s 校正。
- [x] **練習控制列**
  - 已提供 A–B loop、目前小節 loop、速度、count-in 與 metronome；follow-playhead 仍待完成。
  - 上傳音訊的 time-stretch 未完成前明確顯示限制；YouTube iframe 只使用其支援的速度與容許 drift 校正。

### 第三階段：合成按譜演奏

- [x] **Playback compiler 與 immutable event sequence**
  - 已定義 frozen canonical guitar/melody/metronome events、manifest 與 16 字元內容 revision。
  - 由 score、key/capo、selected voicing 實際音高、rhythm 與 melody 編譯；MIDI 與 Web Audio UI 已讀同一 manifest。
- [ ] **Web Audio synth 與分軌控制**
  - 已接 canonical manifest 與 AudioContext clock，提供 score play/pause/stop、Guitar/melody/metronome mute、volume、solo 與合成模式 count-in；原曲與合成播放互斥。
  - 尚需 lookahead scheduler、背景回復重同步與較自然的吉他音色。
- [ ] **Voicing-aware chord playback**
  - 納入 tuning、capo、frets、muted/open strings、actual sounding pitch。
  - 實作 down/up stroke spread、velocity 與 arpeggio templates；key/capo/voicing 變更後重新編譯受影響 events。
- [ ] **Playback API 與 exports**
  - Playback manifest/compile/render endpoints，以及 LRC、ChordPro、MIDI export endpoints。

### 後續實驗與明確排除

- [ ] **歌詞自動對時**：先做結構輔助 fallback，再評估 vocal/ASR timing 或 forced alignment；每行須有 confidence。
- [ ] **歌詞辨識初稿**：feature flag `FEATURE_LYRICS_TRANSCRIPTION=false`；保留 raw result、不可視為確定歌詞。
- [ ] **逐字 karaoke timing**：不阻塞逐行 MVP。
- [ ] **麥克風追譜與演奏評分**：獨立專案階段，不納入目前 MVP。

### M6 驗收條件

- [ ] 使用者可合法貼上或匯入 LRC，完成逐行修正與手動對時。
- [ ] 原曲播放時 lyric/chord/measure/melody highlighter 以同一 media clock 同步。
- [ ] 合成播放時所有音符由 Web Audio clock 排程，並能依 selected voicing 正確發聲。
- [ ] Key、Capo、voicing 改變不重跑 DSP；lyrics timestamps 不被改寫，playback compilation 會失效並重建。
- [ ] 不自動抓取/保存未授權歌詞，且含 lyrics 的 JSON/LRC/ChordPro export 可用。
