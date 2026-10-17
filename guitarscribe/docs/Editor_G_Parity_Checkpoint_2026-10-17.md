# 編輯器與 G 一致性 · 2026-10-17

使用者澄清：簡單試聽頁 G/H 都不錯，較差的是「旋律人工編輯」產生或播放的結果，與 G 有差；簡單試聽方式更輕鬆。停止擴大 H／G decoder 調參。不能將此回饋寫成 H 優於 G，亦不能將先前「沒改善」直接解讀為保存 G 音符辨識失敗。

## 分工與證據

- partner-session 唯讀核對 onAudition、連續音播放及離線合成差異，並覆核 revision 深連結的競態。
- helper-session 查出重整流程會回 job 原譜，新增 7 項 revision-link 測試（包含兩項競態）；沒有讓助手自行改主程式或並行啟動瀏覽器。
- 主線實作、整合及執行瀏覽器驗證。G 保存資料沒有修改。

已確認的產品行為：先前重新整理時 `?job`／activeJobId 載入 job 原分析；已保存／恢復的 G 只顯示為待恢復項。這能重現「編輯區內容不同於保存 G」，但沒有當次使用者瀏覽器快照，因此**不能斷言這就是該次聽感差異的唯一原因**。

主線以實際 5173 App 載入保存 G、選 **文字標籤 Bar 28** 起 8 小節（不可將 option 索引直接當小節數，因有開頭區段）。攔截 AudioContext 為 OfflineAudioContext，仍執行 App 真實 onAudition 與播放函式。67 個音高與起音逐項相等；連續段終點與保存 G 相等。這不是另寫一個相似演算法冒充編輯器。音色、相位、fade 與瀏覽器即時負載仍可能影響聽感，工程相等不代替聽感。

## 修正

- 明確 `?revision=ID` 優先於 `?job` 和 localStorage；讀取該保存譜，不另套 G 或跑分析。指定修訂失敗就顯示錯誤，不回原分析當替代。
- 使用者確認恢復／成功保存後，網址記錄這份 revision；重新整理仍載入該版本。無 revision 的原分析網址維持原意。
- 讀取檢查 request 及工作世代，取消／其他恢復／新分析使舊回應失效。
- 新分析通過輸入驗證、送出前就取消舊啟動恢復；建立成功後網址改為新 job，移除 revision。
- 保存回應也核對工作世代，避免在新分析尚未完成、score identity 仍相同時，把新 job URL 改回舊保存版。
- 不自動保存未保存修改；原有離頁提示、Undo、保存新修訂與工作世代保護保留。

## 工程驗證

新增 `revision-link.spec.ts`：URL 優先、恢復／保存與重整同版、失敗不回原譜、晚到版本、新分析清網址，以及新分析建立／舊保存回應競態。

新增 opt-in `editor-audio-parity-live.spec.ts`：真實 G 深連結與重整、67 音逐項音高／起音、連續段終點、實際離線音訊非靜音、保存資料前後全欄相等。禁止頁面持久化 POST；唯一允許的 POST 為無持久化的 MusicXML 轉換。輸出 `editor.wav` 為真實 App 路徑合成，扣除 30ms 排程前置空白，固定增益由 .16 配為 .3 與參考 G 一致；未改頻率或音長。

第一次專項 5 項通過、1 項測試 fixture 錯誤：預設完整模式卻點「顯示完整工具」。助手修正明確種入 focus，另補兩項競態。完整統一執行 TypeScript／Vite build 通過，70 項回歸中 68 項通過、2 項新測試因音訊／LRC 上傳欄位定位不唯一失敗；修正測試為音訊專用 selector，產品程式未改。其後 7 項 revision-link 與 3 項真實 G／音訊驗證全部通過（1.4 分鐘）。合計 70 項相關回歸、3 項真實驗證各自通過，不能寫成第一次全套一次通過。

紀錄：`/tmp/guitarscribe-workflow-verification/verification-20261017T131339Z.txt` 與 `/tmp/guitarscribe-editor-parity-final.log`。最終公開 editor.wav 與 live test 輸出逐位元相同，SHA-256 `0d6699e607bff97340f5d8d78646838e368c783718249ab5f359fb1489124650`。

## 唯一簡單試聽

[原曲／G／編輯器比較](http://localhost:5173/listening/editor-parity-2026-10-17/index.html)。同段約 14.466 秒，按一次依序播放，約 45 秒。第 3 段由載入保存 G 的真實編輯器合成；只問「第 3 段是否仍有先前的零落感」。頁面也提供另開同一 G 修譜的明確深連結，不要求使用者先找版本或切選段。

生成頁面的來源模板為 `frontend/scripts/editor-parity.html`。音訊來自 live parity 測試的 `editor.wav`；G/source 使用上一輪已確認的 `output/evaluation/transition-final-2026-10-17/{G,source}.wav`。本機試聽檔置於 `frontend/public/listening/editor-parity-2026-10-17/`，生成產物不納入 Git。須使用明確 `index.html` 路徑。

若第 3 段良好，版本流程修正後再觀察編輯，不回頭重調 decoder；若仍較差，再聚焦合成差異。若離線編輯器良好但即時播放差，接續查即時音訊排程及環境，不能再以猜測音符品質代替診斷。
