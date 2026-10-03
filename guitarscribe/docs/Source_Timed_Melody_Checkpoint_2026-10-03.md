# 保留來源時值的旋律候選（2026-10-03，待聽感驗收）

## 原因與修正

使用者指出 50–63 秒同時有錯音與時值／小節不合。已確認舊流程會將連續的一個半音變化合併，再吸附到尚未確認正確的八分拍格線，甚至合併短休止兩側同音。這些都可能改變原始人聲節奏，不能靠調音色解決。

新版針對成功人聲分離、有保存 F0 軌跡的 pYIN 結果：

- 短暫半音偏移仍可視為顫音；持續達最小音長的半音換音要分開，邊界回到第一個變化影格，不延遲到確認時刻。
- 維持 pYIN 的取樣率、hop 與 CPU 設定；不重估來源 F0，不加調性限制或強制修音。
- 保留來源音符起訖與短休止，不吸附拍點、不套用混音多音候選選擇、不合併休止兩側同音。
- 保留最小音長／信心門檻；不再以 Basic Pitch 是否支持作為刪除 pYIN 音符的門檻。
- Basic Pitch 與缺少 contour 的舊路徑維持原處理。參數 `melody_note_processing` 記錄所用版本。

## 候選與證據

基準 job：`12fac6df94ee48a282fe2c542df3ae22`，已略過原檔 18.5 秒。使用現存 contour 重新轉譜，沒有重新下載、分離或分析音訊，也沒有修改既有 job／使用者修訂。

輸出：`output/evaluation/source-timed-v2-2026-10-03/`

- `A-current-notes.wav`：該 job 原始分析譜的 50–63 秒（不含之後的人工修訂）。
- `B-source-timed-notes.wav`：新版候選的同一段。A/B 使用相同的逐音合成及音量，B 同時變更分音與後處理，不是單純關閉量化。
- `C-source-contour.wav`：同段連續來源音高，作為參考，不能當成正確答案。
- `candidate-score.json`：整首候選譜；和弦、拍點與刷奏設定完全不動。
- `report.json`：來源 hash、版本及範圍紀錄。

全曲音符數 374 → 552；50–63 秒 25 → 37。對原始 F0 的有聲影格覆蓋 85.9% → 91.9%，有覆蓋影格的平均音高差約 0.429 → 0.176 個半音。這只衡量對來源軌跡的忠實度，不是對歌曲的準確率，亦不能證明增加的音符都是正確音符。

## 發布界線與下一步

程式與測試可提交，但本 checkpoint **不重建正在使用的後台**。先驗收候選聽感，不要求使用者再跑整首分析。原版／候選都是獨立檔案，沒有套用到使用者編輯。

先 A、再 B，每段只有 13 秒。請回報 B 是否較容易辨認旋律、音符長短是否較合理、哪幾秒仍錯；不必逐音標注。必要時用 C 確認問題是否已存在於原始 F0。Bar 30 拍點異常、和弦時機以及非人聲間奏仍未修正；新版也不能只靠 F0 判定連續同音音節的重新起音。

人工聽感通過後才部署新的分析路徑，並另做拍點／和弦對齊實驗，不能把「更忠於 F0」當成全部問題已完成。

## 驗證與試聽入口

- 後端相關回歸：`102 passed, 1 deselected`，涵蓋 pYIN 分音、後處理、pipeline、獨立候選、人工編輯、MIDI 與 MusicXML。
- 瀏覽器實際載入並解碼 A/B/C：三檔皆為 13 秒、有非零音訊；A/B 峰值相同。這不等於人工聽感驗收。
- 前端运行時可直接開啟以下連結，不需重新分析或重啟後台。WAV 是本機產物，不納入 Git；可用本文件所列 CLI 模組重新產生，再複製到 `frontend/public/listening/source-timed-v2-2026-10-03/`。

  - [A：原版音符](http://localhost:5173/listening/source-timed-v2-2026-10-03/A-current-notes.wav)
  - [B：保留來源時值的新版音符](http://localhost:5173/listening/source-timed-v2-2026-10-03/B-source-timed-notes.wav)
  - [C：來源連續音高參考](http://localhost:5173/listening/source-timed-v2-2026-10-03/C-source-contour.wav)

重現候選：在 backend 環境執行 `python -m app.evaluation.source_timed_audit /app/output/work/jobs 12fac6df94ee48a282fe2c542df3ae22 /app/output/evaluation/NEW_DIRECTORY`，輸出目錄必須尚不存在。
