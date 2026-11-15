# 歌曲結構名稱辨識：第一輪候選與操作說明

日期：2026-11-15。對應 [故事、地圖與代辦](Song_Structure_Stories_and_Plan_2026-11-15.md) 的 ST1–ST3；依使用者選擇先做名稱辨識，沿用與反覆表示在後。

## 交付狀態

已完成兩首固定錄音的本機推論與獨立核對頁，ST1／ST2 工程完成；ST3 的回聽與報告已完成，音樂品質仍是 `awaiting_human`。這不是 ST1–ST7 第一階段全部完成。

| 錄音 | 歌曲段落初稿 | 未判定時長 | 相鄰同名邊界 | 有效執行耗時 |
| --- | ---: | ---: | ---: | ---: |
| 膽小鬼（258.107 秒） | 14 | 0 秒 | 7 | 846.84 秒（約 14 分鐘） |
| 沒那麼簡單（304.472 秒） | 14 | 3.852 秒 | 4 | 921.89 秒（約 15 分鐘） |

以上不是正確率。兩曲區間均完整覆蓋、無重疊與越界；相鄰同名邊界保留，尚未確認是否過切。《沒那麼簡單》開頭 3.85 秒為未判定，末尾約 0.0017 秒是模型 end 區間經音檔長度限制後的短段；原模型末端 304.48 秒保留在資料，未硬改為尾奏。短於 0.1 秒的段落仍列出，改用「聽交界」核對，不提供無法有效聽辨的單段播放。

**驗證：48 項後端／8 項瀏覽器測試通過；兩首真實錄音各四尺寸、播放中切歌、原曲定位與自動停止通過，零寫稿／零合成音／零頁面例外。** 根音稿與原 Score 和分析前 snapshot 完全相同，原 186 個網站檔案不變，服務未重啟。programmer-session 完成唯讀程式／第一首資料與入口核對。[完整數值與段落表](evaluation/song-structure-results-2026-11-15.json)。

每首耗時僅計有效 runner，不含安裝與先前被停止的錯誤前處理（374.94 秒）。systemd 記錄記憶體峰值分別為 2.2G／2.3G，第二首模型階段 swap 峰值 22.6M，均在固定上限內。第二首外層工具 launcher 約 15 分鐘結束（143），受監督的服務仍在 20 分鐘限制內正常產出完成 manifest／candidate；已留服務 journal，沒有因此重跑或誤用 running 結果。

目前工程已提供：固定來源／門檻、隔離模型執行器、候選格式與來源檢查、獨立參考評分器、只播放原曲的結構回聽頁。現有兩曲沒有獨立結構標註，因此名稱正確率、邊界品質與實際修正量都是未知；不能升為正式預設。

## 如何使用核對頁

