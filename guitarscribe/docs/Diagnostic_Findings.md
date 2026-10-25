# Codex：獨立正解診斷紀錄

日期：2026-10-25。首輪基準 `e55bfbb`，產品基準 `cd6a599`。

本輪目的為定位錯誤，不是宣告音樂品質通過。使用者工作譜、保存修訂及已認可 B 均不覆寫；不新增模型或外部付費服務。

## 已證實：編譯器對極短音有失真

手寫 `0.500–0.505s` 音符，原編譯器輸出到 `0.510s`，侵入下一個同音。原因是旋律事件有 10ms 最短長度。修復改為保留正長度音符，無效長度仍沿用既有 fallback，並更新 compiler revision。

六個手寫控制案例，修復前 5 通過／1 失敗，修復後 6 通過。核對音高、數量與秒數（內部 1ms，MIDI 一 tick），不從待測 compiler 產生 expected values。涵蓋休止、同音重複、跨小節延音、弱起、不同拍距、整／半／跨小節和弦，以及來源 offset 和已移調／capo 譜。MIDI 由 mido 讀回並解碼 tempo。

**這不是使用者零落感的根因證明**：現有 pYIN frame 約 23.22ms，這次修正的 5ms 邊界案例不足以解釋其普遍問題。

證據目錄（相對 `guitarscribe/`）：

- `output/evaluation/known-events-phase-a-2026-10-25-final/`：修復前。
- `output/evaluation/known-events-phase-a-2026-10-25-fixed/`：修復後。
- 重現：backend 執行 `python scripts/diagnose_known_events.py NEW_OUTPUT_DIRECTORY`。

限制：不同拍距案例驗證實際秒數，不是 MIDI tempo map 功能；轉調案例從已移調譜開始，不是轉調 API 全流程；合成事件不能驗證辨識品質。

## 既有真實片段的定位界線

失敗 job `db79e1145ea046088b8aa5ef421d0e3f`：45 秒，原分析 76 音符；由保存 contour 推導 G 為 159 音符，其中 72 個短於 100ms，中位長度 116ms。編譯 manifest 保留 G 音符時間，未額外縮短。21 段內部空隙共 6.153 秒已存在於來源 contour；它們是否為正確休止，尚無獨立真值。

這是保存資料的審計，不是證明瀏覽器當時選了哪個版本，也不能把短音數直接當成錯音數。使用者指出的 Bar 8 起八小節固定為原譜 Bar 8–15，不隨候選重編。

## 已驗證：代表案例的瀏覽器排程

真實 backend compiler 回傳 manifest，瀏覽器使用手寫工作譜播放；job GET mock，未保存修訂。實際 WebAudio 探針核對四個音符的音高、起音、gain 歸零與 oscillator 停止相對手寫時間誤差 ≤1ms；休止、同音重複、跨小節長音保留。暫停／續播及兩次循環後停止亦通過。循環週期另以 50ms 容差檢查，停止後 350ms 未新增起音。

初次診斷失敗包含探針誤認 connected melody envelope、把純 MusicXML 轉換當成寫入、以及 UI 測試操作錯過短暫活動視窗。修正測試後單檔 **1 passed（12.8s）**；未為此修改播放器。最終 fixture 的跨小節音為 1.1–3.0s，第一小節循環截於 2.0s，保留足夠時間檢查正在發聲的 oscillator 被停止。

這是 WebAudio 排程驗證，不是喇叭／耳機輸出錄音，也未覆蓋所有 UI 播放入口或音色。測試使用當時運行中的 backend；該代表案例均長於 10ms，因此不依賴短音修復。

## 已證實：理想音高仍無法保留同音重奏

獨立手寫 9 個音符，用 NumPy 合成正弦／諧波音訊，並直接提供一份完全正確的 F0 contour。沒有用 GuitarScribe compiler 或 renderer 生成正解。

理想 contour 解碼為 8 音：`0.5–1.0s C4` 與 `1.0–1.5s C4` 合為 `0.5–1.5s C4`，其他音高和邊界正確。即使 F0 完美，現有只讀音高／有聲區間的 G 解碼也無法恢復該次重新起音。**這是表示資訊缺口，不是調整音高門檻就能保證解決。**

## 已證實：乾淨換音邊界產生錯誤短音

匹配規則預先固定：音高相同、起音誤差 ≤100ms、一對一配對；音尾誤差獨立報告。matched 不是完整音符正確率。

