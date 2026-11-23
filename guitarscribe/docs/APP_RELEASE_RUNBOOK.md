# 個人雲端程式發布與回退

由 [維護交接](MAINTENANCE_HANDOFF.md) 進入。這裡處理既有 VM 的 app/site 更新，不改 runtime、帳號、Cloud Run 或人工稿。初始遷移、整個 work 還原不適用本流程。

## 先在本機準備

1. 核對 `deployment.json`、工作樹及遠端 CI。正式資料以 VM 為準；不要提交私人 output、音訊或 access.json。
2. 決定新的 release 名稱，例如 `2026-11-23-v7`；每次使用新名稱，不能覆寫舊包。從已提交 HEAD 建置：

```sh
python3 guitarscribe/infra/on_demand/prepare_release.py \
  --repo "$PWD" --app-only \
  --out "$PWD/guitarscribe/output/cloud-release-NEW"
```

3. 查看產生的 manifest，只應包含 `app.tar.gz`；記錄完整 commit、SHA256 與 bytes。工具不讀 work/runtime，網頁只取乾淨 Git 建置的 index/assets，不包含本機試聽素材。
4. 將該 manifest 與 app.tar.gz 存入私人桶的新 `releases/<名稱>/`。維護工具可直接由同 commit 的 repo 透過 IAP SCP 上傳，不需要把網站密碼放 shell 命令列。

```sh
gcloud storage cp guitarscribe/output/cloud-release-NEW/app.tar.gz \
  guitarscribe/output/cloud-release-NEW/manifest.json \
  gs://hanana-491223-guitarscribe-private/releases/NEW/ \
  --project=hanana-491223
```

`NEW`、完整 commit 與 SHA 是要按本次 manifest 填入的值，不能照抄某次歷史值。

## 喚醒、備份與套用

從已登入網頁啟動工作室，或依 skill 的 Origin／短效 CSRF／Basic 認證流程喚醒。不要直接 Compute start。記錄是否由本次維護啟動；既有人在使用時不搶先更新。

IAP SSH/SCP 都指定 `--project=hanana-491223 --zone=asia-east1-b --tunnel-through-iap`。本機已有專用金鑰時加 `--ssh-key-file=guitarscribe/output/cloud-control/ssh`，不要為接手重設網站密碼。先在 VM 建立本次專用暫存目錄，再傳檔：

```sh
gcloud compute ssh guitarscribe-personal --project=hanana-491223 \
  --zone=asia-east1-b --tunnel-through-iap \
  --command='mkdir -p /tmp/guitarscribe-NEW'

gcloud compute scp --project=hanana-491223 --zone=asia-east1-b --tunnel-through-iap \
  guitarscribe/output/cloud-release-NEW/app.tar.gz \
  guitarscribe/output/cloud-release-NEW/manifest.json \
  guitarscribe/infra/on_demand/apply_app_release.py \
  guitarscribe/infra/on_demand/release_workspace.py \
  guitarscribe/infra/on_demand/host_activity.py \
  guitarscribe-personal:/tmp/guitarscribe-NEW/
```

在 VM 核對原版 `app-release-manifest.json` 的 commit、使用活動、沒有 queued/running 分析及 root-candidate lock，然後執行：

```sh
sudo systemctl start guitarscribe-backup.service
sudo systemctl show guitarscribe-backup.service -p ActiveState -p Result
sudo journalctl -u guitarscribe-backup.service -n 20 --no-pager
```

必須得到本輪成功 manifest；記錄 manifest 名稱、SHA、GCS generation。更新工具要求最近20分鐘內完成的備份、備份快照晚於最後活動、至少60秒無活動、沒有分析或備份正在跑；這些檢查不代表能辨識所有瀏覽器未保存草稿。持續 heartbeat 或使用者操作時先延後。

```sh
sudo python3 /tmp/guitarscribe-NEW/apply_app_release.py \
  --archive /tmp/guitarscribe-NEW/app.tar.gz \
  --manifest /tmp/guitarscribe-NEW/manifest.json \
  --release NEW \
  --expected-current-commit OLD_FULL_COMMIT \
  --commit NEW_FULL_COMMIT \
  --sha256 PACKAGE_SHA256 \
  --allow-retry-schema
```

最後的旗標只適用11-23首次增加 `jobs/jobs.sqlite3:job_retries` 空表。它不放行其他新表、索引、trigger或任何既有資料變更。未來不需該schema時省略；若新版本真的需要其他 migration，先寫測試與遷移策略，不能放寬成忽略資料差異。

