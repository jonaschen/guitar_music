# GuitarScribe 個人雲端：新 session 的維護入口

適用於現有個人雲端，不是建立第二套服務的部署教學。使用者已確認目前抓歌練習主線可用；維護優先保留雲端最新人工稿。來源版本與最近操作可過期，先查當下狀態。

## 快速接手

1. 找到 Git repo（目前 `/home/jonas/gemini-home/music_analysis`），讀 `guitarscribe/infra/on_demand/deployment.json`、`guitarscribe/docs/Remaining_Stories_2026-11-21.md` 與 `git status --short`。有其他 session 時協調檔案所有權，單一負責者部署。
2. 執行本 skill 的 `scripts/cloud_status.py --repo <repo>`。它只查指定 VM／Cloud Run／備份 manifest 清單與登入狀態，不開機、不讀歌曲、不改 gcloud 預設專案。可用 `--output <repo>/guitarscribe/output/cloud-control/status-YYYYMMDD.json` 保存證據。
3. 確認憑證可用即可，不印 token／密碼。若 gcloud 未登入／權限不符或本機 access.json 缺失，回報無法查核的部分；不要為了巡檢重設密碼或替換服務帳戶。
4. 判斷是正常休息、登入問題、入口故障、VM／應用故障，還是來源服務拒絕。沿下表縮小範圍，再做所需處置。單純狀態查詢不需要喚醒；功能測試／修復確實需要運行時才在現有授權內啟動。

## 固定識別與資料位置

- 專案 `hanana-491223`，編號 **324350766154**；區域 asia-east1，zone asia-east1-b。此專案另有 capybara／hanana／kim 服務，勿改其配置或套共用停機／費用上限。
- 使用者入口是 `https://guitarscribe-324350766154.asia-east1.run.app`。Cloud Run 也回傳另一個雜湊網址，但入口 Host 檢查只接受設定的 public origin；使用 deployment.json 的網址。
- VM `guitarscribe-personal`，Cloud Run `guitarscribe`，網路 `guitarscribe-private`，內網預期 `10.88.0.2:5273`。需以實際設定核對，不自動改 IP／firewall。
- 程式與環境 `/srv/guitarscribe/{app,site,runtime,protocol.json,environment}`；**雲端 `/srv/guitarscribe/work` 是最新資料**。本機 `guitarscribe/output/web-preview/work` 是獨立舊副本，不雙向同步。
- 私人桶 `hanana-491223-guitarscribe-private`：`releases/` 是安裝程式／初始快照，`backups/` 是不可覆寫的已保存資料備份，`control/usage.json` 是啟動帳本。不要混淆初始快照與最新備份。
- 本機密碼 `guitarscribe/output/cloud-control/access.json`，VM `/srv/guitarscribe/access.json`；Secret Manager `guitarscribe-access`，部署指定版本。不要貼內容、放進 Git 或借用其他服務密碼。SSH key 在同本機目錄 `ssh`，不提交。
- `.installed` 與 `release-manifest.json` 記錄主機版本。`bootstrap.py` 已安裝分支保留 work，只設定維護單元；**改 metadata 不代表已升級 app**。

## 狀態如何解讀

| 證據 | 意義／下一步 |
| --- | --- |
| 匿名入口／API 401 | 正常登入保護。登入後才看歌曲與喚醒；不把401當不可用。 |
| VM TERMINATED；status stopped；can_wake=true | 正常休息。資料仍在持久磁碟。勿以重新部署或重新匯資料處理。 |
| checking／starting／preparing | 入口確認資源或開機中；約一分鐘是曾測值，非保證。核對時間與下一次狀態，不連續重送啟動。 |
| can_wake=false／帳本不一致 | 可能預留時數不足、狀態不確定或繞過帳本啟動。核對 VM start/stop、usage.json generation 與事件；不刪帳本、不直接退款、不用 Console 繞過限制啟動。 |
| Cloud Run Ready=false／5xx | 查目前 revision 與該服務日誌；確認完整 GUITARSCRIBE_CLOUD_* 環境鍵、secret掛載與 Direct VPC。輸出時避免完整環境／secret。 |
| VM RUNNING 但 preparing 持續 | 用 IAP 查看主機 user service、健康狀態、磁碟和開機日誌。入口 `/cloud/status` 的探測不會維持主機活動。 |
| 409 保存衝突 | 版本／結構／來源不同，先保留瀏覽器草稿與最新服務端稿；不要強制用舊版本覆蓋或重跑分析。 |
| 新分析409且剩不到30分鐘 | 本輪時間護欄；可繼續保存／回聽，停止後再由網頁啟動新一輪。 |
| YouTube bot challenge | 來源拒絕此主機下載，已匯入的錄音仍可用。提供音檔上傳；不靠換帳號／cookies／代理反覆規避。 |
| 沒有近期備份 | 先看主機運行時間與是否分析中。定時器只在運行時執行，分析中會延後；舊 manifest 存在不代表本輪成功。 |

## 主機排查與操作界線

IAP SSH（VM需已運行，SSH不會自動喚醒）：

```sh
gcloud compute ssh guitarscribe-personal --project=hanana-491223 --zone=asia-east1-b --tunnel-through-iap
```

