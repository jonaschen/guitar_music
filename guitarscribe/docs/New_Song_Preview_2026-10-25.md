# 新曲目與專注 UI 預覽

本輪目標是把固定引擎接進上傳／分析／編輯／保存流程，讓下一首歌可以直接測試。跨曲音樂品質仍待驗收；不重開單曲逐秒調參。

## 操作

1. 開啟 http://localhost:5173，按「分析新曲目」。選擇有權使用的音檔，或輸入 YouTube 連結。
2. 指定人聲開始附近的秒數，先保留 45 秒與完整和弦。人聲分離可用時預設啟用；新曲不覆寫舊譜。
3. 分析完成後，在專注編輯區聽原曲與合奏。旋律版本標示區分原分析與 G 候選；G 仍需明確產生、套用，可 Undo。
4. 只需回報：歌曲／開始秒數、伴奏是否一路合拍、旋律是否大致可辨認、哪個 UI 步驟卡住。明顯問題附大約秒數即可，不必逐音記錄。

YouTube 能力表示下載器已安裝並啟用，不保證所有影片可下載；失敗時可改用本機音檔。完整混音的器樂前奏／間奏仍不是已驗收能力。

## 執行與還原

本機預覽後端：`bash backend/scripts/run_local_preview.sh`（可在任意目錄透過腳本完整路徑啟動）。前端：在 `frontend` 執行 `npm run dev -- --host 127.0.0.1 --port 5173 --strictPort`。啟動前確認沒有現存服務占用連接埠；進行中的分析不得重啟。

腳本明確啟用 Beat This small0 CPU＋Chordino、Demucs、人聲分析及本機 rhythm-patterns。程式的通用預設不變；`/api/v1/capabilities` 回報實際可用能力。明確指定 Chordino 卻缺插件時報錯，不偷偷退回舊引擎。

本機資料仍在 `output/work`，啟動前已用 SQLite backup 備份 jobs 與 revisions 至 `output/runtime/backup-*`。預覽工作保留期限設為十年，防止舊來源因預設一天 TTL 被清理。已認可 G revision 與 B 試聽產物不改寫。

本機 Python 在 `~/.cache/guitarscribe-runtime`；Chordino host／插件在 `~/.cache/guitarscribe-chordino-diagnostic`。Python 3.12 的 Basic Pitch 0.4.0 使用 ONNX runtime 1.31.0：套件以 `--no-deps` 安裝，再補 ONNX、pretty-midi、resampy 等執行依賴，因上游 TensorFlow <2.15.1 限制無相容 wheel。已實測 ONNX 推論；這不是宣稱上游標準依賴解析或 pip check 全綠。Demucs 4.0.1、torch／torchaudio 2.5.1 CPU；模型沿用已下載 cache。

## 工程限制

- 30／45／60 秒為新 UI 分析範圍；API 可選大於零、至多 600 秒，省略保持舊整首行為。裁切副本保留來源開始秒數，原上傳檔不改動。
- 原始拍點／和弦及模型來源保存在 job artifacts；播放與 MIDI 沿用同一工作譜。
- 不一致的 3/4／4/4 拍點會明確失敗，沒有用刪尾、手工搬拍或靜默換引擎掩飾。
- 重型音樂推論移出 API event loop；取消時等待背景推論退出才清理檔案與釋放工作名額。
- 選檔、分析失敗保留舊譜；未保存修改及分析期間新修改都有確認保護。

## 本輪實機紀錄

- 真實上傳 job：`ac1a64df00a24af3aef443b7e1fb54b9`，要求45秒、來源約29.29秒。拍點64個、和弦16個；逐項符號及時間與已認可 B 原始分析完全一致，沒有逐曲校時。節奏同為 pop_4_4_8th_01，刷向／強弱一致。
- Demucs 分離成功，pYIN 原分析77音符；明確產生與套用 G 後136音符。這是新片段候選，不是把全曲已保存1072音符覆蓋成136音符。
- 獨立瀏覽器實測原曲播放、G產生／套用、合奏、保存內容等於送出工作譜、重載；manifest 有295個事件、同時含吉他與旋律，無頁面 JavaScript 錯誤。工程 revision：`25f60bdb-a3a6-475f-b6cf-3eef123f9abb`。腳本 `frontend/scripts/smoke-new-song.mjs` 須明確提供已完成 job ID 與輸出目錄，會新增獨立修訂。
- 首次冷啟動分析耗時291.65秒，當時同時跑全套回歸且本機有記憶體壓力；這不是穩態效能數字，也不承諾即時處理。進度可能停在人聲分離一段時間。
- 後端首輪全套589通過、3失敗：非有限數的驗證錯誤無法序列化。已修正標準422回應並以新舊API共39項重跑通過；實際服務送入 NaN 亦回422。沒有把首輪寫成全綠。
- 前端首輪83通過、11失敗、4略過、1未執行；失敗包含新能力API缺少測試mock與Docker fixture逾時。補齊mock、以本機Python產生同一MusicXML fixture後11項補跑通過；未放寬譜面或音樂斷言。新增G流程測試另有全形文字selector失敗，修正後通過。TypeScript與production build通過（仍有既有大型bundle提示）。
- 前端合併首輪與必要補跑覆蓋98項通過、4項略過，無剩餘失敗；不是單次全套全綠。failed／cancelled清理另補2項通過，避免已結束的新分析繼續被當作進行中。
- SQLite 備份中的4份既有 score／revision 逐列保持一致；B score／manifest SHA 仍與驗收紀錄相同。實機 smoke 另存兩份工程候選，不取代舊版本。

產物、截圖與機器紀錄保存在 `output/runtime/`，不納入 Git。