工具會驗SHA／tar路徑及完整版本，stage新檔、保留舊app/site、暫停原本正在跑的backup timer、停止應用、核對work、交換程式並健康檢查，再比較原始檔案及每個既有資料表的結構／rows。成功寫入 `app-release-manifest.json` 與 `releases/NEW/verification.json`；失敗退回程式並保留work，最後恢復原本timer狀態。

若在stage後被活動護欄拒絕，服務仍保持原狀，release目錄會留下以供查核；下一次選新release名稱或先明確確認該目錄只有本輪未套用stage。不要刪掉有previous/的發布目錄。

## 驗證、備份與收尾

- 匿名401、本人登入、歌曲清單數量、至少一首原稿唯讀、音訊Range206與原介面低頻圖。前端載入的asset必須是新包內的檔名／內容。
- 正式歌不寫入。需要驗證保存時用 `verify_cloud_fixture.py` 的所有權marker流程；完成後清除自己建立的fixture，再比較原資料。新功能仍須先通過本機真API瀏覽器測試與CI。
- 核對 `KEEP_SONGS=true`、backup timer運作、主機沒有新分析。再做完整備份並等待成功。若要證明可還原，用 `backup_work.py restore` 到新且不存在的目錄，核對manifest SHA與SQLite；不要覆蓋線上work。
- 更新 `deployment.json` 的 app_release/app_commit/app_sha256/previous_app_release，以及交接文件和驗證JSON。保存CI連結、備份object/generation/SHA、原資料前後證據、失敗與界線。
- 若VM是本次維護自行喚醒，確認沒有人接續操作／沒有分析／備份後，經IAP執行 `sudo systemctl poweroff`，再查 `/cloud/status` 核對停止與帳本結算。現用入口沒有 `/cloud/stop` API。若狀態改變，先保留工作，不能直接停機。

## 手動回退／中途中斷

一般健康或資料檢查失敗，工具已自動退回程式。若程序被kill、主機斷電，或使用後才發現問題：

1. 先讀當次 `releases/NEW/{verification.json,workspace-before.json,workspace-after.json}`、`previous/`、`failed-*`與現用manifest。中斷可能沒有最後檔案；不要只相信manifest就假設交換完成。
2. 等安全窗口並備份目前work。取得 `id -u guitarscribe`，以該使用者及對應 XDG_RUNTIME_DIR/user bus 停止 `guitarscribe.service`；備份timer先停止並記原狀態。
3. 把現用app/site移到**新的保留路徑**。只把確認屬於前版的 `releases/NEW/previous/app` 與 `previous/site` 移回；不從個人初始快照恢復work。
4. 若存在previous/app-release-manifest.json，一併恢復版本描述。重啟user service，確認health、實際程式hash、歌曲清單及原稿；恢復原timer狀態。若回退也不能啟動，保留所有檔案與日誌，檢查runtime/env，不連續換包。
5. 將回退後版本寫回deployment與交接。新 `job_retries` 表保留；已提交的新工作及人工稿也保留。回退的是程式，不是使用者進度。

工具不涵蓋磁碟損毀、runtime版本升級或破壞性schema migration；這些需另訂恢復計畫，不能直接套用app-only步驟。

## 備份還原演練的具體命令

以下在VM執行；先由本輪 `backup-status.json` 的 `last_success` 取得manifest及SHA，再從GCS metadata核對generation。`MANIFEST`、`SHA256`、`NEW`必須換成剛查證的值。目標目錄不能事先建立；腳本會拒絕覆寫現有目錄。

```sh
sudo /srv/guitarscribe/runtime/main/bin/python \
  /srv/guitarscribe/app/backend/backup_work.py restore \
  --bucket hanana-491223-guitarscribe-private \
  --manifest MANIFEST --manifest-sha256 SHA256 \
  --target /srv/guitarscribe/restored-NEW

sudo python3 /srv/guitarscribe/app/backend/release_workspace.py \
  --work /srv/guitarscribe/restored-NEW \
  --out /srv/guitarscribe/releases/NEW/restored-workspace.json \
  --compare /srv/guitarscribe/releases/NEW/workspace-final.json
```

`workspace-final.json`須在備份前的無寫入窗口以同一snapshot工具產生；只有相同資料版本才能逐表逐檔相等。備份之後又有使用者保存時，不能把差異當毀損，也不能覆蓋新稿來讓比對通過。restore本身已檢查每個object的generation、大小、SHA／MD5與SQLite integrity／邏輯hash；第二次比對用來證明與已記錄的人工稿版本一致。

保存本輪結果後，只清除這次建立且核對過的還原目錄；不要廣泛清理 `restored-*`、`releases/` 或備份桶。線上work復原是另一個需要先保存現況、明確選擇資料版本的維護工作，不能因演練成功就自動切換。