系統單元：`guitarscribe-backup.service/.timer`、`guitarscribe-idle.service/.timer`。應用是 **guitarscribe 使用者的** `guitarscribe.service`，不是 root system unit，也不是本機的 `guitarscribe-friends-web`。先 `id -u guitarscribe`，再使用對應 `/run/user/<uid>` 的 XDG_RUNTIME_DIR 與 user bus 查 `systemctl --user status`／journal。不要假設 UID 永遠1501。

新版主機的 `/backend/cloud/maintenance` 提供備份狀態與可用磁碟；持久紀錄在 `/srv/guitarscribe/maintenance/backup-status.json`，不放進 work 造成遞迴備份。`complete` 才是已完成，`pending` 是之後又有修改，`deferred` 為分析或其他備份中；`failed/interrupted/unknown` 不可當成功。舊版404代表尚未部署，回到timer／manifest核對。詳見 `guitarscribe/docs/Cloud_Maintenance_2026-11-21.md`。

先查 `systemctl show guitarscribe-backup.service -p ActiveState -p Result`、`journalctl -u guitarscribe-backup.service -n 20`、`df -h /srv/guitarscribe`。應用故障再查該使用者服務日誌。不要 `cat environment/access.json` 來蒐集狀態，也不要貼完整 job payload。

重啟／停止／更新前：核對使用者是否正使用、最後活動、jobs 的 active 狀態、structure-analysis 的 running/cancelling、root candidate lock 與備份進程。`host_activity.active_analysis(work)` 能查分析；近期 activity 不能被當成「肯定無未存草稿」。使用者正在編輯時延後服務中斷；繼續本機獨立工作。需要重啟的安全窗口與授權依當下上下文判斷，不把本 skill 當額外授權來源。

## 喚醒、費用與停止

平時使用原網頁的「啟動工作室」。API需本人Basic認證、正確Origin與從/cloud取得的短效CSRF token；不要把憑證放命令列或重播舊 token。Controller先以GCS generation CAS保留時數，再發一次帶 requestId 的Compute start；不確定結果不得盲重送。

每輪上限7200秒／平台STOP，滾動31天40小時；每次先預留9000秒，核對真實start/stop後結算。usage數字含預留與安全邊際，不是帳單。磁碟／備份／入口／流量仍有費用，NT$300是目標，不是總額硬上限。帳單查核要分出其他三服務，不因共享免費額推論一定免費；實際價格問題需查當下官方資料。

可見練習頁會每分鐘heartbeat。關閉／隱藏後30分鐘無活動且無分析可提早停止；平台2小時上限仍有效。自行啟動的驗證工作完成後，在確認無使用者工作／分析／備份的前提下停止，保留磁碟，從 status核對帳本結算。不要刪除 VM／磁碟來「省錢」。

## 備份、復原、發布

詳細可執行步驟在 `guitarscribe/docs/Google_Cloud_Personal_2026-11-20.md`；工具是 `guitarscribe/infra/on_demand/{backup_work,prepare_release,bootstrap}.py`。

- 成功備份以最後發布的 `status=complete` manifest、SHA與generation為準；檔案用SHA去重、SQLite走backup API，不直接拷含WAL的DB。先確認分析停止再手動備份。
- 還原一律到**不存在的新目錄**，核對所有SHA／SQLite integrity／邏輯內容。驗證成功不代表獲准覆蓋線上work。若要切換，先保留當前進度並安排停止窗口。不得以初始personal-work.tar.gz復原使用者後續編輯。
- 純程式更新使用 `python3 guitarscribe/infra/on_demand/prepare_release.py --repo <repo> --app-only --out <新的輸出目錄>`。它從已提交 HEAD 清潔建置，只產生 app.tar.gz／manifest.json，完全不讀 work 或 runtime。核對 manifest 的 release_kind=app_only 與 SHA。只替換 app/site，保留舊版可退回；不要發布本機整個 dist/public/listening，裡面可能有私人音訊。前端清潔建置只取 index/assets 及必要導覽。
- 確認 `GUITARSCRIBE_KEEP_SONGS=true`；不可回到會按TTL刪舊歌的版本，也不可設TTL=0（會全部過期）。跨boot中斷分析回收不能重用舊PID發signal。
- 入口以immutable image digest部署並保留revision回退；Cloud Run必須使用h2c/`--use-http2`保留大音檔上傳，不改成默認HTTP/1的32MiB限制。
- 驗證覆蓋登入、歌曲清單、原音訊Range、保存衝突、重開後資料、至少一首正式歌唯讀流程。人工進度用前後hash或資料版本核對；寫入測試只用有所有權marker的臨時fixture，清除自己建立的資料。
- 正式資料不在Git；發布後記錄app commit、image digest、manifest與測試範圍到deployment.json／工作表，不把舊「曾通過」當新版本通過。

## 交接與剩餘未知

回報：檢查時間、入口／VM狀態、版本、備份最近成功證據、是否動過服務、原稿是否保持、真正失敗與下一步。沒有權限／實際帳單／實體裝置的證據就標未知。不要以維護工具正常替代完整CI或音樂品質評估。

Skill本身不是daemon。新session可直接「使用 $guitarscribe-autopilot 檢查雲端狀態」，依本文件與最新工作表續做；無執行中的代理時不聲稱持續開發或巡檢。既有主機備份timer／平台停機是部署本身的自動化，與代理是否在線無關。
