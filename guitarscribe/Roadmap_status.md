# GuitarScribe 開發進度與待辦事項

> 最後更新：2026-09-14
> 參考規格文件：  
> 1. `GuitarScribe_Web_UI_AI_Handoff.md`（主交接文件）  
> 2. `GuitarScribe_UI_Key_and_Chord_Voicings_Addendum.md`（升降 Key 與和弦指型追加規格）  
> 3. `GuitarScribe_Lyrics_and_Score_Playback_Addendum.md`（歌詞與按譜演奏追加規格）
> 4. `GuitarScribe_Recovery_and_Quality_Plan_v1.0.md`（品質救援與 release gates）
> 5. `GuitarScribe_Reference_Projects_Research_2026.md`（引擎、診斷工具與授權研究）
> 6. `吉他五度圈學習指南.md`（功能和聲、五度圈、轉調與 voice leading）
> 7. `吉他CAGED系統探索.md`（CAGED、音程結構與吉他編配幾何）
>  
> 若兩份文件在移調、Capo 或和弦指型上衝突，以追加文件為準。

---

## 2026-09-14 重新基準化決策

依 `GuitarScribe_Recovery_and_Quality_Plan_v1.0.md`、`GuitarScribe_Reference_Projects_Research_2026.md` 與實際 Live 錄音驗收，原 M0–M6 百分比停止作為出貨完成度。它們只描述工程資產是否存在，不代表拍點、和弦或旋律在音樂上正確。

核心決策：

1. 凍結新匯出格式、自動歌詞、指型美術與大規模 chord vocabulary 擴充。
2. 第一產品目標改為「可信、可修正、可伴奏的 Quick Chord Chart」。
3. 現有主旋律路線停止調參式修補；pYIN 與 Basic Pitch 降級為 stem-first candidate engines，正式輸出必須等待來源分區與 phrase decoder。
4. 修復順序固定為：品質基準／診斷 → Timing bake-off → Canonical TempoMap → Chord bake-off／sequence decoder → Compact lead sheet → Melody reconstruction。
5. 所有第三方引擎先經 adapter、獨立容器、授權審查與相同 golden excerpts 比較，不直接耦合正式 API schema。
6. Live／rubato 保留為 Experimental 壓力測試；第一個 release gate 只採乾淨、穩定 4/4 的合法錄音。

## Legacy Milestone 資產狀態

| 里程碑 | 既有工程資產 | 狀態 | 重新歸屬 |
|---|---|---|---|
| **M0：技術 Spike** | Docker 內 DSP → JSON | ✅ 保留完成資產 | QR0 baseline |
| **M1：後端 MVP** | FastAPI、job、SQLite、OpenAPI | ⚠️ 保留；CPU worker／stage retry 未完成 | QR6 |
| **M2：Web UI MVP** | 上傳、播放、和弦格、匯出 | ⚠️ 保留；預設流程需重整 | QR5 |
| **M3：可編輯樂譜** | 和弦編輯、移調、Capo、指型、revision | ⚠️ 保留；仍依 legacy beat grid | QR2–QR5 |
| **M4：簡化主旋律與 Tab** | 候選音高、Tab、alphaTab、匯出 | 🧪 Experimental；人工辨識驗收失敗 | QR4 |
| **M5：品質與部署** | 自動測試、初步 metrics、Docker | 🔧 重新開啟；缺合法 golden set 與標準 MIR gate | QR0／QR6 |
| **M6：歌詞與按譜演奏** | 手動歌詞、逐行 timing、同步播放 | ⏸ 核心資產保留；自動歌詞／karaoke 暫緩 | QR5 之後 |

**目前位置**：工程骨架可用，但品質救援仍位於 QR0；G1 Timing、G2 Chord Draft 與 G3 Melody 三個音樂品質 gate 都尚未通過。

### Recovery Quality Gates（取代功能百分比作為出貨判斷）

| Gate | 驗收目標 | 狀態 |
|---|---|---|
| **G0 Baseline Ready** | 合法 golden set、版本化標註、baseline artifacts | 🔧 進行中：標註 schema 與 analysis manifest 已建立；仍缺 12–20 首合法標註片段 |
| **G1 Timing Trustworthy** | 16 小節 downbeat 自然、可用少量 anchors 修正 | ❌ 未通過 |
| **G2 Chord Draft Playable** | Easy set 80% 可在 ≤5 次編輯後伴奏 | ❌ 未通過 |
| **G3 Vocal Melody Recognizable** | Easy set 80% 副歌可在 10 秒內辨認 | ❌ 未通過 |
| **G4 Product Flow Usable** | 預設 lead sheet 流程可在 2 分鐘內定位並修正錯誤 | ❌ 未通過 |
| **G5 Live Recording Experimental** | Live／rubato 壓力測試 | 🧪 Experimental，不阻擋首版 |

Melody／Tab 現於 UI 明確標示 Beta／Experimental；未校準的 Melody reliability 百分比與候選事件數不再作為主要品質 KPI。

Recovery 執行紀錄：