入口：[歌曲結構初稿](http://127.0.0.1:5273/structure-review-2026-11-15/)，沿用本機網站登入。

1. 在「歌曲」選擇《膽小鬼》或《沒那麼簡單》。
2. 查看整首的歌曲段落初稿。前奏、主歌、副歌、橋段、尾奏保留各自名稱；器樂段／獨奏段只稱為間奏候選。
3. 按「聽這段」從該段起點播放，到結束自動停止；按「聽交界」播放段落起點前後各 3 秒。首尾不會播放超過音檔範圍。
4. 可使用原曲播放器暫停或自由定位。切換歌曲會停止前一首的回聽。
5. 按「回到這首歌的根音練習」回原有視覺練習頁。

這是核對頁，目前不能修改名稱、移動邊界或保存結構。根音練習仍用原稿；159／151 個根音小段不會被刪除或當成這裡的歌曲大段。先知道名稱初稿是否有幫助，再接可修正／保存／篩選的正式流程。

回聽只有原音訊，不加入合成根音、模型 sonification 或辨識和弦聲音。頁面上的「待確認」涵蓋名稱與邊界；全曲有覆蓋並不表示全曲都辨識正確。

## 方法與可重現性

- 原作者 [All-In-One](https://github.com/mir-aidj/all-in-one) 查核版本 `18e78903c0365147a2c5d4e5e57ebf88cb7d800e`。
- 本次使用 [all-in-one-infer](https://github.com/openmirlab/all-in-one-infer) 純 PyTorch attention 移植，固定版本 `c83bc00800fe5e6edf568ace427fd35587d7d567`。它是候選，不宣稱整條推論與原作者環境等價。
- 固定 `harmonix-fold0`，不是八 fold ensemble；兩首用同一模型／參數。原作者 checkpoint SHA-256 `0db596dfb0995f41d62f6267d76a9d54c046f1649bd35e1dbeca0c5f9a7b8acd`，來源 HF `taejunkim/allinone` revision `379e5fd010b3fdd0ee8381ff8cbcfa51d70b5c19`。
- 本機無 GPU；這不代表原版一定不能跑 CPU。選移植版是本次相容性候選，並未以 CPU 限制推論出原版不可用。
- 新環境 `~/.cache/guitarscribe-structure-runtime`，以 `.pth` 只讀引用現有基礎套件，新增依賴安裝在新環境。現行服務 runtime 未重新安裝或更新。
- 原版 Demucs 4.0.1 CLI 在原 runtime 執行 HTDemucs 四聲部，轉成 44.1 kHz／雙聲道，使用原版全曲 mean/std 正規化與逆轉、shifts=1、overlap=.25、PCM16 WAV／clip rescale；在該子程序同時固定 Python random 與 torch seed=0。
- 驗證 bass／drums／other／vocals 四檔的取樣率、聲道、相同幀數、時長及 SHA，再以 `skip_separation=True` 交給結構模型。每次執行用新輸出／spectrogram 目錄，不按 `input.wav` 同名重用不同曲目的快取。
- 每曲整個程序群最多 20 分鐘、2.5 GiB RAM、0.5 GiB swap、200% CPU；兩首依序執行。音訊不送外部分析服務，網路僅用於取得程式／模型。
- [固定 v1 協定](evaluation/song-structure-protocol-2026-11-15.json)、[預測前 v2 修訂](evaluation/song-structure-protocol-v2-2026-11-15.json)、[環境與 Demucs 權重 hash](evaluation/song-structure-environment-2026-11-15.json) 留存。

### 已發現並拒絕的前處理問題

第一次執行發現移植版直接把來源的 48 kHz 波形送入預期 44.1 kHz 的 HTDemucs，並未使用原 CLI 的全曲正規化。已在產生結構預測前停止，保留 `cancelled_invalid_preprocessing` 紀錄；不能把該次結果列為完成或音樂品質失敗。

v2 只修正為上述原版 CLI 前處理，來源、單 fold 模型、品質門檻與資源上限均未更改。此問題也新增先紅後綠的取樣率／聲部／長度拒絕測試。移植版 attention 的五份上游 NATTEN golden fixtures 通過，只支持該算子數值對照，不代表所有前處理、模型與後處理已完全等價。

### 授權查核界線

原作者 [Hugging Face 模型卡](https://huggingface.co/taejunkim/allinone/blob/379e5fd010b3fdd0ee8381ff8cbcfa51d70b5c19/README.md) 標示 MIT；移植套件的 checkpoint metadata 有不同的 CC-BY-NC-SA 標示，矛盾保留記錄，不能把移植套件的標示直接當成作者授權。madmom 程式與其預訓練模型資料亦有不同授權；這條路徑使用 DSP／DBN 與 All-In-One logits，不呼叫 madmom 的預訓練 beat RNN。此輪是本機個人練習候選，沒有新增公開模型／音訊散布。

## 評分規則與測試能證明什麼

協定在預測前固定：逐曲時長加權名稱正確率至少 .85，主歌／副歌 recall 至少 .80，整段副歌完全漏辨為 0，邊界 F1（3 秒容差）至少 .80，另報 .5 秒結果；參考覆蓋至少 .95、跨參考集主歌與副歌各至少兩次且各 30 秒，修正段落比例至多 .25。第三首保留曲尚未選定，不能宣稱跨曲泛化驗收完成。

`compare_structure()` 只接受帶來源 SHA、標註者、證據與獨立性聲明的參考。名稱按時間交集評分，邊界排除錄音首尾並作一對一匹配；未知參考區降低標註覆蓋率，不假充已知答案。沒有參考就不報準確率；標註者聲明仍需審查，程式不能證明其獨立性。需要人工修正多少次另計。`assess_reports()` 依固定協定檢查逐曲與跨集門檻，拒絕把相同音訊 SHA 重複當新證據；缺參考為 `awaiting_reference`、缺修正量為 `awaiting_human`，通過也只稱為 `passed_on_reference_set`，不自動升為正式預設或宣告保留曲驗收。

自動測試使用刻意已知的區間與音訊格式案例，包含所有段都誤標副歌、漏掉副歌、位移邊界、同一邊界不可匹配兩次、未知區域、錯誤來源、失敗殘留候選、來源時間小量取樣舍入。瀏覽器測試檢查播放、停止、切歌、錯誤狀態與四尺寸；這些都不是兩首真歌名稱正確性的證據。

## 重跑與回退

有獨立標註後可用 `backend/scripts/score_song_structure.py --run <完成目錄> --reference <標註JSON> --out <新結果JSON>` 評分；標註須含 `audio_sha256`、`independent_of_candidate: true`、`annotator`、`evidence` 與 `sections`（每項 start／end／label）。只做模型結果轉存不構成獨立標註，不能勾選獨立性。

執行器：`backend/scripts/analyze_song_structure.py`；完成後才以 `backend/scripts/build_song_structure_review.py` 建立全新核對目錄。執行需要包含本機音檔路徑與原 Demucs Python 路徑的 runtime protocol；版本庫中的協定省略機器路徑，不能直接當輸入。模型安裝版本見環境紀錄，避免以最新版覆蓋。

執行推論時須以程序群資源限制包住整個 runner，不能只限制 Demucs 子步驟；例如在 repository 根目錄：

```sh
systemd-run --user --unit=structure-unique-run --pipe --wait \
  --property=MemoryMax=2684354560 --property=MemorySwapMax=536870912 \
  --property=CPUQuota=200% --property=RuntimeMaxSec=1200 \
  --property=TimeoutStopSec=10 --property=Nice=10 \
  --working-directory="$PWD" \
  env OMP_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
  /home/jonas/.cache/guitarscribe-structure-runtime/bin/python \
  guitarscribe/backend/scripts/analyze_song_structure.py \
  --protocol guitarscribe/output/evaluation/song-structure-2026-11-15/protocol-v2.json \
  --job <job-id> --out <全新輸出目錄>
```

若外部 timeout／OOM／取消導致 Python 無法寫最後狀態，需依退出原因把殘留 `running` 記錄成失敗／取消並保留 log；`build_song_structure_review.py` 只接受 `candidate_ready_unreviewed`，即使目錄留有 candidate 檔也不採用。發布時再檢查音訊 SHA、來源關聯及完整區間。

```sh
# 在 guitarscribe/frontend，執行隔離頁的互動測試
npx playwright test --config playwright.structure.config.ts

# 真實本機兩曲唯讀檢查；需要已完成推論與已發布核對頁
node scripts/check-song-structure.mjs
```

新的核對頁是獨立靜態目錄，不替換原練習入口、不更改 API 或重啟服務；回退可移除該新增目錄。所有實驗資料留在 `output/evaluation/song-structure-2026-11-15/`；音檔、權重、credentials 不納入 Git。

## 下一段

音樂品質保留 `awaiting_human`。ST4–ST7 尚未完成：獨立結構保存契約、可修改名稱／邊界、確認／復原、依歌曲大段導覽原根音工作區。ST8–ST11 才處理比較、沿用與反覆譜；名稱相同永遠不等於和弦或根音相同。
