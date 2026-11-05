# Codex 報告：自動音樂驗證第一段交付

2026-11-05。本段完成可重複執行的參考評分校驗及外部工具校驗準備。**尚未改善新歌的辨識準確度，也尚未建立無參考音樂裁判。** 正式網站辨識／播放預設、工作譜與已驗收音檔未改。沒有新試聽要求。

## 已完成及證據

1. 重用現有 mir_eval，將正常拍速連續度 CML 與容許半速／倍速的 AML 分開顯示，避免把「跟得上」誤稱「拍速正確」。第一拍仍獨立評估，不以拍點分數代替。定義見 [mir_eval 拍點指標](https://mir-eval.readthedocs.io/latest/api/beat.html)。
2. 修正評分範圍：參考與預測都只取 `[excerpt_start, excerpt_end)`。以前可能把片段外的預測拍點算入，導致無關的扣分。無參考回報未知；不重新對齊、不跳過開頭五秒；重複、倒序或非有限時間直接拒絕。報告格式 1.3 → 1.4。
3. 先固定[規則](evaluation/Validator_Protocol_2026-11-05.md)，再執行六個既有 GuitarSet 錄音、42 個控制案例，全部符合預先指定的檢查。控制包含半速、倍速、第一拍錯位、漏拍、錯根音和過度切分。這是檢查器驗證，不是 42 次辨識成功。
4. 重評 16 份既有分析，無模型推論。包含 Librosa／chromagram、參考拍點輔助、small0，以及六份 Chordino；來源、標註、快取譜的 SHA256 在執行前後核對。完整音檔與人工版本不覆寫。
5. 完成 Klangio 結果的離線讀取器、準備素材／評分命令。嚴格檢查時間範圍、格式與涵蓋；缺漏不補成靜音，N 與 X 分開，外部結果不會變成 ground truth 或產品工作譜。47 個相關測試通過，包含封包到評分的端到端合成契約測試；不是 Klangio 實測。

本段投入為評分修正、快取重評、工具契約查證及本機素材準備；模型推論 0 次、外部音訊上傳 0 次、付費 0、使用者試聽 0。不把未量測的工作時數寫成估計實績。

## 結果對開發的意義

例如 Funk3 的 fold3 拍點／第一拍 F1 都是 1，但 chromagram 根音正確率約 77.8%。拍子修好並不代表和弦也正確。現行 Chordino 快取結果如下：

| 錄音 | 根音正確率 | 大／小和弦正確率 | 事件數／參考事件數 |
| --- | ---: | ---: | ---: |
| SS2 | 92.2% | 93.4% | 1.50 |
| Rock1 | 97.4% | 97.4% | 1.17 |
| Funk3 | 82.4% | 86.5% | 1.44 |
| SS3 | 94.2% | 94.2% | 1.31 |
| Rock2 | 84.2% | 85.2% | 1.07 |
| Funk2 | 22.1% | 19.0% | 2.07 |

這些是舊快取的重新評分，不宣稱新發現／新改進。它們證明自動評分可以指出哪份**有標註**資料失敗；低分案例須保留，不用平均數掩蓋。事件數也只作切分診斷，不能單憑比較密就刪和弦。

限制：六份皆是吉他錄音而非使用者的完整流行歌混音；已看過，不能當未知測試。完整 small0 曾使用 GuitarSet 訓練；fold3 排除的是指定錄音，不能延伸為無資料重疊。標註的和弦邊界亦未逐點獨立聽審。目前《後來》的半速／第一拍錯誤是人耳判決，沒有逐拍真值，不能把人耳描述自行換成加倍／移一拍的「正解」。

## 外部校驗已準備到哪裡

已核對 Klangio 官方 [拍點 JSON](https://api-docs.klang.io/docs/jobs/beat-tracking-request)、[和弦 JSON](https://api-docs.klang.io/docs/jobs/chord-recognition-requests) 與 [OpenAPI](https://api.klang.io/open_api)。拍點含秒數／拍內位置，和弦含起訖秒數／標籤，可作離線比較。

[封包清單](evaluation/external-validation-packet-2026-11-05.json)已固定：SS2、Rock1、Funk3，各 0–15 秒，總共 45 秒原素材，六個建立工作請求（拍點與 major-minor 和弦各一次）。每個 WAV 約 1.3 MB。只擬上傳 WAV，不上傳標註、專案、使用者歌曲或工作譜。素材來自 [GuitarSet 1.1.0](https://zenodo.org/records/3371780)，CC BY 4.0，保留署名與原檔雜湊；裁為 PCM16，無其他混音。

先用公開標註校驗外部工具，不直接把外部工具當答案。此階段每個來源各自報拍點、第一拍、和弦分數；不做三首平均總分、不自動升產品預設。若連這三個簡單片段也無法穩定通過，該品質層不升為目前混音曲目的參考。若表現可用，再另行提出固定失敗／已接受混音片段的交叉檢查；本封包不包含那些歌曲。

使用者已同意免費校驗，並確認尚無帳號。上傳授權已取得，不重問；尚缺帳號／API key、帳戶可用額度確認。[官方工作流程](https://api-docs.klang.io/docs/getting-started/basic-job-workflow)說明建立工作可能消耗額度；本次價格頁存取失敗，不能沿用 10 月的價格或保證免費。建議此次支出上限 **US$0**，只有帳戶明確允許這六次免費工作才執行；不購買或升級。不把 API key 寫進文件、Git 或聊天。

## 可重現命令

以下從儲存庫根目錄執行；`PY` 指向已安裝 backend 依賴的 Python。輸出路徑必須尚未存在。快取／原音訊不在 Git，需保留本機既有 output。

```bash
PY=/home/jonas/.cache/guitarscribe-runtime/bin/python
$PY guitarscribe/backend/scripts/check_reference_validator.py guitarscribe guitarscribe/docs/evaluation/validator-plan-extended-2026-11-05.json guitarscribe/output/evaluation/validator-replay/report.json
$PY guitarscribe/backend/scripts/prepare_external_validation.py guitarscribe guitarscribe/docs/evaluation/validator-plan-2026-11-05.json guitarscribe/output/evaluation/external-validation-replay
```

將來取得實際外部結果後，依清單將結果存成 `<recording_id>.beats.json` 與 `<recording_id>.chords.json`，即可評分。這個命令不連網，也不能證明手動放入的 JSON 確實來自服務；實際 API job ID 與上傳雜湊還須另存。

```bash
$PY guitarscribe/backend/scripts/evaluate_external_validation.py guitarscribe/output/evaluation/external-validation-2026-11-05 guitarscribe/output/evaluation/external-validation-results guitarscribe/output/evaluation/external-validation-report.json
```

本機產物：`output/evaluation/reference-validator-2026-11-05/`；精簡數值已提交於 [results](evaluation/validator-results-2026-11-05.json)。補入的三份標註沿用 `benchmark_guitarset_pilot.reference`，從原 confirmation JAMS 匯入，無人工修改標籤。

唯一建議下一步：在零付費、有授權與帳戶額度的前提下執行此小型外部校驗，再決定是否值得用它輔助目前的混音曲目診斷。現在不再換模型或對單曲調參。

帳號準備：由使用者在 https://auth.klang.io/register 註冊，於 https://api-dashboard.klang.io 的 Overview 取得 API key。已建立空白私密檔 `/home/jonas/.config/guitarscribe/klangio-api-key`（0600），使用者填入單行 key；此檔不在儲存庫，不讀出到紀錄。尚未登入或註冊。
