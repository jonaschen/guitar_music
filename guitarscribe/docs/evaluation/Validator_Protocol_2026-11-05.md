# Codex：參考評分器驗證規則（執行前固定）

目的：確認評分器能揭露半速、倍速、小節錯位、漏拍與錯和弦；不是建立無參考音樂裁判。產品辨識器、預設、人工工作譜及音檔不改。

固定資料：2026-10-24 GuitarSet 三個 pilot 錄音，各自原有標註與 SHA256；原 Librosa、標註拍點輔助的 chromagram、small0 diagnostic-v2，以及已存在的 fold3-excluded score。全部是已看過的資料，small0 完整模型含 GuitarSet 訓練資料，不能當泛化測試。標註拍點輔助不是自動結果。

每個標註生成以下控制案例（只在記憶體改資料，不改音訊）：

| 案例 | 預先固定的檢查 |
| --- | --- |
| reference identity | beat F1、CMLt、downbeat F1、chord root 均等於 1 |
| half tempo：每隔一拍取樣 | count ratio 約 0.5、CMLt < 0.1、AMLt > 0.9 |
| double tempo：相鄰拍點中間插一拍 | count ratio 約 2、CMLt < 0.1、AMLt > 0.9 |
| bar phase：第一拍改成後面一拍 | beat F1 = 1、downbeat F1 < 0.1 |
| dropout：移除片段中間 4 秒拍點 | CMLc < 0.7、beat F1 < 0.98 |
| wrong root：所有有和弦區段升一個半音 | timing 不變、root accuracy < 0.1 |
| fragmentation：每個同名和弦一分為二 | root accuracy = 1、fragmentation ratio = 2 |

這些閾值只用於檢查刻意注入的錯誤有沒有被看見，**不是 MVP 音樂品質門檻**。任何案例失敗都完整記錄，先查評分器／假設，不改到通過。缺參考必須 unknown；不以模型間一致度代替正確率。

評分範圍統一為 `[excerpt_start, excerpt_end)`；不重對齊、不調速、不跳過前五秒。來源音訊必須通過既有 SHA256；所有輸入檔雜湊固定在 plan。重評各既有 score，只報分層指標，不合成總分或把有規律視為正確。

下一步判準：控制案例全通過，只代表可用這套工具比較**有標註**資料。對目前使用者完整混音來源，仍缺逐拍／和弦真值；必須取得獨立參考，或維持未知。外部工具輸出也只是另一個估計器，須先用這些標註校驗。

## 第二批範圍（執行前補入，規則不變）

盤點發現現行 Chordino 已有六份快取，全部納入，避免只重評舊 chromagram。增加同三個 pilot 的 Chordino，以及原有 confirmation 的 SS3、Rock2、Funk2；後三份標註使用原匯入程式從既有 JAMS 重建，不跑模型。這些資料以前已使用過，不再稱保留測試。Chordino 的空拍點欄位不評分，只評和弦。新 plan 與結果另存 extended，首批結果保留；共六錄音、42 控制案例、16 份既有結果。