- [x] `QA-002`：版本化 quality annotation model 已涵蓋 rights/hash、難度、excerpt、beat/downbeat、chord region、section、melody 與錯誤分類。
- [x] `QA-003a`：`mir_eval` 分層 report 已可獨立輸出 beat/downbeat/tempo/phase、chord root/maj-min/boundary/fragmentation、melody voicing/pitch/chroma 指標及人工聆聽欄位；不產生跨層綜合分數。
- [x] `ARCH-001a`：已定義 versioned analyzer run metadata 與 `TimingResult`、`ChordResult`、`MelodyCandidateResult` canonical candidate contracts；第三方引擎可保存 raw artifact 位置，不必污染正式 `SongScore` schema。
- [x] `TIM-001a`：現有 Librosa 已可輸出 canonical timing candidates，同時保留 0.5×／1×／2× tempo 與四種 phase；每次 job 先保存 `timing-candidates.json` raw artifact 才投影 legacy score，且明確警告 phase 仍為假設。
- [x] `QA-003b1`：quality report CLI 可產生 reference／estimated 的 timing click、chord triad、melody tone 六路 deterministic WAV，供人工分層 A/B 聆聽。
- [x] `QA-003b2`／`REG-001a`：可批次產生不可覆蓋的 baseline/candidate 分層 metrics、delta、source hash 與配對 sonification bundle；失敗時不留下不完整報告。
- [x] `REG-001b1`：batch manifest 保存 baseline/candidate commit、canonical score SHA-256 與完整 analyzer provenance/parameters，並提供 Docker CLI 操作文件。
- [x] `ARCH-001b1`：Chordino／Chromagram 已由共用 adapter 輸出 canonical chord regions，job 先保存 `chord-candidates.json` 再進入正式 chord post-processing；更底層 chroma/frame evidence 尚待保存。
- [x] `UX-002`：分析 reconnect 會區分永久 404 與暫時網路錯誤；過期 job 自動清除 localStorage／URL 並恢復新分析流程，暫時斷線每 2 秒自動重試。
- [x] `DBG-003` 基礎：新分析結果保存 analyzer 版本、選項、vocal separation 結果與 tempo map version；完整參數 hash 待補。
- [x] `UX-001`：Melody／Tab 標為 Beta／Experimental，移除未校準 reliability 百分比。
- [x] `DBG-001`：新分析會保存 Original／Vocal Stem／Raw Detector／Final Melody 四路診斷音訊；Web UI 可在相同 playhead 切換比較。未執行 vocal isolation 時不會假裝存在 Vocal Stem。
- [x] `DBG-002` 基礎：Original waveform 疊加 beat、downbeat/bar、chord boundary、final melody 與 playhead；可點擊或用鍵盤跳至確切時間。區段標記與縮放仍待補。

## Quality Recovery Milestones（目前主 Roadmap）

### QR0：可信基準、Adapter 與診斷環境

**狀態：進行中。退出後開啟 G0 Baseline Ready。**

已完成：

- [x] Original／Vocal Stem／Raw Detector／Final Melody 四路同步 A/B/C/D 音訊。
- [x] 原始 waveform 與 beat、bar、chord、melody、playhead overlay 基礎。
- [x] 版本化 quality annotation schema 與錯誤分類。
- [x] analyzer 名稱、版本、選項、vocal separation 與 legacy Tempo Map version provenance。
- [x] Melody／Tab 標為 Beta／Experimental，移除未校準的單一 reliability 百分比。

下一步：

- [ ] `QA-001` 建立首批 6 首合法 bake-off excerpts（Easy 3、Medium 2、Hard 1），最終擴充至 12–20 首。
- [ ] `REG-001b2` 記錄各 stage 耗時與 CPU/RAM 用量，並以首批合法 excerpts 建立第一份真實 baseline bundle。
- [ ] `ARCH-001b` 將現有 Librosa／Chordino fallback／pYIN／Basic Pitch 以 adapter 接入 canonical contracts，且先保存 raw result 才投影到正式模型。
- [ ] `DBG-002b` 以 wavesurfer.js Regions／Timeline／Minimap 取代目前 provisional canvas，支援縮放與可拖曳區域。
- [ ] `DBG-004` 一鍵保存 `wrong beat`、`wrong chord`、`wrong melody`、`should be silence` 與選取區間。
- [ ] `REG-001` 保存目前 commit、參數、輸出音訊、JSON、metrics 與人工備註為不可覆蓋 baseline。
- [ ] 完成 BeatNet、Omnizart、autochord、Chordino、Demucs 與模型權重的授權／維護決策記錄。

退出條件：至少 6 段合法短片段可重複分析；任一錯誤可在 30 秒內定位到 source、timing、detector 或 post-processing；每次改動可產生 before/after report。

### QR1：Timing Engine Bake-off

**狀態：未開始；依賴 QR0 excerpts 與 metrics。**

