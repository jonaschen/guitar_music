# GuitarScribe 維護與交接入口

這是下一個 session 的起點；最後整理日期：2026-11-23。當下部署值以 `infra/on_demand/deployment.json` 與實際查詢為準。**本輪開發／驗證進行中，尚未宣稱新版已部署。** 收尾會補實際 commit、備份與驗證紀錄。

## 先掌握產品與工作狀態

產品是個人抓歌練習工具：選歌 → 整理前奏／主歌／副歌等大段 → 鎖定一段 → 看低頻、聽原曲、記根音／和弦 → 比較並沿用重複段。使用者已確認此方向可用，平時沒有很多測試時間。預設低頻回聽不加入人工和弦或根音聲音；明確開啟的理論參考聲是另一操作。

- 當前排序及舊清單對照：[總盤點](Backlog_Review_2026-11-23.md)。原137個未勾選條目有逐行索引，不等於137個產品缺口。
- 上一輪已發布功能：[11-21故事](Remaining_Stories_2026-11-21.md)、[11-21發布證據](Cloud_Update_2026-11-21.md)。
- 最新操作：[根音／圖上A–B](Root_Visual_Practice_User_Guide_2026-11-14.md)、[結構整理](Song_Structure_User_Guide_2026-11-17.md)、[鎖定段落與和弦沿用](Section_Chord_Practice_2026-11-17.md)、[調性／組成音工具](Learning_Practice_2026-11-21.md)。
- 本輪操作：[中斷分析恢復與和弦級數](Recovery_and_Degrees_2026-11-23.md)。發布是否完成看本文件版本摘要，操作文件不代替部署證據。
- 不重啟自動主旋律、不強推新模型、不要求重新驗已接受片段。個人使用、原介面介紹；不擴大成公開分享或多帳號。
- 工程驗證不能代替獨立音樂標註、實體手機與實際帳單；剩餘項要分清未完成工程、待外部證據與已停止方向。

## 五分鐘接手

在 Git 根目錄執行，所有路徑除另註外相對根目錄：

```sh
git status --short
git log -6 --oneline
cat guitarscribe/infra/on_demand/deployment.json
python3 skills/guitarscribe-autopilot/scripts/cloud_status.py --repo "$PWD"
```

狀態工具只讀，不開 VM。11-23 本輪首次查核是入口 Ready、匿名401／登入200、VM TERMINATED、can_wake=true，屬正常休息；這是歷史檢查，不保證未來仍相同。工具會查備份清單，但清單存在不等於已驗證可還原。

不要列印 `access.json`、token或完整環境。若缺登入或權限，先記錄哪一步不能查；不要重建資源、重設帳密或拿初始快照覆蓋現況。

工作樹可能有使用者私人素材、舊顧問筆記及 `.tsbuildinfo` 修改。只提交本次檔案；不可 `git add .`、清理全部未追蹤檔或用 reset 覆蓋他人工作。

## 服務與資料位置

| 項目 | 位置／識別 |
| --- | --- |
| 固定入口 | https://guitarscribe-324350766154.asia-east1.run.app |
| GCP | `hanana-491223`／324350766154，asia-east1，asia-east1-b |
| Cloud Run／VM | `guitarscribe`／`guitarscribe-personal`，e2-standard-2，40 GiB持久磁碟 |
| 最新人工稿 | **VM `/srv/guitarscribe/work`**；本機output是獨立舊副本，沒有雙向同步 |
| 現用程式／網頁 | `/srv/guitarscribe/app`、`/srv/guitarscribe/site` |
| 現用版本證據 | `/srv/guitarscribe/app-release-manifest.json`；初始`release-manifest.json`不是現用app版本 |
| runtime | `/srv/guitarscribe/runtime`、`environment`、`protocol.json`；一般app更新保留 |
| 私人桶 | `hanana-491223-guitarscribe-private`；`releases/`程式、`backups/`資料、`control/usage.json`時數帳本 |
| 備份狀態 | `/srv/guitarscribe/maintenance/backup-status.json`，API `/backend/cloud/maintenance` |
| 本機授權檔 | `guitarscribe/output/cloud-control/access.json`及`ssh`；未進Git，不可輸出內容 |
| VM授權／Secret | `/srv/guitarscribe/access.json`／Secret Manager `guitarscribe-access` |

同專案還有其他服務，不能套用全專案刪除／停機。每次會話最多2小時、31天40小時；NT$300是費用目標而非帳單硬上限，磁碟等仍計費。入口休息時使用網頁「啟動工作室」；不要用Console直接開機繞過帳本。新版分析至少需剩30分鐘，本輪重試入口也受同一護欄。

## 維護與故障處置

完整規則：[skill雲端維護](../../skills/guitarscribe-autopilot/references/cloud-operations.md)。基礎架構與備份操作：[個人雲端手冊](Google_Cloud_Personal_2026-11-20.md)、[備份狀態](Cloud_Maintenance_2026-11-21.md)。

