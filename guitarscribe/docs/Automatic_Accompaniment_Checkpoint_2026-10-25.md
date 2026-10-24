# 固定引擎的完整片段伴奏比較

完成六段實錄比較、另一個和弦引擎的隔離建置、延伸和弦播放修正，以及原曲29秒的全自動伴奏候選。現在需要一次聽感判斷；不再請使用者逐字標時間。尚未宣稱跨曲品質通過或產品可自動處理所有歌曲。

## 唯一人工驗收

[開啟整段比較](http://127.0.0.1:5173/listening/automatic-accompaniment-2026-10-25/index.html)，先聽A再聽B。兩段各約29秒，涵蓋原先完整句子。只回報：B整段更好／差不多／更差／無法判斷，以及最後「哀愁」仍搶拍／大致貼合／偏慢／無法判斷。明顯不和諧時可附一句位置，其餘不需測試。

A是前次 `post-consensus-audit-2026-10-23/candidate-v2`，保留當時逐段探索的結果；B僅以同一原曲音訊執行small0拍點／重拍與Chordino預設辨識，零歌詞標記、零逐曲時間／和弦修正。沿用同一刷奏型、合成器、原曲與音量。這是整體方法比較，同時改變拍點、和弦及其指型，不能將聽感差異歸因於單一因素。

來源packet內容29.291979秒，另有既存渲染尾端；分析結果只按預先記錄的內容長度裁尾，沒有刪除音樂錯誤。B得到64拍／16重拍、16個和弦區段。G與保存revision完全未寫入；候選獨立且只合成吉他，原唱來自原曲。

## 六段實錄：根音改善，邊界仍有明確失敗

採[官方Chordino原始碼](https://github.com/c4dm/nnls-chroma)，固定commit `4c5f214a75cb354f8d8c933e161377c5b4d83713`，內建字典／預設參數，無外部字典。這是可比較的既有引擎，並非學習模型泛化驗證。後三段已在前輪開啟，這次不能再稱未見確認集。

| 錄音 | 原版根音 | Chordino根音 | 原版邊界F1±100ms | Chordino邊界F1±100ms |
|---|---:|---:|---:|---:|
| SS2 | 87.12% | 92.15% | 21.43% | 50.00% |
| Rock1 | 96.90% | 97.44% | 60.00% | 40.00% |
| Funk3 | 79.45% | 82.40% | 66.67% | 11.11% |
| SS3 | 93.82% | 94.24% | 60.61% | 52.94% |
| Rock2 | 83.40% | 84.20% | 46.15% | 23.08% |
| Funk2 | 18.45% | 22.06% | 17.65% | 10.00% |

原版為Librosa＋Chromagram，非參考拍點診斷。Chordino獨立輸出時間，未輸入標註拍點；空beat的評分警告不計入和弦結果。Rock2僅27秒，仍列smoke。Funk2有大量延伸／省略音和弦，兩種方法都不合格。其他片段的分數不能掩蓋此失敗。此組結果支持製作受控試聽候選，不支持直接替換預設引擎。

## 播放與評分修正

- 評分器補上 `6→maj6`、`m6→min6`、`m7b5→hdim7`，保留未知品質為X；六筆原始Chordino結果未知標籤皆0。轉位不納本輪根音／品質判分。
- 原先G7、D7、G6只有根音fallback，無法忠實播放；新增7／maj7／m7／6／m6／m7b5通用E／A形指型。所有12根音的完整音集合與品格限制有測試，保留舊三和弦排序與已存指型。沒有把不支援的和弦默認major。
- 136項評分、benchmark失敗處理、指型、optimizer與MIDI測試通過。指型測試曾抓到m7b5漏降五音，已修正並重跑。
- 三個音檔等長，逐弦起音符合manifest，峰值無clipping、尾端無殘音；真實瀏覽器已驗證播放推進與互斥暫停。首次UI檢查固定等150ms太早，改成等待實際播放進度後重建新目錄；保留未通過的10/24頁作紀錄，交付10/25頁。

## 成本與重現

官方舊二進位下載站45秒逾時；改用官方源碼，在使用者cache建置。Vamp僅安裝到隔離目錄；Boost開發標頭下載約10.7MB後解壓，未安裝進系統。原服務依賴、環境及引擎選擇未更換。官方repository標示GPL-2.0；本次未重分發其binary或原始碼。

兩個獨立benchmark程序冷啟動各24.5／26.1秒；後續每段約0.7–1.3秒，包含音訊載入。原曲正式候選整體51.4秒；不混稱純模型推論速度。來源、版本、雜湊、完整分數與渲染結果在 [結果JSON](evaluation/automatic-accompaniment-results-2026-10-25.json)。

```sh
VAMP_PATH=/home/jonas/.cache/guitarscribe-chordino-diagnostic/source \
PYTHONPATH=/home/jonas/.cache/guitarscribe-chordino-diagnostic/python \
/home/jonas/.cache/guitarscribe-runtime/bin/python \
  guitarscribe/backend/scripts/build_automatic_accompaniment_probe.py \
  --packet guitarscribe/output/evaluation/lyric-anchor-capture-2026-10-23/packet \
  --output /tmp/automatic-probe-new
```

渲染使用 `frontend/scripts/render-automatic-accompaniment.mjs`，指定`--packet --candidate --baseline --slug`，輸出目錄必須不存在。沿用實際Vite服務及產品pluckedTone音色。音訊產物只留本機，不納Git。