- [x] 將現有 Librosa 封裝為 timing baseline adapter，保留 tempo／phase 候選，並明確標示 legacy score 的首拍只是 phase-zero 假設。
- [ ] BeatNet 放入獨立 Python 3.9 optional worker/container；不污染主 Python dependency graph。
- [ ] 對相同 6 段比較 beat、downbeat、tempo、meter、phase error、速度、記憶體與人工 click audition。
- [ ] 保留多個 tempo／meter／phase 候選；不在 benchmark 前直接替換預設引擎。
- [ ] BeatNet license／model redistribution 完成審查後，才能成為 primary candidate；現有 Librosa 保留 fallback。

退出條件：選出一個 timing primary 與一個 fallback；Easy set 至少 80% 可連續聽 16 小節而 downbeat click 自然落在第一拍。

### QR2：Canonical TempoMap 與人工校正

**狀態：未開始；現有 first-beat、half/double、nudge 僅視為 legacy correction tools。**

- [ ] 建立 versioned `TempoMap {beats, downbeats, meter, tempoSegments, pickup, anchors, version}`。
- [ ] 支援 pickup、不完整第一小節、half/double tempo 候選與 1–3 個 timing anchors。
- [ ] anchors 間局部 tempo interpolation，支援穩定曲與有限 tempo drift。
- [ ] Beat／Downbeat audition 使用不同 click；加入 waveform 拖曳與 keyboard correction。
- [ ] chords、melody、lyrics、playback、MusicXML、MIDI 全部只讀同一 TempoMap revision。
- [ ] 加入 first-boundary、pickup、tempo change 與 MusicXML measure regression fixtures。

退出條件：G1 Timing Trustworthy 通過；失敗的 Easy 片段可用第一拍加最多 2 個 anchors 修正，所有下游立即一致 reflow。

### QR3：Chord Engine Bake-off 與可伴奏草稿

**狀態：進行中；現有 beat-synchronous chroma decoder 只作 baseline。**

已完成：

- [x] `CHORD-TH-001` 建立保守的功能和聲 context layer：輸出 Roman numeral 與 tonic／predominant／dominant／secondary dominant／modal mixture／chromatic；辨認 V/x 與 minor-key harmonic dominant。
- [x] `CHORD-TH-002` 只修正低信心、無合理五度解決的調內平行 major/minor 誤判；以獨立 `detected_symbol` 保存原始辨識，不覆蓋高信心 borrowed chord 或 secondary dominant，也不干擾正式和弦的移調來源。
- [x] 和弦卡片顯示 Roman numeral 與 harmonic function；CAGED 仍定位為後段 voicing／voice-leading 編配層，不用指型反推聲學標籤。
- [x] `CAGED-001` major triad 提供完整 C／A／G／E／D movable shape family；minor triad 先提供實用的 A／E／D anchors，刻意不生成不符合人體工學的完整 C／G minor grip。
- [x] `CAGED-002` voicing optimizer 改為整段 dynamic programming，以難度、把位、逐弦手指移動、低音移動與可保留共同音選擇連續指型，不再逐顆只比較 base fret。
- [x] `CHORD-SEG-001` chromagram 先以完整和弦證據輪廓偵測 harmonic change，再為區段指派 label；beat grid 只限制可能邊界，不再強迫每拍各自判定和弦。
- [x] `CHORD-SEQ-001` baseline sequence decoder 結合聲學證據、短事件 change penalty、N.C. 與弱調性／五度解決 prior；樂理只用於接近候選的 tie-break，不禁止 borrowed／chromatic chord。
- [x] `CHORD-QA-001` quality report 增加 boundary precision／recall、事件數與每分鐘密度、1.25 fragmentation gate、review load；低信心 chromatic、理論修正與未被覆寫的孤立 outlier 會在 SongScore／Web UI 明確標記 Review。
- [x] `CHORD-QA-002` change、N.C.、duration/change penalty、五度解決與調性 prior 權重集中為具名 decoder config，並寫入 canonical analyzer provenance，確保 threshold bake-off 可重現。
- [x] `CHORD-QA-003` decoder 參數一路保存到 SongScore provenance；`chord-calibration` 可比較多組完整 run，以 accuracy／boundary／fragmentation error／review load 產生 Pareto frontier，保留人工伴奏試聽作最終決策。
- [x] `CHORD-QA-004` 所有 decoder 校準參數可由 `GUITARSCRIBE_CHORD_*` 環境變數設定，pipeline 使用並自動記錄實值，不需改碼即可產生多組 comparison run。
- [x] `CHORD-QA-005` annotation 的 `acceptable_labels` 正式納入 duration-weighted maj/min 與 root accuracy；報告同時保留 strict／acceptable 指標，calibration 以 acceptable accuracy 避免懲罰明確標註的合理替代簡譜。
- [x] `CHORD-QA-006` 加入具來源雜湊與完整 beat/downbeat/chord ground truth 的 `synthetic-easy-01` quality smoke annotation；明確標示僅驗證 plumbing，不計入 30–60 秒 Easy listening set。
- [x] `CHORD-QA-007` 完成首次端到端 smoke calibration：default 為 4 events／acceptable maj-min 0.936／boundary F 0.667／fragmentation 1.0；conservative 為 3 events／0.749／0.8／0.75。兩者各有取捨而同列 Pareto frontier，因此不以合成短片段更換預設值。
- [x] `CHORD-QA-008` annotation 明確區分 smoke／quality_gate；quality gate 強制 30–60 秒與 source file。`quality-audit` 驗證 schema、唯一 ID、SHA-256、beat/downbeat 與 chord 全區段無縫覆蓋，並輸出是否可進入 calibration。
- [x] `CHORD-QA-009` `quality-annotation-init` 由合法來源音訊建立不可覆蓋的 hashed draft，只填 metadata、不偽造 beat/chord truth；quality gate 必須明確標成 reviewed 並記錄 reviewer 才能通過 audit。
- [x] `CHORD-CAND-001` chromagram 1.3 每個 harmonic region 保存 raw top-3 maj/min/N.C. evidence、acoustic rank 與 decoder-selected 標記；major/minor 理論修正延後至 postprocess，candidate lattice 經 canonical artifact round-trip，能區分聲學候選不足與 sequence prior 選擇錯誤。

