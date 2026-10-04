# 開發方向檢視與下一道驗收（2026-10-04）

## 方向不變，優先序收斂

依品質救援計畫、參考專案研究與人工修譜計畫，目標仍是「準確且充分的分析 → 可讀／可編輯樂譜 → 原曲對照 → 保存與忠實匯出」。主旋律包含人聲與樂器；不是只分析人聲，也不是讓使用者修補大量錯音。停止用功能百分比代替音樂品質驗收。

本次明確證據：

- 使用者確認 G 轉譜與 C 來源軌跡在多段接近；因此暫固定 G，不再以包絡或後處理修補來源錯誤。
- 中段 100–113 秒：分離人聲清楚且音準正常，但 C／G 略走音。下一個比較層是音高追蹤。
- 後段 220–233 秒：使用者確認主要旋律在伴奏軌、聽似小提琴。不是已驗證的樂器分類，但足以否定該段應沿用人聲軌作為主旋律來源。

## 工作與驗收分離

| 層次 | 現況 | 接續工作／通過條件 |
| --- | --- | --- |
| 來源與音高 | 人聲局部可辨認；器樂主旋律未通過 | 中段精細追蹤、後段器樂候選先做短片段比較；不能只看 detector confidence |
| G 轉譜 | 多段接近 C，有独立譜與匯出 | 保留參數；來源改善後確認不丟真音、休止與時值；可讀性仍待處理 |
| 時間與和弦 | 和弦伴奏有聽感改善；Bar 30–31 局部對齊未解決 | 正確旋律與和弦合奏，檢查共享 TempoMap；禁止局部 offset hack |
| 編輯與產品 | 已有編輯／撤銷／保存；候選尚未進 UI | 下一個整合 checkpoint：可比較候選、明確接受、保留人工修訂；不是繼續增加診斷按鈕 |
| 品質資料 | 目前主要依單曲片段 | 累積使用者確認的來源／區段標記；之後跨歌曲驗證，不宣稱單曲結果等於整體 gate 通過 |

先完成本輪來源候選試聽。有明確改善者再接入獨立候選／編輯流程；若器樂候選仍不辨認，不繼續無止境微調自製規則，回到參考研究中的獨立 predominant-melody／分離模型比較，先檢查依賴及授權。未通過片段應保留待確認標記，不填入自信但錯誤的正式譜。

## 本輪實驗與限制

新增 `app.evaluation.source_candidates`，只讀現有 stem，分析 13 秒試聽區段及兩側約 2 秒上下文；沒有重新分離整首、下載模型或寫正式 job／revision。

### 中段人聲

相同 22.05kHz、hop 512、frame 2048、32 thresholds 與局部音訊，對照 pYIN resolution 0.5／0.1。兩個候選都用相同連續相位合成，沒有 G 解碼、調性矯正或拍點吸附。保留同 context 的粗解析度對照，避免把局部重跑的差異全部歸因於解析度。

參數含義依 [librosa pYIN 官方文件](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html)。解析度變細不保證追蹤正確，更不代表已解决八度／聲部問題；CPU 成本需另評估才可整曲部署。

### 後段器樂

使用伴奏的 STFT 插值頻譜峰值，保留每影格最多六個候選，加上諧波支持分數，再以音高跳動成本選擇連續路徑；第二條路徑折扣第一條附近的候選，作為競爭假設，不代表第二樂器。原始峰值候選及路徑均保存。

峰值擷取依 [librosa piptrack 官方文件](https://librosa.org/doc/0.11.0/generated/librosa.piptrack.html)；後續諧波評分與路徑成本是本專案未校準的實驗。196–1568Hz 搜尋範圍是假設，不是樂器識別；可能選到泛音、吉他或其他聲部。**不是小提琴分離器，也不是已驗證的主旋律演算法**。不能自動覆蓋人聲／器樂段落，不能用頻譜分數冒稱準確率。

## 下一次使用者測試

中段比較 `V-fine.wav` 與 `V-coarse-control.wav`：細版是否較少走音？後段比較 `I-primary.wav`／`I-alternative.wav`：哪個能跟上伴奏中的那條疑似小提琴旋律？兩者都不對也應直接記錄，不要求人工修音。

所有輸出與原曲保留相同分析秒數，沒有改起點。試聽未通過前，不部署新的正式分析路徑；不要求重新分析或重啟。

## 工程驗證與重現

19 項來源候選／來源診斷／G／独立候選測試通過。新增測試只證明候選路徑保留空影格、來自實際峰值，以及在合成低音＋單音例子可回復高音；不證明真實多音伴奏的主旋律準確。四個發布 WAV 已於瀏覽器確認皆為 13 秒、可解碼且有非零音訊。

本機產物在 `output/evaluation/vocal-fine-verified-2026-10-04/` 與 `output/evaluation/instrument-path-2026-10-04/`。報告記錄來源 hash、上下文、版本、參數；較粗的初次執行有 JIT／啟動成本，不能由兩次耗時比較斷言細解析度較快。

```sh
python -m app.evaluation.source_candidates /app/output/work/jobs/12fac6df94ee48a282fe2c542df3ae22 /app/output/evaluation/NEW_DIRECTORY vocal
python -m app.evaluation.source_candidates /app/output/work/jobs/12fac6df94ee48a282fe2c542df3ae22 /app/output/evaluation/ANOTHER_NEW_DIRECTORY instrument
```

輸出目錄須尚不存在。試聽基底 `http://localhost:5173/listening/source-candidates-2026-10-04/`；檔名為 `V-coarse-control.wav`、`V-fine.wav`、`I-primary.wav`、`I-alternative.wav`。來源音訊仍可使用上一輪 stem-source-review 的人聲／伴奏檔對照。