VM已運行時可用IAP：

```sh
gcloud compute ssh guitarscribe-personal --project=hanana-491223 --zone=asia-east1-b --tunnel-through-iap
```

應用是 `guitarscribe` **使用者服務** `guitarscribe.service`；不是root的system unit。先 `id -u guitarscribe`，再設對應`XDG_RUNTIME_DIR=/run/user/<uid>`與user bus，由該使用者查`systemctl --user`／journal。系統單元是`guitarscribe-backup.service/.timer`、`guitarscribe-idle.service/.timer`。

| 現象 | 首先核對 | 避免的錯誤處置 |
| --- | --- | --- |
| 401 | 是否尚未登入／憑證可用 | 不視為API壞掉、不關閉認證 |
| stopped且可喚醒 | 正常休息，依網頁啟動 | 不重部署或重新匯歌 |
| preparing持續 | VM狀態、user service、health、磁碟、journal | 不重送多次wake |
| 保存409 | 來源、版本或段落邊界變動；保留瀏覽器草稿 | 不強制覆蓋另一頁新進度 |
| 備份failed／interrupted | 最近成功、timer／journal、空間、active analysis | 不把舊成功manifest當本輪成功 |
| 新YouTube下載拒絕 | 來源機器人驗證，改用有權分析的音檔 | 不反覆換代理／cookie規避 |
| 中斷上傳分析 | failed/cancelled且保留原音檔時按重新分析 | 不是從stage斷點續算；舊歌不會被覆蓋 |
| 測試逾時 | 追蹤request與UI保存狀態、本機RAM／其他建置負載 | 不直接放寬斷言宣稱通過 |

## 資料契約與本輪變更

- jobs metadata 在 `work/jobs/jobs.sqlite3`，每個job的音訊／診斷在`work/jobs/<id>`。人工結構、根音、和弦、學習筆記各有獨立來源指紋與版本檢查，不能拿新分析直接重建它們。
- 重新分析只接受failed/cancelled的本機上傳來源。`POST /api/v1/jobs/<id>/retry`建立新job，從保留原音檔**從頭執行**，保留分析選項、標題；不複製或覆寫人工稿。缺檔與YouTube拒絕不假裝可恢復。
- `retry_of`記來源；`can_retry`是當下能力提示。`job_retries(parent_id PRIMARY KEY, child_id)`將一次重試持久去重：回覆丟失／重複點選返回同一child；child再失敗時，從child明確重試。
- 新表是向後相容的附加schema，不改既有jobs rows。**發布前後不能只要求整個SQLite dump hash相同**：核對既有tables/rows不變，新增表允許且應為空；回退程式不刪表、不還原舊DB。完成過重試後，備份須包含新表和新job音檔。
- task取消前可能尚未進入coroutine，回收由完成callback涵蓋；只有取得semaphore者釋放它。CPU thread無法強殺，重複取消也需等到結束再清來源及釋放容量。
- 上傳大小檢查最多讀limit+1 bytes；舊同步入口先驗大小才建暫存檔，避免超限漏清理。

## 開發與驗證

目前可用Python：`/home/jonas/.cache/guitarscribe-runtime/bin/python`。本機`guitarscribe/.venv`與`.tooling-venv`未必有FastAPI；不要看到venv便當完整runtime。其他主機依backend `pyproject.toml`與CI安裝隔離環境；不要把登入憑證／runtime私檔打包成skill。

```sh
# 在 guitarscribe/backend
/home/jonas/.cache/guitarscribe-runtime/bin/python -m pytest tests/test_jobs.py tests/test_job_retry.py tests/test_analysis_worker.py tests/test_api.py -q
# 完整後端
/home/jonas/.cache/guitarscribe-runtime/bin/python -m pytest tests -q

# 在 guitarscribe/frontend
npm ci
npm run build
GUITARSCRIBE_TEST_PYTHON=/home/jonas/.cache/guitarscribe-runtime/bin/python npx playwright test --config playwright.recovery.config.ts
GUITARSCRIBE_TEST_PYTHON=/home/jonas/.cache/guitarscribe-runtime/bin/python npx playwright test --config playwright.ci.config.ts
npx playwright test --config playwright.webkit.config.ts
GUITARSCRIBE_TEST_PYTHON=/home/jonas/.cache/guitarscribe-runtime/bin/python GUITARSCRIBE_TEST_BROWSER=webkit npx playwright test --config playwright.learning.config.ts

# 在 guitarscribe/infra/on_demand，使用裝好 requirements.txt 的隔離環境
python -m pytest -q
```

