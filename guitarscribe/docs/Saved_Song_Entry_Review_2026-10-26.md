# Codex：不同歌曲的固定伴奏演奏回歸

日期：2026-10-26。工程檢查完成；待《小手拉大手》一次演奏聽感比較。

## 基準選擇

現場與第三來源此前均為《情非得已》，不能當成不同歌曲驗證。盤點《小手拉大手》時，發現原 job 的舊 Librosa／chromagram 拍格與和弦不是此前使用者偏好的 29 秒自動伴奏；因此沒有用舊 job 重新開始調整。

直接重用 `automatic-accompaniment-2026-10-24/score.json` 與 2026-10-25 的已接受 packet。此前回覆為「B 好一些 比之前的版本進步 大致貼合了」，另有「很好 而且刷和弦的聲音也變好了」。內容 29.291979 秒，涵蓋完整句子；來源分析時間 49.957729 秒起，原檔時間另加 18 秒。這比後來 14.466 秒短片段更適合判斷後段是否逐漸錯位。

score、manifest、source.wav、已接受 candidate.wav 均與版本化接受紀錄的 SHA256 一致。當前原版 compiler 的事件亦與當時 manifest 逐項一致，沒有默默替換較佳基準。

## 對照

- A：直接發布已接受的 candidate.wav，SHA256 完全一致。
- B：同一份譜套用 `chord-entry-performance-v1` continuous；不改和弦、拍格、節奏、指型或音色，不再辨識或吸附。
- 16 個和弦跨度中 14 個套用新入口／延音安排；2 個因弦偏移可能跨越和弦末端而保留原演奏，沒有為此歌放寬保護規則。
- 兩版均為 530 個實際弦音；原曲增益 0.45、吉他倍率 1、限制器倍率 1，未個別正規化。B 峰值約 0.620，無截波；RMS 不作音樂品質判定。

這一組只驗證演奏安排能否跨到另一歌曲，不能歸功於伴奏 stem 或新辨識器；此基準本來就是 Chordino 分析原混音的結果。沒有動到 G、使用者工作譜或保存修訂，也沒有外部上傳。

## 驗證與重現

準備腳本：`backend/scripts/prepare_saved_song_entry_review.py`。先固定 protocol 再產物；驗證來源雜湊、原 manifest 保真、輸入不變、非吉他事件不變，並用 mido 獨立解析 A/B MIDI 的 note-on/off，時間誤差須小於 2ms。

於 frontend 執行：

```sh
node scripts/render-chord-attack-diagnostic.mjs ../output/evaluation/saved-song-entry-2026-10-26 saved-song-entry-2026-10-26 scripts/saved-song-entry.html
```

渲染通過弦音排程一致性、無截波、尾端歸零與原控制音檔一致性。頁面檢查 HTTP 200、兩段長度約 29.642 秒（含 release 尾音）、互斥播放及跳轉／續播。小型證據存於 `docs/diagnostics/2026-10-26/saved-song-entry/`，音訊留本機。

## 唯一下一步

請使用者各聽一次 A/B，回答「B 較順／差不多，都可以／A 較順／兩個都不對／聽不清楚」。若有明顯搶拍／拖拍可補一句，不要求秒數、拿吉他或逐和弦標記。

若 B 較差，保留 A，檢查入口移動與延音差異；不對這首歌追加調參。如果相當或較好，也只記為第二首歌這個固定片段的證據，尚非整首或更多來源驗收。旋律品質仍是獨立未解決項目。
