# 個人雲端練習與面對面討論

## 使用者決定

使用既有 Google Cloud 專案 `324350766154`（`hanana-491223`），先自己使用，新增雲端費用盡量每月 NT$300 以下。保留原本介面，帶著自己抓的歌曲結構、根音、和弦、低頻圖與原曲回聽，直接向別人說明判斷依據。**不需要匯出、不新增朋友帳號或公開分享頁。**

本文件取代 11/05 的常駐 VM 建議；當時的容器沒有後來加入的結構分析執行環境。既有專案另有三個 Cloud Run 網站，本次只新增 `guitarscribe-*` 資源；NT$300 是 GuitarScribe 的新增費用目標，不包含其他網站帳單。

## 開始使用與現場說明

固定入口：**https://guitarscribe-324350766154.asia-east1.run.app**

1. 用手機或電腦開啟網址，輸入個人雲端帳號 `jonas`。密碼是獨立產生的，存於本機 `guitarscribe/output/cloud-control/access.json`；不是舊的本機展示密碼，也不放進 Git 或文件。
2. 若看到休息畫面，按「啟動工作室」。第一次實測約 49 秒，實際可能更久；出現「進入原本介面」後即可開啟。等待時重新整理狀態即可，不用連續按啟動。
3. 頂端「我的歌曲」→ 選歌曲的「視覺練習」或「樂譜」。它使用雲端歌曲清單，因此換裝置也能找到原來的歌；樂譜會優先開啟最近保存的修訂。新分頁保留原分頁尚未完成的操作。
4. 要說明判斷：在原「歌曲結構」選一段已確認的主歌／副歌，按「鎖定這段練和弦」→「產生低頻圖」→ 移動圖上游標、選 A–B 範圍、播放原曲，對照你填的根音或和弦。低頻圖與原曲回聽不加入合成和弦。
5. 修改和弦後等「已保存」再離開。頁面會顯示本輪剩餘時間；到 2 小時會停機，回使用狀態重新啟動。沒有保存成功的瀏覽器草稿不保證能跨裝置恢復。
6. 不用了就關閉或隱藏練習頁；30 分鐘沒有活動且沒有分析時會休息。保持頁面可見會維持活動，但仍受每輪 2 小時上限約束。

「我的歌曲」是原介面的導覽補充，沒有另做匯出譜或分享頁。已搬移 25 首完成歌曲，包括《可惜不是你》的 9 大段、近期其他練習曲與已保存根音／樂譜進度。**之後請以這個雲端網址為主要進度，本機舊站不會自動同步。**

新增歌曲仍可使用原介面的「上傳音檔」。本次實測既有 YouTube 網址時，YouTube 對雲端 IP 回覆機器人驗證，直接貼 YouTube 網址目前不能保證成功；已匯入的歌不受影響。沒有移轉瀏覽器 cookies 或規避來源限制。

## 使用者故事與故事地圖

| 步驟 | 使用者故事 | 驗收 |
| --- | --- | --- |
| 開啟 | 我在外面也能登入自己的練習空間 | 固定 HTTPS 入口，匿名不可讀取、播放或啟動主機；家中電腦關閉也可用 |
| 繼續 | 換裝置仍能找到歌曲與已保存進度 | 雲端「我的歌曲」可進入原視覺練習與最近保存樂譜；結構、根音、和弦稿各自保留 |
| 討論 | 我能指出為什麼這樣抓 | 原本低頻圖、游標、A–B 原曲回聽、結構與和弦編輯全部沿用；看圖不添加和弦聲音 |
| 離開 | 不使用時節省費用，回來資料仍在 | 關閉/隱藏頁面後 30 分鐘無活動且沒有分析才提早停機；資料留在持久磁碟 |
| 維護 | 改版後仍能接續練習 | 來源版本與檔案雜湊、SQLite 一致備份、原曲校驗、重啟驗證與可回退發布 |

## 部署方式與費用控制

採台灣區按需啟動的 `e2-standard-2`（2 vCPU、8 GiB）與 40 GiB `pd-standard` 持久磁碟。Cloud Run 小型入口提供登入、喚醒與內網代理；閒置可縮至零。主機使用臨時外部 IP 下載音訊，沒有固定外部 IP、NAT、Load Balancer、Cloud SQL 或長約。私人音訊與備份桶不對外公開。

這個方式保留現有 SQLite、systemd 資源限制、原 Demucs 前處理及已驗證的結構模型；不需為個人試用先重寫所有資料庫。Cloud Run 本機檔案不適合當唯一持久資料；其入口只存無狀態代理，啟動帳本另存 GCS，以 generation 條件寫防止同時重複啟動。

每次最長 **2 小時**，由 Compute Engine 平台執行 STOP；近 **31 天合計最多 40 小時**。每次啟動先預留 2.5 小時，只有核對主機實際 start/stop 時間才結算退回多餘時數。啟動失聯不重發、不先退額度；跨月份不會直接歸零放行。安裝與驗證的主機時間也納入帳本。剩不到 30 分鐘時暫停新增長分析，保留閱讀、回聽與保存。