- [ ] 在統一 major／minor／N.C. label set 下比較現有 decoder、Omnizart、autochord；Chordino 僅作可選傳統 baseline。
- [ ] 將 harmonic change detector 納入人工標註 excerpt bake-off，依 boundary F-measure 校準 threshold，並與候選引擎共同比較。
- [ ] 以人工標註 excerpt 校準 sequence decoder 權重，並將低信心孤立 outlier 明確標記為 review。
- [x] borrowed chord 保留；低信心孤立 outlier 降權並標記 review，不以 smoothing 強制覆蓋。
- [ ] 自動 report 已包含 duration-weighted chord accuracy、boundary tolerance 與 fragmentation ratio；仍需完成 Easy set 人工伴奏測試。
- [ ] 選定 primary/fallback 後再逐層評估 dominant 7、maj7、min7、sus、slash/inversion。

退出條件：G2 Chord Draft Playable 通過；Easy set 事件數不超過人工參考 1.25 倍，至少 80% 片段可在不超過 5 次編輯下作為伴奏草稿。

### QR4：主旋律重新研究與重建

**狀態：未開始；現有 Final Melody 已確認不可辨認，停止 threshold／smoothing 疊加。依賴 QR2。**

- [ ] Basic Pitch 僅接受單一 vocal／lead stem；full mix 僅可作 diagnostic candidate。
- [ ] Omnizart vocal note／contour 作第二意見，不直接寫正式 SongScore。
- [ ] 先分類 Vocal／Instrumental Lead／No Melody，再依區段選擇來源。
- [ ] 建立 phrase graph，以音程連續性、節奏位置、休止、重複動機及和弦／調性相容度解碼。
- [ ] 合併 vibrato／slide／裝飾音，處理 octave error；輪廓穩定後才量化。
- [ ] 同時保留 humanized timing 與 notated timing；低信心段落保持空白。
- [ ] Melody-only blind recognition test 成為 release gate，不再以 note count 或 detector confidence 驗收。

退出條件：G3 Vocal Melody Recognizable 通過；Easy vocal set 至少 80% 副歌片段可由熟悉歌曲的測試者在 10 秒內辨認。Instrumental lead 與 Live 仍可維持 Experimental。

### QR5：Compact Lead Sheet 與演奏流程

**狀態：未開始；現有收合 UI 與卡片 grid 只作過渡。依賴 QR2／QR3。**

- [ ] 預設入口改為 Quick Chord Chart；Vocal Melody Beta 與 Live Experimental 為次要模式。
- [ ] 結果第一屏顯示 transport、Key／Capo 與前 8–16 小節；進階 analyzer／revision／export 收入 More。
- [ ] 4／8 小節一行，延續用 `%`／延長線；加入 section、repeat collapse 與 virtualization。
- [ ] Chord／Roman Numeral／Nashville Number 切換，非調內低信心事件標示待確認。
- [ ] contextual editor 使用 Bar／Beat／Slot；raw seconds 降為次要資訊。
- [ ] sticky transport 整合 loop、slowdown、metronome、transpose、Capo 與 Undo／Redo。

退出條件：G4 Product Flow Usable 通過；使用者不展開 Advanced 即可跟譜，並能在 2 分鐘內定位與修正一個錯拍或錯和弦。

### QR6：Worker、Cache 與可恢復性

**狀態：部分完成，可與 QR1–QR5 平行。**

已完成：Demucs 非阻塞子程序、30 分鐘 timeout、completed job persistence、恢復 URL、artifact retention 與暫時 polling retry。

- [ ] 所有 CPU-heavy analyzers 移出 Web process，API health check 在任何 stage 都能即時回應。
- [ ] stage 顯示 elapsed time 與合理 ETA range；不假裝精準百分比。
- [ ] 以 input hash、engine/model version、parameter hash cache 每個 stage artifact。
- [ ] Timing／Chord／Melody 可單獨 retry 與版本比較，不重跑 download／separation。
- [ ] server restart 後 active job 可恢復或明確續跑，不只保留 completed result。

