# 來源音高有界分音候選（待聽感驗收）

## 回饋與實作

使用者排序 C > E > D，之前 C > B > A。來源 F0 仍是較好的聽感參考，不宣稱離散音符已通過。新實驗不改寫 job、revision、來源音訊或正式分析路徑。

`app.evaluation.conservative_notes` 提供兩種非正式解碼：

- F：只合併前後同音、中間一至兩影格且距半音分界至多 0.15 半音的孤立變化；不跨休止、不連鎖合併。全曲 1501 → 1459 音符。50–63 秒與 E 相同，因此不要求使用者重聽。
- G：每個連續有聲區段內，以動態規劃選擇整數 MIDI 音高。最小化逐影格音高平方誤差，加上 0.35 的換音成本；每個影格偏離原始 F0 不得超過 0.6 半音。沒有最小音長、信心刪音或拍點吸附。短暫但明確的半音變化不能被直接吸收，模糊分界則可減少來回換音。參數是待驗證假設，不是已校準的音樂標準。

兩者都保留原有聲／無聲遮罩、來源時間與信心值，只有診斷檔案，尚未配置正式譜面、MIDI 或播放預設。

## 實際歌曲量測

来源 job `12fac6df94ee48a282fe2c542df3ae22`，原檔略過 18.5 秒。

- G 全曲 1059 音符，相較 E 的 1501 少約 29%；仍可能過密，不能當成成熟可讀樂譜。
- 全曲 8396 個有聲影格全部保留，沒有新增有聲影格；與 E 不同音高的影格 712 個。
- 50–63 秒 468 個有聲影格全部保留；與 E 不同音高 25 個。舊 D 在本段刪去 38 個、另改變 42 個。
- 以上是來源忠實度／複雜度，不是歌曲準確率。G 不保證優於 E 或 C；來源 F0 本身、半音化、同音重複起音與器樂段落問題仍存在。
- C／E／G 採相同連續相位正弦合成器、增益及有聲區段首尾淡入淡出，沒有逐音重新起音；此次不測吉他音色或和弦對齊。

## 重現與驗收

在 backend 環境執行：

```sh
python -m app.evaluation.conservative_notes /app/output/work/jobs/12fac6df94ee48a282fe2c542df3ae22/melody-contour.json /app/output/evaluation/NEW_DIRECTORY
```

輸出目錄必須尚不存在；預設 50–63 秒，可用 `--start`／`--end` 指定其他範圍。產生 JSON 音符、含來源 hash／參數／差異的報告，以及 C／E／F／G WAV。本機產物不納入 Git。

本次完整驗證產物在 `output/evaluation/bounded-notes-verified-2026-10-03/`。前端本機試聽 G 位於 `frontend/public/listening/bounded-notes-2026-10-03/`；瀏覽器已確認能解碼為 13 秒、有非零音訊。

60 項相關測試通過，涵蓋新解碼、短真音／低信心保留、休止、分界抖動、最大誤差、獨立輸出禁止覆寫，以及既有 pYIN／後處理／contour 診斷。實際全曲最大來源音高偏差約 0.5002 半音，低於實驗上限 0.6；發布試聽 WAV 與最終驗證輸出逐位元相同。

請比較 [G 新候選](http://localhost:5173/listening/bounded-notes-2026-10-03/G-bounded-connected.wav) 與 [E](http://localhost:5173/listening/connected-controls-2026-10-03/E-frame-semitones-connected.wav)，必要時再聽 [C](http://localhost:5173/listening/source-timed-v2-2026-10-03/C-source-contour.wav)。回報排序與明顯不對的局部秒數即可，不必重新分析、部署或逐音標注。

只有聽感改善成立才考慮整合譜面／編輯與更大範圍驗證；不能把更多音符、較少來源偏差或通過單元測試等同音樂品質過關。