計價查核：台灣 VM 每小時 US$0.07759188、臨時外部 IPv4 使用時每小時 US$0.005。以 40 小時計，兩者約 US$3.30，另加持久磁碟、入口請求、儲存、流量與稅。用 **1 USD = NT$35 作保守規劃假設（不是即時匯率）**，先以約 NT$180–300 規劃小量個人使用，實際仍依用量與帳單核對。免費額由帳務帳號共享，沒有預先當作一定免費。

40 小時是主機使用限制，**不是總帳單 NT$300 的硬封頂保證**。大量播放下載或其他專案費用不在此限制裡。Google 已有部分服務的 spend cap，但同專案 Cloud Run 限額會牽連其他三個網站，本次不設定這種共用限額。

來源：[VM 價格](https://cloud.google.com/products/compute/pricing/general-purpose)、[磁碟價格](https://cloud.google.com/compute/disks-image-pricing)、[IP 與網路價格](https://cloud.google.com/vpc/network-pricing)、[平台自動停止](https://docs.cloud.google.com/compute/docs/instances/limit-vm-runtime)、[Cloud Run 計費](https://cloud.google.com/run/pricing)、[spend cap 範圍](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)。

## 排序待辦與狀態

| 順序 | 工作 | 狀態 |
| --- | --- | --- |
| 1 | 目標專案、現有服務與費用盤點，確認個人使用範圍 | 完成 |
| 2 | 有登入保護的喚醒入口、外部用量帳本、平台停機、串流代理 | 完成；真雲端喚醒已通過 |
| 3 | 清潔程式包、既有 runtime 與模型、SQLite/API 備份及原曲校驗 | 完成；6 份資料庫與 143 個既有檔案一致 |
| 4 | 私有 VM、資料搬移、原介面與跨裝置歌曲入口 | 完成；25 首歌曲可由清單進入 |
| 5 | 真雲端登入、音訊 Range、低頻圖、保存/衝突、停機後恢復 | 完成；兩次停機／喚醒，保存版本與內容一致 |
| 6 | 維運、備份/復原、用量查詢、改版/回退與使用說明 | 完成；真 GCS 備份、去重與新目錄還原通過 |

## 維護界線

執行環境封裝限定 Ubuntu 24.04 x86_64 / CPython 3.12，保留套件版本與授權檔。它是已驗證環境的移轉包，不宣稱任意 Linux 可直接移植。程式包從 Git 提取後重新建置，只收 `index.html` 與程式 assets；不帶本機生成的試聽站。個人資料另包，兩者不可混成公開下載。

首次移轉後，本機保留原資料；雲端與本機**不是雙向同步**。後續使用雲端網址作為主要進度，維護時不得拿舊的本機資料覆蓋雲端。重開機不得重新匯入初始備份。

程式維護仍需實際執行代理與驗證；這份部署不代表代理在回合結束後會自動持續開發。工程驗證不替代音樂正確性；使用者確認的結構與和弦判斷應保留原狀。

## 維運操作

資源識別集中於 [`deployment.json`](../infra/on_demand/deployment.json)，執行碼與測試在 [`infra/on_demand`](../infra/on_demand)。私人安裝包、音訊、備份只存在私人桶 `gs://hanana-491223-guitarscribe-private/`；入口映像固定 digest，密碼透過 Secret Manager 掛載。VM 僅接受入口的 5273 與 IAP 的 SSH，沒有公開後端連接埠。

- VM：`guitarscribe-personal`，`asia-east1-b`；40 GiB 開機磁碟不隨 VM 刪除。**停止 VM** 會保留磁碟，刪磁碟才會失去該份資料。
- 程式：`/srv/guitarscribe/app`；網站：`/srv/guitarscribe/site`；進度與音訊：`/srv/guitarscribe/work`。`GUITARSCRIBE_KEEP_SONGS=true` 明確取消工作到期清理，重開機仍會回收中斷分析的操作狀態，不刪已完成的歌。
- 平時從網頁啟動。不要在 Console 任意另開主機繞過用量帳本；未能核對的啟動會停在保守狀態，需維護者調查，不能直接刪掉帳本重置時數。
- 查詢運行狀態：登入後 `/cloud`；頁面所示包含預留時數，並非即時帳單。實際費用至 Cloud Billing 按 `guitarscribe` 資源與服務核對。
- 程式單元：`guitarscribe` 使用者的 `guitarscribe.service`；備份／閒置是系統單元 `guitarscribe-backup.timer`、`guitarscribe-idle.timer`。

IAP 維護入口（僅維護者的 Google 身分；不是網站密碼）：

```sh
gcloud compute ssh guitarscribe-personal --project=hanana-491223 --zone=asia-east1-b --tunnel-through-iap
```

### 備份與還原

開機 15 分鐘後、執行中每 30 分鐘嘗試一致備份。正在分析或資料變動時本輪跳過／失敗，保留前一份完整備份；日誌有明確結果。每個音訊／SQLite 快照先存成不可覆寫的 SHA-256 物件，最後才發布完成 manifest。相同檔案去重，不會每半小時重傳全部原曲。主機可讀備份、只能新增 `backups/`，不能刪掉或覆寫舊備份。

磁碟上的成功保存立即保留；異地備份有排程間隔，並不是每次編輯同步完成。備份日誌：

```sh
sudo journalctl -u guitarscribe-backup.service -o cat --no-pager -n 20
sudo systemctl start guitarscribe-backup.service
```

還原必須選擇日誌中 `status=complete` 的 manifest 與 SHA，寫到**不存在的新目錄**。工具會驗證所有檔案、SQLite integrity 與邏輯內容；既有目錄會被拒絕。

```sh
sudo -u guitarscribe /srv/guitarscribe/runtime/main/bin/python /srv/guitarscribe/app/backend/backup_work.py restore \
  --bucket hanana-491223-guitarscribe-private \
  --manifest backups/manifests/20261120T121343Z-282ace04eb5a44bab718b13d5ea67bd1.json \
  --manifest-sha256 ad46cdf13c82b49f43c9b59f0adcbeb0421a5ca508c5b7d0b3e555dc5186acff \
  --target /srv/guitarscribe/restored-NEW
```

以上是首次驗證用快照，正式救援應選當時最新且完整的一份。驗證後才安排停止程式、備份目前工作目錄、人工切換；工具本身不覆蓋線上 `work`。本次真 GCS 還原 150 個檔案已通過，第二次備份新增 0 個 blobs。舊備份目前不自動刪除；日後隨歌曲數／修改量檢視儲存費用，不能單獨刪仍被 manifest 引用的 blobs。

### 改版與回退

1. 先跑所改層的測試，確定無正在分析或未保存操作；確認最新完整備份。
2. Git 版號、清潔建置與 runtime 套件清單隨私人 release 保存。新的前端只包含 `index.html`／`assets`／雲端導覽，不能直接發布本機整個 `dist` 或 `public/listening`。
3. 主機程式更新只替換 `app`／`site` 並保留上一版；**不要解開初始 `personal-work.tar.gz` 覆蓋現有 work**。目前 `bootstrap.py` 在 `.installed` 存在時只設定維護單元，不重匯資料，也不是自動升版器。
4. 健康、匿名拒絕、歌曲清單、音訊 Range 與一首唯讀練習查核通過後才交付。若失敗，回上一版程式／前端；這輪沒有破壞性 DB migration。不可把歷史的未啟用長期保存版直接切回而遺失 KEEP_SONGS 保護。
5. 入口用已知映像 digest 部署新 revision；依需求回上一 revision，私人資料留在 VM／GCS，不在 Cloud Run 容器檔案系統。

本次只遷移已驗證的既有 runtime，沒有宣稱提升和弦／結構音樂準確率。手機寬度經桌面 Chrome 自動化驗證，實體手機與 Safari 仍未實測。

## 2026-11-20 驗證結果

- 基礎設施 94 項測試通過：登入／CSRF、重複啟動與 generation 衝突、滾動額度與停止期限、串流／斷線／h2c 33 MiB、備份與拒絕覆蓋、復原及歌曲清單。後端歌曲／YouTube 35 項通過。長期保留、來源攔截提示與舊歌清單均先取得失敗測試再修正。
- 真雲端的三首原曲在 1440／390 寬度產生非空低頻圖、鎖定副歌與原曲播放正常；零合成音、零原稿寫入、零頁面例外。手機硬體／Safari 未驗證。
- 獨立合成測試歌曲由原瀏覽器介面選副歌，保存 `Am/C`、復原、重做、重載成功；另一分頁舊版本寫入被拒絕。主機真正停止再經網頁啟動後，和弦 v3 與完整回應雜湊一致。測試歌時間設為 2000 年，證明長期保存開關生效。測試歌已清除，原六份 DB 邏輯內容完全不變。
- 結構分析在 VM 以原 Demucs／模型／systemd scope 執行 12 秒合成 fixture，88.906 秒完成 ready；沒有套用至使用者稿。這只驗證執行鏈，不評音樂品質。
- 真備份首次 150 個檔案／約 1.27 GB 新 blobs，第二次 0 新 blobs；從 GCS 取回到新目錄，逐檔 SHA 與 SQLite 驗證成功。失敗／部分上傳不發布完成 manifest。
- 正式 app `27afecb`，私人 `releases/2026-11-20-v3`；270 個程式／站點檔案完全吻合 manifest。前端基底仍是 `7925dcc` 的清潔建置，只有雲端導覽補充。入口以 deployment.json 所記 digest 部署。

證據摘要：[機器可讀驗證](evaluation/cloud-personal-2026-11-20.json)。含私人音訊的安裝包與瀏覽器截圖留在本機 output／私人桶，不發布到 Git。

測試範圍：上述為本次相關自動測試與正式雲端實測。查核時發現基底 `7925dcc` 的[既有全專案 CI](https://github.com/jonaschen/guitar_music/actions/runs/44090189688) 已有後端 32 項與前端多項失敗；本次沒有宣稱全專案 CI 全綠。新雲端測試另加入 CI，既有全套問題另列維護待辦，不以實際部署通過取代它們。