退出條件：長分析不阻塞 API；任一 stage 可獨立重跑；重新啟動後工作與 artifact 狀態一致且可解釋。

## 接下來兩個 Sprint

### Sprint A：看得見且量得到的 baseline

1. `ARCH-001` canonical analyzer result interfaces。
2. `QA-003` mir_eval adapter 與分層 report schema。
3. `DBG-002b` wavesurfer.js Regions／Timeline／Minimap。
4. `DBG-004` 選區錯誤標記與 annotation export。
5. `REG-001` baseline artifact manifest／hash／不可覆蓋輸出。
6. 取得首批 6 段合法 excerpts；若資料未齊，完成 synthetic timing/chord fixtures，但不得用它們宣稱音樂品質 gate 通過。

### Sprint B：先修時間，再決定和弦引擎

1. BeatNet optional container 與 Librosa adapter 同片段比較。
2. beat/downbeat sonification、phase 與 drift report。
3. Timing primary/fallback 決策與 license note。
4. TempoMap schema、first downbeat、pickup、anchors 原型。
5. 只在 Timing 候選確定後啟動 Omnizart／autochord chord bake-off。

### 明確暫緩

- 自動歌詞辨識、逐字 karaoke、麥克風評分。
- 新 export 格式、PDF 美術與更多 chord diagram。
- 全曲自動 voicing 最佳化擴充。
- 在沒有 golden before/after report 時繼續調整旋律 threshold、register filter 或 smoothing。
- 直接在主 backend 安裝 BeatNet、madmom、Omnizart、autochord、Essentia 全套依賴。

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
- [x] **OpenAPI 文件**
  - `/docs` 以功能 tags 整理端點；job lifecycle、權利確認與 YouTube resolver 的限制已列入說明。
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
  - 依 `beats[].measure` 分組；小節為外層卡片、和弦在小節內以緊湊 adaptive grid 排列。
  - 小節卡最低寬度 10rem、和弦卡最低寬度 5.25rem；窄螢幕不再強制每個和弦一整列。
  - 旋律時間軸、標準譜、Tab、歌詞與合成播放改為按需展開；手機摘要改為緊湊雙欄，避免長歌曲結果頁過度縱向延伸。
- [x] **JSON 匯出按鈕**（主文件 §4.4）
  - 後端 `JsonScoreExporter` 已存在，但 UI 無下載按鈕
- [x] **ChordPro 匯出**（主文件 §4.4）
  - 後端尚無 ChordPro 格式化器
  - UI 無匯出按鈕
- [x] **節奏建議顯示**
  - 後端回傳的刷奏型已在 UI 顯示上／下刷與空拍。
- [x] **行動版適配**（主文件 §4.1 提到可收合工具列）
  - 結果頁的 arrangement toolbar 在手機寬度改為緊湊雙欄，移調操作與完整寬度按鈕會跨欄；關鍵 Tab／回復原調控制有 Playwright mobile-viewport 覆蓋。
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
- [x] **轉調後重新計算 voicing**（追加文件 §12）
  - 轉調或改 Capo 時，以新的 `shape_symbol`、capo 與最高琴格重建候選，並選擇首個可彈指型供播放／匯出使用；不重跑 DSP。

#### 其他 M3 待辦

- [x] **和弦邊界拖曳**（主文件 §4.3）
  - 選取和弦後可拖曳起始／結束 range handles；邊界受相鄰和弦、歌曲範圍與最短 0.1 秒長度限制，所有變更可 Undo/Redo。
- [x] **新增和弦區段**（主文件 §4.3）
  - playhead 位於既有和弦內時會安全切開該段並以輸入和弦接續；位於空白區則填入至下一個 chord，所有操作皆納入 Undo/Redo。
- [x] **拍點與小節修正**（主文件 §4.3）
  - 已提供整體 beat-grid ±100ms nudge，保持拍距、可 Undo，適合校正全曲一致的 offset。
  - 已提供 half-time / double-time 切換：重新建立 beat／measure 編號並相應調整 BPM，不重跑 DSP，可 Undo。
  - 已可將播放頭所在 beat 設為目前時間，或以 range handle 逐拍拖曳；兩者皆保護相鄰 beat 的排序。
  - 可選擇播放頭所在起算的 1、2 或 4 小節，整段 ±100ms 平移且維持原有拍距與相鄰拍點間隔。
  - 可指定第一個偵測拍為小節內第 1–4 拍，整首重新編排 beat／measure 並支援 Undo，用來修正自動 beat tracker 不知道真正 downbeat 的整體小節相位錯誤。
- [x] **Beat-synchronous 和弦解碼與簡譜式平滑**
  - Chromagram 證據先以偵測拍點聚合，再輸出拍點對齊的和弦段落；低信心、只維持一拍的 A–B–A 假跳動會合併回主要和弦。
  - 調性估算改用整首和弦的時長加權大小調音階／功能相容度，不再直接把出現最多的單一和弦當作主和弦。
