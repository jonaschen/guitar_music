# 2026-11-23 個人雲端改版與交接

新版已部署，正式歌曲唯讀驗證、備份還原與停機結算完成。程式是 `1de9ee21255a560138b250fa0ec97aff81e444fc`，私人發布包 `releases/2026-11-23-v9`。兩小時本機持續操作測試尚在執行，結果不預先列為通過；收尾補於本文與 [驗證摘要](evaluation/cloud-update-2026-11-23.json)。

## 使用者可用的改善

- 上傳音檔分析失敗／取消，來源仍保留時可重新分析；新工作沿用原選項、舊人工稿保留。重試回覆丟失仍找回同一新工作，避免重複排隊。
- 修復排隊取消與重複取消時的名額／來源清理；分析顯示實際階段與經過時間，超限上傳限制記憶體讀取並清理暫存。
- 鎖定段落後可依個人主音／調式假設，切換實際和弦、羅馬級數與數字閱讀；保留原名稱、未知和局部範圍。
- Capo建議比較完整指型、前後換把及選填把位，採用時套用實際選出的按法路徑，並保留原發聲和弦。只剩根音的備用按法不算完整覆蓋。

[操作說明](Recovery_and_Degrees_2026-11-23.md)；[故事地圖與待辦盤點](Backlog_Review_2026-11-23.md)。這些改善沒有重新訓練辨識模型，也不代表音樂準確率提升。原曲／低頻練習仍預設不加人工和弦聲。

## 發布與資料保護

從已提交的Git HEAD清潔建置，包SHA256為 `2e213c9597426bcc2416dde401ba01a6ce5d08b2ba368617817dc33b60f90ed5`，2,010,203 bytes；manifest generation `1795438568500493`。v6–v8僅為本輪準備包，沒有部署到正式站。

只交換VM的app/site，Cloud Run image、runtime、environment、protocol與work保持。280個安裝檔案SHA與包一致，KEEP_SONGS=true，25首歌曲保留。更新前後、瀏覽器驗證後與停止前，6份既有資料庫的schema／rows及144個原檔均核對一致；唯一允許的schema新增是空的 `jobs/jobs.sqlite3:job_retries` 及其主鍵索引。

前版v5程式及manifest保留在 `/srv/guitarscribe/releases/2026-11-23-v9/previous`。現用版本看 `/srv/guitarscribe/app-release-manifest.json`，回退依 [操作手冊](APP_RELEASE_RUNBOOK.md) 只退程式，不能還原初始work覆蓋新進度。可重用的更新／比對工具及測試已進Git。

## 驗證證據

完整 [CI 45178334278](https://github.com/jonaschen/guitar_music/actions/runs/45178334278) 三個工作成功，對應上述正式程式commit：

| 類別 | 結果 | 範圍／界線 |
| --- | --- | --- |
| 後端 | 1483通過、3跳過、5 warnings | 2項缺systemd user環境；1項缺原作者參考來源。跳過不算通過。 |
| 雲端入口／備份 | 116通過、無跳過 | 本機缺依賴的4項已由完整CI補齊。 |
| 前端主要流程 | 358通過、7跳過 | 既有私人checkpoint／指定live revision條件未備齊；非新功能跳過。 |
| WebKit操作 | 20通過 | Linux WebKit，非實體iPhone。 |
| WebKit學習頁真API | 5通過 | 調性、原曲／參考聲、級數與局部範圍。 |
| Chromium／WebKit恢復及Capo真API | 4通過 | 丟失回覆後去重、採用指型、保存新版本、重開、原稿不變。 |

本機另完成221項Capo／轉調／指型相關後端、5項按法UI回歸、4項級數理論測試及清潔build。先失敗後修正的記錄涵蓋取消、重試、超限輸入、級數和Capo；沒有為通過而放寬原稿保護。

正式站匿名401、登入成功、3首既有歌曲的結構／和弦／學習資料及音訊Range206通過。桌面1440px Chromium與390px WebKit在《可惜不是你》鎖定副歌實測原曲A–B、級數草稿、錄音能量及Capo比較：無頁面例外、無橫向溢出、無正式稿寫入、原曲播放時參考音振盪器數為0。該曲Capo 0方案完整覆蓋160/160個和弦事件。這證明介面與資料契約，不證明160個和弦皆辨識正確；正式站沒有採用測試方案。

## 備份、還原與費用控制

私人桶 `hanana-491223-guitarscribe-private`，兩份均150檔；時間為台北：

| 時點 | Manifest | Generation | Manifest SHA256 |
| --- | --- | --- | --- |
| 更新前：21:17:01快照、21:19:14完成 | `backups/manifests/20261123T131701Z-35c8dc026d214abda176c4f8e6551a2c.json` | `1795439954345431` | `9f095574e6c042ac5c5e0f4d1db1d043e9c62ad8f2c2e87054441e66f74b7723` |
| 更新後：21:21:05快照、21:22:29完成 | `backups/manifests/20261123T132105Z-47337d37f482436a8cce20bcff7d349a.json` | `1795440149382445` | `c48837a037dc41884a8f177de869d339f746b03f1ff39aafbfaae4d2896450de` |

更新後備份實際下載還原到新目錄，逐object校驗generation／大小／SHA／MD5，6份SQLite integrity及邏輯hash通過，再與更新後work快照逐表逐檔一致。只清除本輪建立的還原目錄，沒有覆蓋線上work。

正常入口喚醒約58.85秒就緒。確認沒有分析、備份已完成且244秒無活動後，本輪自行啟動的VM以IAP poweroff；21:26:49查核TERMINATED／stopped、can_wake=true。31天帳本使用8520秒，剩135480秒，本次增加795秒（含安全邊際）；這不是實際帳單，也不是NT$300硬上限。

## 交接與未完成部分

下一個session先讀 [維護交接入口](MAINTENANCE_HANDOFF.md)。根目錄AGENTS.md、guitarscribe-autopilot、README與現行工作表都導向同一入口。137個歷史未勾選條目已有逐項狀態、理由及證據；沒有批次假勾完成。

完整stage快取／單層重算、指型套用範圍、全層TempoMap、通用錯誤標註與真歌資源baseline仍有工程待做。獨立音樂標註、實體手機與真實月帳單仍未知。主旋律、公開多人平台與ASR等維持停止／未納入範圍。

本輪跨session工具連線失敗，沒有宣稱已與programmer-session同步。所有改動按明確檔案清單提交；私人錄音、截圖、授權檔與一次性維護腳本留在ignored output，不放Git。
