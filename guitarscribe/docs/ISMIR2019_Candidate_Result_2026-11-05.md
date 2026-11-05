# ISMIR2019 本機替代模型：固定比較未通過，停止候選

2026-11-05，A13。完成可行性、原版預設五模型 ensemble 的九來源比較及同域評分，**候選未通過**。Funk2 root 從 22.06% 降到 0%，原始 lab 整段為 N；HU33 root 逐來源平均變化 −5.53 個百分點，只有 21 改善。停止這個固定候選，不挑 fold、不改字典、不再換另一模型搜尋。沒有變更產品／預設，也沒有新的人耳驗收。

## 可信來源、授權與可行性

唯一候選是作者 [music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition/tree/481f4ce703f8822b99f4037e9104ba1760e21ea3)，固定 commit `481f4ce703f8822b99f4037e9104ba1760e21ea3`。檢索專案既有文件、腳本與技能未找到曾試用並淘汰的紀錄；這不是保證所有外部歷史都不存在。

[作者 README](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition/blob/481f4ce703f8822b99f4037e9104ba1760e21ea3/README.MD) 指定庫內預訓練模型與預設 submission 字典；本次沿用原五個 checkpoint 平均與原 HMM，不使用另行提供的 reweight 權重。程式與這五個權重同在庫內，[MIT LICENSE](https://github.com/music-x-lab/ISMIR2019-Large-Vocabulary-Chord-Recognition/blob/481f4ce703f8822b99f4037e9104ba1760e21ea3/LICENSE) 未見權重專屬例外條款。此查核不等於完整訓練資料權利或資料重疊審核，也未授權產品採用。

原始碼與權重 ZIP 下載 27,239,052 bytes，SHA256 見數值 provenance；額外依賴為數十 MB 級，依安裝日誌未接近 1GB 上限，未宣稱有逐 HTTP 精確下載計量。隔離位置 `~/.cache/guitarscribe-ismir2019/`，獨立 venv 透過唯讀 site 路徑重用現有 CPU torch。未修改正式 runtime；新增 h5py／pydub／jams 等只裝入新環境。依賴解析先拉入較新 NumPy，已在該隔離環境固定回 NumPy 1.26.4、pandas 2.2.3、matplotlib 3.9.4、contourpy 1.3.1；完整實際套件記錄在本機 `packages.txt`。未宣稱作者所有訓練／視覺化依賴或全環境 pip check 都通過。

原始程式不改。唯一相容處理是 wrapper 的 `np.int=int`，恢復舊 NumPy 名稱；沒有更改前處理設定、網路、權重或解碼。實際套件版本使用現有可用版本及作者最低版本條件，並非重建2019年的完整環境；librosa 等實作版本差異仍是重現限制，不能把本次失敗直接外推成論文方法無效。五份權重均成功載入，各 500,772 個參數；合成零 CQT 執行五次子模型 forward，僅驗證 CPU 與預設 301 個解碼候選可用，未看音樂分數。

## 事前計畫與評分語義

[固定計畫](evaluation/ismir2019-plan-2026-11-05.json) 在任何九來源音樂預測前寫定，記錄完整作者 source/checkpoint hash。原九份音訊、片段、參考與 Chordino baseline 不變，全為開發／回歸集。原資料與模型訓練的可能重疊未完整審核，不稱未見驗證。

各音訊直接交作者 loader：22050Hz mono，原 CQTV2 hybrid CQT 288 bins、每八度36 bins、F#0、hop512、原 tuning=None；原時間是 frame index × 512/22050，沒有平移或依參考重對齊。原始 lab 完整保存；評分只與既有共同區間相交。GuitarSet 對兩引擎使用相同歷史 merged／去 slash／裁界表示，HU33 保留完整標籤；這是保持舊評分表示，不是把候選強迫轉成 triads。所有輸出標籤可可靠解析，未知標籤秒數 0，參考 root／majmin 可評秒數均與 A09 相同。

成功須同時滿足 Funk2 root 增 ≥10 個百分點、HU33 平均增 ≥5 個百分點且至少兩份各增 ≥5；九份各自 root／majmin 退步 ≤2 個百分點、漏＋多和弦增加 ≤0.25s、邊界 precision／recall 退步 ≤5 個百分點。任何一項失敗即停止，不事後修改門檻。

## 每來源結果

下表 baseline → candidate；root 可評涵蓋均100%，majmin 可評另列。完整錯誤秒數、邊界 precision／recall、未配對數、原始 lab 與 hash 見 [數值證據](evaluation/ismir2019-results-2026-11-05.json)。

| 錄音 | Root | Majmin | Majmin 可評範圍 | 漏＋多和弦增加 s | 失敗閘門 |
| --- | --- | --- | --- | ---: | --- |
| 00_SS2-88-F_comp | 92.15% → 95.67% | 93.41% → 98.84% | 29.993s (68.74%) | +0.650 | missed_false |
| 01_Rock1-90-C#_comp | 97.44% → 98.39% | 97.44% → 98.39% | 32.000s (100.00%) | -0.209 | 無 |
| 02_Funk3-112-C#_comp | 82.40% → 90.99% | 86.53% → 44.97% | 4.286s (12.50%) | +1.858 | majmin, missed_false |
| 03_SS3-84-Bb_comp | 94.24% → 98.45% | 94.20% → 98.38% | 39.993s (87.50%) | -0.209 | 無 |
| 04_Rock2-142-D_comp | 84.20% → 94.03% | 85.18% → 95.75% | 21.971s (81.25%) | -0.209 | 無 |
| 05_Funk2-119-G_comp | 22.06% → 0.00% | 19.00% → 0.00% | 16.129s (49.99%) | +32.031 | root, majmin, missed_false, boundary_precision, boundary_recall |
| SWD_HU33_04 | 64.24% → 59.27% | 68.98% → 68.56% | 36.100s (81.05%) | +0.000 | root, boundary_recall |
| SWD_HU33_18 | 58.30% → 38.32% | 56.70% → 44.64% | 34.120s (80.32%) | +12.399 | root, majmin, missed_false, boundary_recall |
| SWD_HU33_21 | 73.17% → 81.54% | 73.00% → 79.30% | 44.660s (100.00%) | +0.000 | boundary_recall |

Funk3 的 majmin 只涵蓋12.5%時間，大幅退步不能外推為全段幅度，但仍違反既定控制。Funk2 原始輸出為 `0.0–32.27573696145125 N`，評分僅裁至固定32.263197秒，沒有把 N 偷補成和弦。它是模型完整輸出的失敗，不是空檔或下載失敗；目前沒有足夠證據判定 all-N 的聲學／解碼原因，本段不重跑／調參追逐此例。

## 驗證與停止決策

五項解析測試通過，包含原完整和聲／N 保留、固定裁界，以及重疊、無限時間、不可映射或空結果拒絕。九份原始輸出映射成功、基線分數與 A09 相同、參考可評分母不變；完成後原作者 source 與五份 checkpoint hash 仍完全一致。

實際音樂分析九次 ensemble＝45 次子模型 forward，另有可行性合成輸入五次 forward，沒有訓練。CPU 限兩執行緒、循序，零外部音訊請求／付費／live 操作。可行性與完整實測都在原45分鐘／三小時上限內完成。

完整本機證據為 `guitarscribe/output/evaluation/ismir2019-comparison-2026-11-05/`，含原 lab、每來源 log、原計畫、套件、inference manifest 及完整結果。重新評分、不推論：

```bash
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/evaluate_ismir2019_candidate.py guitarscribe
```

推論 wrapper 保留在 `backend/scripts/run_ismir2019_candidate.py`，拒絕既有每來源 log／lab，不允許到期後續跑。Git 不提交權重、環境、音訊；精簡結果保留九份原始 lab，其他機器須有同 hash 輸入才能重評。

**唯一下一步是顧問驗收本次停止決策並重新決定產品優先序。** 本次實驗沒有提供可安全採用的辨識修改；不追加模型搜尋，不把部分來源改善包裝成任選歌曲已可用，也不交使用者聽這份失敗候選。