- [x] **Undo / Redo**（追加文件 §11）
  - 至少涵蓋 Key、Capo 與 voicing 變更
- [ ] **刷奏型選擇**（主文件 §2.3）
  - 已從 `rhythm-patterns/` 動態載入資料模板，並依每小節和弦變化密度在穩定四分與流動八分刷奏間選擇；無模板時會安全回退。
  - UI 已渲染刷奏型（上刷 / 下刷 / 空拍），並可手動覆寫 pattern，立即影響合成播放與 MIDI；仍待納入 onset strength 等音訊特徵。
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
  - Vocal focus 可逐次分析啟用 Demucs；隔離成功時以單音高 pYIN 追蹤人聲基頻，避免直接從多音 Basic Pitch 候選中猜選旋律。若追蹤失敗則安全改用隔離人聲上的 Basic Pitch；未安裝時安全退回全混音並明確警告。
  - 實際 Live 音檔驗證：隔離後低於 G3 的可疑低音由 170 降至 11，旋律中位音高由 F#3 提升至 F4。
  - pYIN 實測已完全移除低於 G3 的候選；另以 10/90 percentile 音域邊界移除 15 個 B5 以上的孤立離群音，避免 stem 洩漏被當成旋律。
  - 隔離人聲會以 Basic Pitch 做第二次交叉驗證，僅保留重疊且 ±2 半音一致的音符；Live 實測保留 396/478 個 pYIN 音符（82.8%），降低孤立高音誤判。
  - 快速 pYIN profile 以同一首 5.5 分鐘 Live 重跑：輸出 358 音（G3–G5、中位 D4、C5 以上 16 音），相較早期未交叉驗證輸出的 493 音／G3–C6／74 個 C5 以上候選更保守；Demucs 為主要耗時來源。
- [x] `MelodyNote` 資料模型（含 string、fret、source_midi、source_note）

### ❌ 待完成

- [x] **旋律視覺化 UI**
  - 已提供可點擊的 pitch timeline 與小節化五線譜式預覽；長歌 timeline 會限制文字 label 密度，所有音符仍可點擊與由 tooltip 查看。
  - 已提供六線 Tab 時間軸與逐音 string/fret 卡片
- [x] **alphaTab 整合**（主文件 §5.5）
  - 以既有 MusicXML 匯出渲染標準譜與吉他 Tab，採懶載入避免拖慢上傳頁。
  - 暫時沿用 GuitarScribe 的原曲／合成播放時鐘；alphaTab 自帶播放器不啟用，避免雙時鐘不同步。
- [x] **音符量化**
  - 對齊節奏網格（四分、八分、十六分音符）
- [x] **進階指板映射**
  - 已實作連續音符的手位轉換成本最佳化，並提供平衡／低把位／盡量同弦的偏好 UI。
  - 修改偏好或最高琴格時，會立即重新映射 Tab，不需重跑音訊分析。
- [x] **移調後旋律重新映射**（追加文件 §14 M4 影響）
  - Key 或 Capo 改變後 Tab 依新的 sounding pitch 與 capo-relative fret 重新映射，不需重新辨識。
- [x] **MusicXML 匯出**
  - 已依偵測小節切分，保留休止、調號、拍號、標準調弦與音符 string/fret 技術記號，供 alphaTab 顯示可彈 Tab。
- [x] **MIDI 匯出**
  - 旋律與選定 chord voicing 的 accompaniment 分別輸出至 lead（channel 0）與 nylon guitar（channel 1）；即使沒有可信主旋律仍會保留可彈的和弦節奏。
- [x] **旋律 confidence 與品質提示**（主文件 §7.5）
  - 依音符密度、平均信心與來源是否已分離提供可靠性與可讀警告；原始候選音高 debug 輸出仍待補。
  - 可在不重跑 DSP 的情況下套用較嚴格的 confidence／時長／單音輪廓清理，也會移除立即回到原音域的短暫孤立大跳音；可用 Undo 回復完整偵測結果。
  - pYIN 現保留真實 voiced probability，低信心 stem leakage 不會再被硬抬過下游篩選門檻。

---

## Milestone 5：品質與部署

> 主文件 §13 Milestone 5

**目標**：Golden dataset、失敗案例分類、E2E 測試、資源限制、可觀測性、部署文件。

### ✅ 已完成

- [x] Docker Compose 可一鍵啟動（`make build && make serve-stack`）
- [x] 後端完整測試套件（98 項測試，涵蓋 API、分析器、後處理、工作佇列、移調、匯出與評估指標）
- [x] 測試 fixture（合成音訊，不含受版權保護內容）
- [x] README 操作指令

### ❌ 待完成

- [x] **Golden dataset**（主文件 §11.1）
  - 已有合成、可合法使用的 golden baseline；擴充至 10～20 個片段仍待完成
  - `guitarscribe evaluate` 可對 baseline annotations 與 SongScore JSON 執行 BPM error、Beat F-measure、Chord recall、Melody pitch accuracy metrics
  - `evaluate` 可選擇性套用 per-metric quality threshold，門檻失敗會以 non-zero exit code 結束，可作為 CI quality gate。
  - 已加入合成 annotations fixture