CI `.github/workflows/ci.yml`是完整環境的依據。缺Hypercorn／google-api-core時本機infra會skip四項，不能宣稱全通過；遠端CI須補齊。建置／完整後端與長時間瀏覽器測試不要同時擠在這台8 GiB主機上，以免把負載造成的延遲誤判；保留失敗trace而非只留下最後成功。

長時間測試是opt-in，使用合成音及臨時SQLite，從不讀正式歌；fixture啟動時複製dist保持測試版本穩定：

```sh
GUITARSCRIBE_TEST_PYTHON=/home/jonas/.cache/guitarscribe-runtime/bin/python GUITARSCRIBE_SOAK_MS=7200000 npx playwright test --config playwright.soak.config.ts --reporter=line,json
```

此測試會反覆編輯、保存、原曲播放、pagehide暫停與重開；不能據此宣稱所有真實歌曲、手機Safari或長期記憶體無洩漏。實體手機與音樂品質證據分開。

## 發布、備份與回退

逐步命令與可重用更新工具見 [程式發布操作手冊](APP_RELEASE_RUNBOOK.md)。`apply_app_release.py` 已覆蓋身份／SHA／tar檢查、只交換程式、資料核對與失敗回退；`release_workspace.py` 是只讀證據工具，拒絕原稿變更並只接受明確允許的空retry表。工具與測試在Git內，不依賴output裡的一次性腳本。

1. 確認當前commit／工作樹，跑適當測試並確認遠端CI。僅提交所屬檔案；程式與文件可分段提交。
2. 使用`prepare_release.py --app-only`從**已提交HEAD**清潔建置，產生新的輸出目錄；manifest必須為`release_kind=app_only`，只有app包，核對commit與SHA。不搬本機work、不發布整個public/listening。
3. 透過正常入口喚醒（若已有人使用，先核對時段）；IAP查看最近activity、queued/running分析、結構分析、root-candidate lock與backup service。使用者活動／分析變動便延後中斷，繼續本機工作。
4. 更新前做完整備份，等待`status=complete`的manifest，保存object名／generation／SHA。舊manifest清單不取代此步。還原演練只到不存在的新目錄，核對SHA、SQLite integrity與資料；不覆蓋線上work。
5. app包上傳私人桶新release路徑，再於VM驗SHA與tar路徑（僅app/site、不得symlink／絕對／`..`）。stage到新目錄，保留舊app/site。切換前再次確認activity與分析未改變。
6. 暫停backup timer，停止應用user service，僅交換app/site，啟動服務。KEEP_SONGS=true、既有runtime／environment／protocol／work保留；30秒健康檢查失敗便退回舊程式。必須恢復backup timer。
7. 驗證匿名401／登入成功、歌曲清單、原音訊Range、至少一首正式歌唯讀、版本／草稿保護。資料比較以既有table rows與檔案為準，記錄預期schema新增；寫入只用所有權marker的臨時fixture。
8. 更新`app-release-manifest.json`與repo `deployment.json`，記錄實際部署app commit、包SHA、前版保留路徑、CI和備份。正式工作不能被本機快照回灌。
9. 完成驗證／完整備份後，確認沒有使用者活動或分析，再由正常入口停止自行喚醒的VM，核對帳本結算。不要刪磁碟來省錢。

**回退**：核對當下工作安全窗口，停止user service，把目前app/site移到保留目錄，再把本次release的`previous/app`、`previous/site`移回並啟動；只退程式，保留work和新schema。核對health、版本、原稿與backup timer後更新deployment紀錄。不可用初始personal-work.tar.gz回復人工進度。

上面是操作順序，不是允許無條件停機。若有使用者正在操作、分析或備份，先保護現況。完整資源名稱、帳本／CSRF入口與service細節見skill維護參考。

## 接手完成的判準

下一個 session 應能回答：線上是哪個app版本、服務是正常休息還是故障、最近可驗證備份是哪份、雲端人工稿在哪裡、哪些測試實跑／未跑、哪些功能尚未完成、現在下一個可執行項目是什麼。

當次收尾需更新本文件的版本摘要、總盤點R1–R8、Next_Decision／Autonomous_Development最新入口與驗證JSON；不能只留下聊天說「完成」。skill本身不是背景排程器，session結束後不會自行工作。

## 換電腦或 session 的必要條件

Git內保存程式、故事、手冊與 `skills/guitarscribe-autopilot`；目前本機的skill安裝是指向它的連結。接手者需要能讀這個repo，並在可執行工具的環境讀取SKILL.md。只有相同帳號登入並不表示每個客戶端都已安裝本機skill或擁有這台電腦的檔案。

唯讀雲端檢查需要Python 3與已授權的gcloud身分；完整開發依CI準備Node 20、Python與依賴；實際部署另需GCP/IAP權限和既有授權檔。憑證走安全管道／Secret Manager，不放skill、Git或聊天。缺憑證時仍可讀文件與做本機工程，明列尚未查證的雲端部分，不能自行重設或重建服務。
