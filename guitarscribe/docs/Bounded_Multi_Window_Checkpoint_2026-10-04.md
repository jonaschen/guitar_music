# G 候選跨段落驗收（2026-10-04）

## 已知聽感

使用者回報 50–63 秒 **G ≈ C，兩者略好於 E**。這是該片段的正向驗收，不代表整首正確；不更動 G 的解碼參數，改測不同段落。

## 本次完成

- 新增 `app.evaluation.bounded_checkpoint`，從唯讀 job／contour 建立獨立 SongScore，拒絕有人工旋律修訂或移調的輸入，避免混用來源。
- 保留來源起點 18.5 秒、和弦、拍點、刷奏與原始警告，增加候選版本及未驗收說明。沒有寫入正式 revision store，也沒有覆蓋工作譜。
- 全曲 1059 個音符均有弦／格；所有 8396 個有聲影格保留，沒有跨原休止新增聲音。部分片段音符仍很密，不能當成完成的傳統節奏排版。
- 產生 `candidate-score.json`、`candidate.mid`、`candidate.musicxml`。JSON 使用既有編輯／修訂資料模型，暫存修訂保存與重新載入測試通過；尚未在使用者 UI 中載入，也不要求現在匯入或取代人工修訂。
- 實際全曲播放 manifest 的旋律音高及起訖逐音等於候選譜。此檢查不等於音樂上與和弦對齊，也不是 MIDI 合奏聽感驗收。
- 70 項相關測試通過，包括候選不可變性、時間、弦格、匯出、暫存 revision、既有旋律編輯及 G 分音。6 個瀏覽器試聽檔均可解碼、13 秒、有非零音訊。

## 本次測試

仍使用 job `12fac6df94ee48a282fe2c542df3ae22`，不重新推論。各段 C／G 採同一合成器、音量及時間範圍；C 是來源軌跡，不是歌曲正確答案。未由樂句標注確認段落種類，因此只稱前段／中段／後段，不冒稱已測所有主歌、副歌或器樂段落。

| 段落 | 分析時間 | 原檔時間 | G 音符數 | 有聲影格遺失 |
| --- | --- | --- | --- | --- |
| 前段 | 10–23 秒 | 28.5–41.5 秒 | 89 | 0 |
| 中段 | 100–113 秒 | 118.5–131.5 秒 | 81 | 0 |
| 後段 | 220–233 秒 | 238.5–251.5 秒 | 27 | 0 |

先聽各段 G，只有聽起來有異常或無法判斷時再對照 C。回報每段「G 接近 C／G 較差」，以及是否聽得出原曲；若 C 與 G 都不對，需回到來源追蹤而非繼續修分音。

連結基底：`http://localhost:5173/listening/bounded-checkpoint-2026-10-04/`，檔名 `early-G.wav`／`early-C.wav`、`middle-G.wav`／`middle-C.wav`、`late-G.wav`／`late-C.wav`。

產物：`output/evaluation/bounded-checkpoint-2026-10-04/`（本機、未納入 Git）。重現：

```sh
python -m app.evaluation.bounded_checkpoint /app/output/work/jobs 12fac6df94ee48a282fe2c542df3ae22 /app/output/evaluation/NEW_DIRECTORY
```

不需重建後台、重新分析、修改工作譜。多段聽感確認後，再安排獨立候選載入與合奏測試；Bar 30–31 拍點及器樂旋律覆蓋仍未解決。