- [x] **準確率指標**（主文件 §11.2）
  - BPM 誤差、Beat F-measure、Chord symbol recall、Melody pitch accuracy
- [x] **E2E 測試**（追加文件 §13.4）
  - Playwright 端對端 UI 測試（upload workflow、可編輯 score workspace）
  - 移調往返回到相同 chord
  - Capo 推薦套用
  - 和弦抽屜操作
  - Undo/Redo
- [ ] **非功能測試**（主文件 §11.3）
  - 不合法 URL、過長影片、無音訊軌、worker 重啟
  - 暫存檔清除驗證
  - API 路徑注入防護
  - 併發工作數與記憶體限制
  - [x] YouTube downloader 的無 WAV 輸出與超出下載大小限制已有 isolated tests；過大 WAV 會在失敗前移除。
  - [x] 伺服器重啟時會將進行中的 vocal separation 工作標示為 failed，而非留下卡住的 job。
  - [x] 正規化與人聲分離的每次分析暫存 workspace 會在成功或失敗後清除，並有測試覆蓋。
  - [x] 上傳檔名只會產生短的英數副檔名；job 與同步 API 皆不會採用不可信路徑片段。
- [x] **可觀測性**
  - 結構化日誌
  - 效能指標（分析時間、記憶體用量）
- [ ] **資源限制完善**（主文件 §12）
  - [x] Per-client submission rate limiting（預設每小時 5 次，可設定；多 worker 部署仍需 shared limiter）
  - [x] 分析併發與等待佇列都有可設定上限；佇列滿時會回覆 HTTP 503 與 Retry-After。
  - 檔案大小與 duration 硬限制
  - 匯出檔名特殊字元清理
- [x] **部署文件與備份政策**
  - `docs/OPERATIONS.md` 已涵蓋持久化資料位置、停機備份／還原、資源控制、安全曝露邊界與更新前驗證。
  - GitHub Actions CI：main push 與 pull request 會分別執行 Docker backend pytest、frontend build 與 Playwright E2E。

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
- [x] 自動測試涵蓋十二個 pitch class — 移調測試涵蓋 key、chord root、slash bass 與 melody MIDI pitch class。
- [ ] 匯出格式保持一致 — JSON、ChordPro、LRC、MIDI、MusicXML 已可輸出；PDF 匯出與跨格式視覺校對仍待完成。

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
2. **Chordino 安裝不穩定** — Docker build 自動降級為 Chromagram；fallback 已改為 beat-synchronous 與大小調功能相容度估算，但仍只支援 24 組大小三和弦，不能可靠辨識七和弦、sus、add 或 slash chord。
3. **RhythmSuggester 仍屬保守啟發式** — 已讀取本機 templates 並可手動覆寫，但尚未納入 onset strength 等音訊特徵
4. **標準譜 engraving 有限** — alphaTab 已提供標準譜與吉他 Tab 預覽；複雜記譜的視覺校對仍待補強。
5. **指板映射仍是啟發式** — 已提供平衡／低把位／盡量同弦與最高琴格限制；自訂調弦、手指／換把生物力學與全曲最佳化仍待補強。
6. **無 Major/Minor 模式切換** — 追加文件 §4.2 提到「若功能未實作，UI 不提供模式切換」

---

## Milestone 6：歌詞與按譜演奏

> 依據 `GuitarScribe_Lyrics_and_Score_Playback_Addendum.md` v1.0。核心 MVP 已實作，剩餘項目聚焦在時鐘抽象、音色與自動歌詞能力。

**目標**：使用者可匯入並修正逐行歌詞；原曲或合成樂譜播放時，歌詞、和弦、小節與旋律以同一主時鐘同步高亮。

### 第一階段：資料與歌詞 MVP

- [x] **Lyrics data model 與 schema**
  - 新增 `LyricsTrack`、`LyricLine`、預留 `WordTiming`、source/raw_text/revision/origin/confidence。
  - `SongScore` 與 JSON Schema 納入 lyrics；原始匯入內容與使用者修正版分開保存。
- [x] **歌詞儲存與 revision API**
  - SQLite scores/revisions 持久化已完成；提供 revision-based lyrics read、整體更新與單行 PATCH。每次歌詞 API 修改都 fork 新 revision，保留父版本。
  - 已提供 split 與 merge-next API；分割會按文字比例切分已知 line timing，並重編行號。所有歌詞修改可保存 revision。
- [x] **TXT/LRC 匯入與 LRC 匯出**
  - 使用者貼上文字、TXT、LRC；保留重複段落。
  - 依換行/空行建立 lyric lines，解析與輸出逐行 timestamps。
  - 顯示使用權提示；不抓取第三方歌詞網站，也不提交商業歌詞 fixture。