| 控制輸入 | 原始解碼／G 音符數（正解9） | G 漏音／額外音 | 觀察 |
|---|---:|---:|---|
| 理想 F0 | —／8 | 1／0 | 相鄰同音合併，首音延長500ms |
| 乾淨正弦 | 8／10 | 1／2 | 同音合併，兩個換音邊界多出約46ms短音 |
| 乾淨諧波 | 8／10 | 1／2 | 相同的漏音與額外音模式 |
| 前置靜音→裁切→44.1kHz | 8／10 | 1／2 | 未見整體秒級偏移，仍有相同切分問題 |
| 旋律＋和弦＋脈衝，未分離 | 1／1 | 9／1 | pYIN 直接吃混音失敗；這不是正式 Demucs 流程的品質評估 |

正弦／諧波的非邊界有聲內部 191 frames 均在正確音高 ±50 cents 內；但邊界處 contour 已含錯誤中間音高。正弦 G 在 `1.9737–2.0201s` 多出 F4、`3.5062–3.5527s` 多出 Eb4，解碼把它們輸出成音符。最早錯誤分別在 **起音資訊表示** 與 **F0 邊界估計**，不是這兩案的 MIDI 或播放排程。

合法 75ms 音被解成約162.5ms，不能因保留了該音高就算音長正確。frame 評分排除每個邊界 ±50ms，因此此短音完全不進 frame 內部評分；須看 note-level 時間。配對音中，因同音合併，首音尾端多約556ms；其他音尾約 −26 至 +60ms，起音絕對誤差 p95 約48ms。

裁切控制的 1.25s 在 22050Hz 落於半個 sample：實際裁切少一個 sample（約0.045ms），裁切波形與原波形移一個 sample 後逐值相同。這不是使用者聽到的明顯搶拍證據。

## 和弦與拍點：受控結果，尚不能定原曲根因

- 四個獨立合成長和弦：Chordino 輸出4事件，時間加權完全相同標籤比例90.94%；三個內部切換的最近邊界距離約43、180、37ms。這不是跨曲準確率。
- 合成混音：仍4事件，但標籤比例降至68.11%；邊界最近距離約50、6、37ms。邊界距離可重用預測，不能稱為 recall／F1。
- 純脈衝及合成混音的 Beat This 輸出都未通過既有拍點／重拍一致性保護，保留 raw beats/downbeats，未強制補成正常結果。這些簡單合成音非真實音樂，不能由此宣告模型對流行歌曲無效。
- 本輪沒有跑 Demucs，沒有以新設定重跑使用者歌曲，也沒有驗證原曲和弦真值。伴奏錯位的最早原因仍未定位。

## 可重現證據與投入

版本化摘要：[修復前](diagnostics/2026-10-25/known-events-before.json)、[修復後](diagnostics/2026-10-25/known-events-after.json)、[合成音訊結果](diagnostics/2026-10-25/synthetic-results.json)。完整逐層音訊／contour／解碼／MIDI 留在 `output/evaluation/` 的對應日期目錄，可由腳本重建。合成結果記錄來源 SHA256、診斷程式及實作 SHA256、套件版本與參數。

在 backend 重現合成診斷（本機既有 runtime）：

```bash
OMP_NUM_THREADS=2 \
PYTHONPATH="$HOME/.cache/guitarscribe-chordino-diagnostic/python" \
VAMP_PATH="$HOME/.cache/guitarscribe-chordino-diagnostic/source" \
"$HOME/.cache/guitarscribe-runtime/bin/python" \
  scripts/diagnose_synthetic_transcription.py NEW_OUTPUT_DIRECTORY
```

相關 Python 驗證：`test_midi.py`、`test_known_events_diagnostic.py`、`test_synthetic_diagnostic.py` 合計 **28 passed**。這個數字只證明指定工程行為，不代表音樂品質分數。

確認無進行中分析工作後，已重啟本機 backend 載入短音修復；live manifest API 實測保留 `0.500–0.505s`。backend `/health` 與前端 `127.0.0.1:5173` 均回應200。

合成音訊當輪執行（含生成／裁切及模型運算）25.45秒；瀏覽器最終一次12.8秒，先前診斷探針修正與失敗重跑另有耗時。整體工作約數十分鐘、低於首輪8小時檢查點；平行 session 有重疊，無精確去重工程工時及token費用資料，不捏造金額。本輪在已有足夠下一步定位證據時交付，不為用滿上限增加實驗。

**尚未證明**：相同機制在使用者歌曲中占多少錯誤、音符切分改善能否達到可用品質、伴奏錯位原因及跨曲泛化。下一步見 [Next_Decision.md](Next_Decision.md)。
