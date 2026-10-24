# 和弦持續時間加權：完成確認，未升級預設

本輪先定位錯誤，再凍結一個候選、打開三段事先保留的錄音驗證。候選在開發資料改善，但在確認資料退步，**不升為預設**。沒有調整各曲參數、沒有更動G、沒有新增使用者試聽。

## 方法與診斷界線

原decoder對各region的emission等權計分，短暫尾音與長持續區段各投一票。候選僅設 `ChordDecoderConfig(duration_weighted_emissions=True)`，使整個emission（包含調性prior及N）乘區段秒長，其他閾值與轉換成本不變。這會改變相對平滑強度，不只是「計算修正」；短和弦可能受抑制。預設False，沒有產品UI／環境開關自動啟用。

保留未加權margin計算confidence，並測試短強證據和弦、相同長區段拆分、根音同音異名、排名相同時不冒稱唯一第一。confidence仍未校準。

原三段若使用標註和弦區間聚合聲學證據，根音argmax均100%；這只表明理想區間下可選對根音，並非自動能力，更不是完整和弦品質。關閉所有prior／轉換懲罰會使SS2退步，因此不採用。

## 固定候選結果

以下均為根音時長一致率；參考拍點診斷不算自動分析。所有百分比均包含失敗區間，沒有依和弦種類剔除不利部分。

| 組別／錄音 | 拍點來源 | 原版 | 時長加權 |
|---|---|---:|---:|
| 開發 SS2 | 標註 | 92.19% | 98.44% |
| 開發 Rock1 | 標註 | 97.92% | 97.92% |
| 開發 Funk3 | 標註 | 79.69% | 87.50% |
| 確認 SS3 | 標註 | 98.44% | 100.00% |
| 確認 Rock2 | 標註 | 78.12% | 78.12% |
| 確認 Funk2 | 標註 | 17.19% | 12.50% |
| 確認 SS3 | 自動Librosa | 93.82% | 95.46% |
| 確認 Rock2 | 自動Librosa | 83.40% | 83.40% |
| 確認 Funk2 | 自動Librosa | 18.45% | 15.10% |

Funk2的參考拍點邊界F1±100ms也從30.30%降至22.22%；自動拍點的邊界F1雖從17.65%升至20.69%，根音仍退步，不能只挑改善指標。完整各項數值與來源report雜湊見 [機器可讀結果](chord-duration-results-2026-10-24.json)。

確認Funk2大量標註是延伸、省略音／省略根音和弦，現有24個三和弦模板即使使用標註區間，根音也僅12.5%。這與前三段的oracle 100%形成直接反例。不能把註記根音當作每次必然實際發聲的低音，也不能再把所有問題歸因於換和弦時間。下一步需比較其他和弦分析方法及能力範圍，不能繼續只改節拍。

## 成本、錯誤與重現

三段確認錄音選自先前已保留的SS3／Rock2／Funk2進行；沒有使用學習式beat模型，避免其GuitarSet訓練重疊。新下載傳輸共7,013,200 bytes，只有選定ZIP成員，原音訊不進Git。全部零逐曲人工修改。

Rock2實錄只有27.04秒，第一次兩個runner都因30秒quality-gate規則中止；保留失敗產物。修正匯入器將短錄音標為smoke後，以新目錄重跑，未補長音訊、未降低quality-gate門檻。因此三段確認中僅兩段符合時長門檻；本輪仍不是整體品質gate通過。

```sh
python guitarscribe/backend/scripts/diagnose_chord_evidence.py \
  --dataset guitarscribe/output/datasets/guitarset-1.1.0/confirmation \
  --protocol guitarscribe/docs/evaluation/chord-duration-confirmation-2026-10-24.json \
  --output /tmp/chord-confirmation-new --timing librosa
```

省略`--timing`預設用標註拍點；oracle欄位永遠使用標註和弦區間，不得當全自動輸出。輸出目錄必須不存在，失敗非零退出。完整聲學根音排名與decoder候選保存在本機report，方便追查錯誤。34項相關分析／pipeline測試及3項資料匯入測試通過。