- [x] **歌詞編輯與手動對時 UI**
  - 已提供匯入、逐行文字編輯、split/merge-next、Set start/end、播放高亮、分配 timing 與可開關的最近拍點 snapping；完成對時的歌詞行可直接拖曳 start/end range handles。所有修改皆標示為 user edit 並納入 Undo/Redo。
  - 播放時高亮目前行與下一行，點擊行可 seek；文字輸入時不攔截快捷鍵。
- [x] **ChordPro lyrics export**
  - 逐行 timing 輸出獨立和弦列並保留 language/source/timing metadata；逐字 timing 將 chord 插入對應 word 前，並跳脫使用者歌詞中的 ChordPro 控制字元。

### 第二階段：播放時鐘與原曲同步

- [ ] **TransportController / master clock abstraction**
  - 原曲模式以 media player 為 master；合成模式以 Web Audio transport 為 master。
  - React render 與 `setInterval` 不得作為音樂時鐘；UI 用 animation frame 讀取 playhead。
  - 原曲模式已補上 animation-frame 讀取 HTMLMediaElement 的 currentTime，讓 chord／measure／melody／lyric highlighter 不再受低頻 `timeupdate` 限制。
  - 已抽出 `transportClock.ts`：media 與 AudioContext clock 都以單一 `now()` 介面提供 score 時間；RAF 僅取樣並渲染，不能推進播放時間。
- [x] **本機音訊播放器與 score sync**
  - 已提供 Play/Pause/Stop/Seek、前後小節、chord/melody/lyric 高亮；media offset 校正仍待完成。
  - 點擊和弦、小節或歌詞可跳轉；保存 `media_offset_seconds` 並提供 ±0.1s 校正。
- [x] **練習控制列**
  - 已提供 A–B loop、目前小節 loop、速度、count-in、metronome 與可開關的 follow-playhead；播放時目前和弦會捲入可視區。
  - 上傳音訊的 time-stretch 未完成前明確顯示限制；YouTube iframe 只使用其支援的速度與容許 drift 校正。

### 第三階段：合成按譜演奏

- [x] **Playback compiler 與 immutable event sequence**
  - 已定義 frozen canonical guitar/melody/metronome events、manifest 與 16 字元內容 revision。
  - 由 score、key/capo、selected voicing 實際音高、rhythm 與 melody 編譯；MIDI 與 Web Audio UI 已讀同一 manifest。
- [x] **Web Audio synth 與分軌控制**
  - 已接 canonical manifest 與 AudioContext clock，提供 score play/pause/stop、Guitar/melody/metronome mute、volume、solo 與合成模式 count-in；原曲與合成播放互斥。
  - 已完成 0.35 秒 look-ahead scheduler：不再在開始播放時建立整首歌的 oscillator；已結束的 source 會釋放。畫面 playhead 仍由 AudioContext clock 經 requestAnimationFrame 推導。
  - 已在頁面回到前景時恢復既有 AudioContext；被背景節流後已逾時的 events 會跳過、持續中的音符會由目前 playhead 重接。
  - 吉他 synth 已有 pick transient、快速 attack、衰減與低通濾波，較容易辨認為撥弦節奏；高品質 sample-based 吉他音色仍待後續資產與授權決策。
- [x] **Voicing-aware chord playback**
  - 已納入 tuning、capo、frets、muted/open strings、actual sounding pitch；down/up strum 現已在 canonical manifest 明確記錄逐弦 12ms spread 與 velocity，Web Audio 與 MIDI 共用此資料。
  - 已加入可手動選擇的 4/4 arpeggio template；manifest 會以較長、但受 rhythm slot 限制的逐弦 spread 編譯，Web Audio 與 MIDI 共用。更多節奏型仍可擴充；key/capo/voicing 變更後會重新編譯受影響 events。
- [x] **Playback API 與 exports**
  - Playback manifest/compile/render endpoints，以及 LRC、ChordPro、MIDI export endpoints。

### 後續實驗與明確排除

- [ ] **歌詞自動對時**：已提供依小節／拍點的結構輔助 fallback；UI 會顯示 Suggested 與各行 confidence，不宣稱為語音辨識或 forced alignment；仍待評估 vocal/ASR timing。
- [ ] **歌詞辨識初稿**：feature flag `FEATURE_LYRICS_TRANSCRIPTION=false`；保留 raw result、不可視為確定歌詞。
- [ ] **逐字 karaoke timing**：不阻塞逐行 MVP。
- [ ] **麥克風追譜與演奏評分**：獨立專案階段，不納入目前 MVP。

### M6 驗收條件

- [x] 使用者可合法貼上或匯入 LRC，完成逐行修正與手動對時。
- [x] 原曲播放時 lyric/chord/measure/melody highlighter 以同一 media clock 同步。
- [x] 合成播放時所有音符由 Web Audio clock 排程，並能依 selected voicing 正確發聲。
- [x] Key、Capo、voicing 改變不重跑 DSP；lyrics timestamps 不被改寫，playback compilation 會失效並重建。
- [x] 不自動抓取/保存未授權歌詞，且含 lyrics 的 JSON/LRC/ChordPro export 可用。
