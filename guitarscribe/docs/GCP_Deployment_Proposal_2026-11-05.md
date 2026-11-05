# Codex：Google Cloud 試用部署與成本方案

使用者先維持家裡電腦試用，也希望評估 Google Cloud。建議保留現行站，待決定投入雲端時，先做一次限時試部署，再決定是否常駐。本文件是方案，**尚未建立、購買或變更任何雲端資源**。

## 建議配置

採台灣 `asia-east1` 的 Compute Engine、Linux x86_64、既有 Docker Compose，延續單工作佇列與邀請密碼。優先考慮 **e2-standard-2：2 vCPU／8 GiB**；若小量朋友使用、可接受排隊，再試較便宜的 e2-medium。台灣區支援 E2，見 [官方區域表](https://docs.cloud.google.com/compute/docs/regions-zones)。

這個選擇沿用現成容器、SQLite 與背景分析工作，不需要先改成另一套服務架構。目前分析不需要 GPU 或付費辨識 API。本機已驗證2 CPU／2 GiB容器可在約46秒完成274秒控制歌曲；**尚未在GCP測速**，不能把這個時間直接保證給雲端。

e2-medium 雖對作業系統顯示2個 vCPU，持續CPU配額相當於1個 vCPU；與 standard-2 的效能條件不同。規格依 [Google 官方 E2 說明](https://docs.cloud.google.com/compute/docs/general-purpose-machines#e2_shared-core)。

## 月費試算

查核日期2026-11-05；台灣區、USD、隨用隨付、每月730小時。**沒有計入試用金、既有折扣、稅或匯率，也不購買長約。** 價格從官方頁面內台灣區的表格抽出，未誤用預設 Iowa 價格。

| 項目 | 較省方案 | 建議試部署方案 |
| --- | ---: | ---: |
| 機型 | e2-medium／4 GiB | e2-standard-2／8 GiB |
| VM 每小時 | US$0.03879594 | US$0.07759188 |
| VM 每月 | US$28.32 | US$56.64 |
| 40 GiB balanced disk | US$4.00 | US$4.00 |
| 一個使用中的外部 IPv4 | US$3.65 | US$3.65 |
| **上述固定項目小計** | **US$35.97／月** | **US$64.29／月** |
| 小量試用的規劃預算 | **US$40–50／月** | **US$70–80／月** |

來源：[VM 台灣區價格](https://cloud.google.com/products/compute/pricing/general-purpose)、[磁碟價格](https://cloud.google.com/compute/disks-image-pricing)、[外部 IPv4／網路價格](https://cloud.google.com/vpc/network-pricing)。磁碟按配置容量收費；IPv4採US$0.005／小時。最後一列是我們預留流量與小量備份的規劃額度，**不是封頂報價**；大量播放／下載、備份、網域或額外雲端服務另計。若直接保留20 GiB標準快照資料，以台灣區US$0.05／GiB月估算約US$1／月，實際取決於儲存量。

初期沿用既有 HTTPS 入口或既有網域的單機 TLS，沒有規劃 Load Balancer、Cloud NAT、Cloud SQL 或 GKE。40 GiB是起始容量，不是歌曲無限保存；容量接近上限時須另做保留策略或擴容。

## 上線前只做一輪限時驗證

1. 先確認部署專案、帳務歸屬與HTTPS入口；本機 gcloud 的預設專案不自動視為使用者已選定的部署位置。
2. 經同意後，建立一台 e2-standard-2 試驗 VM，最多運行24小時；套用已驗證映像，使用獨立測試資料，保留家中站作回退。
3. 優先在該主機測試 YouTube 長／短網址下載。家中網路成功不保證雲端網路也成功；若此主要入口不可用，停止這個部署候選，不先搬全部資料。
4. 通過後驗證完整歌曲分析、手機播放、保存／重啟及備份還原，再決定是否切換受邀入口。雲端部署不改善辨識模型本身，音樂品質仍單獨檢查。
5. 試驗結束後清理本次建立的 VM、磁碟、IP 等資源；保留報告與必要備份。僅停止 VM 不等於所有費用歸零。

24小時的 VM＋40 GiB磁碟＋IPv4 約US$2.11；可先以 **US$5作試部署規劃額度**，涵蓋少量流量與操作餘裕，需另外取得執行同意。這不是已授權支出，也不是帳單硬上限。

預算告警不會自行停止這台VM的計費。Google的新 spend cap 支援特定API服務，並不停止持續存在的運算／儲存資源；本方案仍須有到期關機與清理。見 [官方預算說明](https://docs.cloud.google.com/billing/docs/how-to/budgets)、[spend cap 適用範圍](https://docs.cloud.google.com/billing/docs/how-to/budgets-spend-caps)。

## 現在的決定

維持家中試用站，雲端方案先備妥，不要求現在立刻購買。若決定試部署，才確認目標專案與這一輪支出；不把雲端建站當成音樂品質已過MVP門檻。

對應程式已推送 `197504b`；[容器驗證報告](Container_Release_Verification_2026-11-05.md)與 [維運步驟](OPERATIONS.md)可供審閱。價格原頁與台灣區抽取資料保存在本機 `output/evaluation/gcp-deployment-plan-2026-11-05/`，不包含雲端憑證或帳單。
