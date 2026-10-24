# 可選的學習式拍點／重拍引擎

已完成 Beat This small0 的可選接線，尚未取代預設Librosa。這是實際可被AnalysisPipeline使用的BeatAnalyzer，不是把人工參考拍點當成新推論結果。固定CPU、小模型、無DBN、未訓練或逐曲改參數。

## 啟用與重現

先依平台安裝CPU版torch/torchaudio，再安裝專案的timing extra。本次驗證環境為Python3.12、torch2.5.1+cpu、torchaudio2.5.1+cpu、beat-this1.1.0。

```sh
python -m pip install torch==2.5.1 torchaudio==2.5.1 --index-url https://download.pytorch.org/whl/cpu
python -m pip install -e './guitarscribe/backend[timing,quality]'
```

明確設定 `GUITARSCRIBE_BEAT_ENGINE=beat_this_small`，CPU基準使用2個torch threads；啟動服務可設定 `OMP_NUM_THREADS=2`。未設定時仍使用Librosa，不會自動下載模型。新引擎首次使用才下載官方small0約8.4MB checkpoint；模型與套件版本／權重SHA保存於score provenance。伺服器部署前需確認模型快取及可選依賴。

模型輸出的downbeat必須對應已偵測到的beat；相鄰重拍的拍數必須一致為3或4。保留首個重拍前的pickup（measure 0），拒絕漏拍／變拍／非有限時間與會捏造重拍的投影。confidence標0表示未校準，不是宣稱辨識可靠度為0。只支持一致3/4、4/4，分母採quarter-note慣例，不處理所有複合拍型。

新引擎存 `timing-analysis.json` 及 `tempo_map_version=learned-downbeats-v1`，原引擎流程與G保存譜不變。失敗時回報錯誤，不悄悄改回錯誤小節相位。30項相關測試通過：模型無須下載的注入測試、pickup／meter檢查、完整pipeline相容及舊引擎回歸。

## 已完成small0診斷：有訓練重疊，不能當泛化通過

[官方模型說明](https://github.com/CPJKU/beat_this)與[訓練資料清單](https://github.com/CPJKU/beat_this_annotations)顯示GuitarSet在訓練資料中。雖然本專案未用這三筆調參，仍不能說small0未見它們。因此保留的三筆確認錄音未開啟，也不拿它們替small0證明未見表現。

| 錄音 | 舊重拍F1 | small0重拍F1 | 舊邊界F1±100ms | small0邊界F1±100ms | small0根音一致率 |
|---|---:|---:|---:|---:|---:|
| SS2 | 0.0% | 72.7% | 21.4% | 89.7% | 90.9% |
| Rock1 | 16.7% | 96.0% | 60.0% | 80.0% | 97.9% |
| Funk3 | 0.0% | 100.0% | 66.7% | 64.5% | 77.9% |

第三段和弦根音從79.4%降至77.9%，邊界也略降。更準的拍點不保證和弦分析全部改善，不得只報前兩段。

CPU兩threads每段模型推論約6.7–7.5秒，32–44秒實錄；不含依賴下載、模型初次載入與完整歌曲分音／旋律分析。首次量測腳本有list/ndarray介面錯誤，保留失敗報告後修正重跑，約22秒失敗推論亦是開發成本，不掩蓋為音樂失敗。

產物：`output/evaluation/beat-this-small0-2026-10-24/diagnostic-v2/report.json`；原始模型beats/downbeats、投影與下游分數均保存。官方程式及權重採MIT；來源與作者說明保留，未重分發權重。

## 排除訓練錄音的補充檢查

官方v1.0 `guitarset/8-folds.split` 將 `00_SS2-88-F_comp_mix` 與 `02_Funk3-112-C#_comp_mix` 分至fold3。官方訓練程式以該fold作validation，使用fold3 checkpoint可檢查未納入該模型訓練的兩段錄音；這不是排除整個資料集，也不是排除所有相同進行的其他演奏。

此補充使用固定fold3，禁止為結果選模型；runner先檢查每筆split再執行。模型大小及架構不同於small0，結果不能偷換為small0的未見成績。結果另記錄，尚未以此更改產品預設。

### 實跑結果與未通過項目

| 錄音 | fold3拍點F1 | fold3重拍F1 | 小節投影 | 下游和弦 |
|---|---:|---:|---|---|
| SS2 | 90.6% | 78.8% | 拒絕 | 不產生樂譜／不計和弦分數 |
| Funk3 | 100.0% | 100.0% | 支持 | 根音77.8%，邊界±100ms F1為64.5% |

SS2模型先輸出15個四拍間距，最後兩個重拍間卻只有三拍；目前模型不能可靠區分尾段誤判與變拍，不能強行編成4/4。保留拒絕結果，未刪尾、未按標註修補。Funk3雖然拍點與重拍完全匹配，和弦根音仍低於舊基準79.4%。兩筆中僅一筆可投影，並非可用率已達標；兩筆樣本也不足估計一般拒絕率。

兩段推論各約12秒，模型載入／首次下載合計約19.1秒，checkpoint約78MB；零人工時間修正。產物在 `output/evaluation/beat-this-small0-2026-10-24/fold3-excluded/report.json`。權重SHA256為 `849de186a21ed1cd41d0ac78dc412c61f5283dcafffa9dd32f390674c50792cf`，官方split SHA256為 `f89662e69dd27f586feec238f2e9f8f0da58841f8143460667b929e09a0f5bfc`。

補上尾段三拍衝突的回歸案例後，相關測試共31項。下一個關卡仍是完整混音的固定方法驗證，以及拍點正確時仍失敗的和弦辨識；不新增本曲的手動調整，不要求使用者替這些工程問題反覆試聽。
