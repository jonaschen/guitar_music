# Codex：本機交付整體檢查

日期：2026-10-27。受測應用版本：`7db838f`。後續本提交只修正測試定位並補齊驗證文件，不改分析、播放、譜面或 UI 行為。

## 範圍

涵蓋本機來源提交、播放／循環、和弦及既有編輯工具、Undo、保存／恢復、換歌失敗保護、匯出，以及真實既有資料的唯讀匯出。旋律研發維持停止，不重新判定音樂品質；未新增使用者試聽或 UI 驗收。

## 結果與證據

**最終合併結果：後端 703 項通過；瀏覽器 131 項通過、4 項跳過，無未解決失敗。** 瀏覽器數字由首輪及針對性重跑合併，並非第二次全套執行。見 [機器可讀摘要](diagnostics/2026-10-27/release-check/summary.json)。

- 後端完整測試：**703 通過**，80.32 秒；5 個既有依賴棄用提醒。見 [後端紀錄](diagnostics/2026-10-27/release-check/backend-tests.txt)。
- 瀏覽器首輪：135 項中，128 通過、4 跳過、2 失敗、1 未執行。保留 [原始結果](diagnostics/2026-10-27/release-check/frontend-initial.txt)，不把首輪寫成全部通過。
- MusicXML 失敗及同組未執行項目：測試未指定本機 Python，預設 Docker 映像建置逾時。指定現有 runtime 後 **2 項通過**，含 1280px／390px 真實匯出內容的畫面渲染。見 [重跑紀錄](diagnostics/2026-10-27/release-check/frontend-musicxml.txt)。
- 工作區測試：舊定位 `getByText("0.0–8.0")` 同時匹配歌詞時間與新增和弦核對區。改為歌詞區內的精確文字定位，保留原有歌詞時序斷言，重跑 **1 項通過**；見 [重跑紀錄](diagnostics/2026-10-27/release-check/frontend-workspace.txt)。
- 4 項跳過為要求明確 `GUITARSCRIBE_RECOVERY_REVISION` 的既有實驗旋律即時測試；沒有當作通過，不因此重新開啟旋律研究。

前端 production build 已於受測應用版本完成，既有 alphaTab 大型 chunk 提醒仍在；本輪只有測試與文件變更，不重建相同應用。

## 真實資料檢查

對一份《小手拉大手》保存修訂，以及《情非得已》兩個既有分析來源，讀取並送至 MusicXML、MIDI、ChordPro 與播放 manifest 匯出端點：

- MusicXML 可解析，MIDI 可解碼，ChordPro 非空，播放事件可產生。
- 三份 MIDI 都沒有無對應的 note-off 或剩餘未關閉的 note-on。
- 再次讀回保存資料，內容與檢查前一致；報告記錄 score SHA-256。
- 沒有建立 jobs／revisions、沒有來源下載或音訊外傳。

詳見 [三份真實譜的結果](diagnostics/2026-10-27/release-check/real-score-exports.json)。此為結構與可用性檢查，不代表新來源的和弦／旋律品質驗收。MIDI 時長可能包含既有尾音，不將檔案總長相等當作拍長正確率。

## 操作與後續界線

日常入口、啟動、保存及備份見 [收尾與使用說明](Closeout_2026-10-27.md)。完整本機回歸指令已補入 [OPERATIONS.md](OPERATIONS.md)，MusicXML 測試明確指定本機 Python，避免誤用 Docker。

交付定位維持本機和弦核對與修譜工具。已驗收 UI／伴奏不再重測，既有修訂與旋律實驗入口保留；新曲目品質尚不能由這些工程測試保證。後續依實際使用的具體問題修復，不以反覆調參或重複全套測試製造進度。
