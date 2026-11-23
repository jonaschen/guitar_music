# GuitarScribe 維護與交接入口

這是下一個 session 的起點；最後整理日期：2026-11-23。當下部署值以 `infra/on_demand/deployment.json` 與實際查詢為準。**新版v9已部署，備份還原與停機結算完成；兩小時本機持續操作測試已通過（412次循環）。** 完整證據見 [11-23發布紀錄](Cloud_Update_2026-11-23.md) 及 [驗證JSON](evaluation/cloud-update-2026-11-23.json)。

## 現用版本摘要

- app：`1de9ee21255a560138b250fa0ec97aff81e444fc`，`releases/2026-11-23-v9`；正式程式完整CI成功。文件提交可能較新，不能把文件HEAD誤當線上app commit。
- 前版：v5／`f269caa`，程式與manifest保留在VM `releases/2026-11-23-v9/previous`。
- 25首歌、6份既有DB及144個原檔保持；唯一新增schema為空retry表。280個安裝檔案與包SHA一致。
- 最近實證備份：11-23 21:22:29台北完成、150檔，manifest `backups/manifests/20261123T132105Z-47337d37f482436a8cce20bcff7d349a.json`；generation／SHA見發布紀錄。已還原到新目錄並逐表逐檔核對，未覆蓋正式work。
- 11-23 21:26:49查核：VM休息、可喚醒，帳本使用8520秒／剩135480秒；為當次歷史狀態，不是費用帳單。
- 長測：2小時／412次編輯、保存、原曲回聽與重開通過；測試固定bcd04c1網頁版本，後加級數／Capo另有CI與真API證據。第一輪5秒保存逾時、最終寫入成功的證據與原因未知一併保留，見 [持續操作紀錄](evaluation/practice-soak-2026-11-23.json)。
- 本輪CI：後端1483＋3 skip、infra116、前端358＋7 skip、WebKit20＋學習5＋真API恢復／Capo4；跳過原因、長測界線與未知見發布紀錄。

最後交接只讀查核為11-23 22:07:17台北：仍正常休息、可喚醒、帳本數字未變。本輪R1–R9已收尾；後續真實工程與外部證據見文末，並非所有歷史規劃都已完成。

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

本輪查詢其他Codex session的工具連線失敗，因此沒有宣稱已通知 `programmer-session`。本輪程式與文件均以明確檔案清單提交；後續若恢復並行協作，先協調檔案所有權，部署仍由單一session負責。

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

## 日常維護與儲存基準

每次接手先做只讀狀態查核；每次發布前後做備份與版本／人工稿核對；需要檢查容量或帳務時再讀相應資料，不為例行查核開啟VM。這是接手流程，不是已設定的代理排程。

11-23 21:48台北，私人桶backups共1,282,941,367 bytes，releases共4,272,649,990 bytes；正式驗證期間VM可用31,347,773,440 bytes、disk_low=false。這是一次基準，不是容量承諾。狀態API低於3 GiB會標記disk_low；先查新增來源、模型／包、備份暫存及未完成還原，保留使用者稿和可用回退證據。

```sh
gcloud storage du --summarize \
  gs://hanana-491223-guitarscribe-private/backups/ \
  gs://hanana-491223-guitarscribe-private/releases/ \
  --project=hanana-491223
```

上述命令只列儲存量，不讀音訊內容、不啟動VM。備份依SHA去重，SQLite版本仍會增加新blob；目前沒有新增自動刪除政策。容量持續增加時先提出具體保留範圍並保存可還原證據，不直接刪除舊備份／初始runtime或用通配符清空output。

## 實際費用的查核界線

11-23已只讀確認專案啟用計費並連結帳務帳號；列出本專案可存取的BigQuery datasets沒有回傳任何資料集，因此沒有取得可查詢的billing export。這不代表帳號其他專案沒有匯出，也不代表本月費用為零。未為查核開啟服務、建立匯出或改預算。

接手可先從Cloud Billing既有報表按專案、服務／SKU及可用資源欄位核對，必須把同專案其他服務區分開。若只有整個專案總額，標明它不是GuitarScribe單獨費用；沒有明細就保留未知。`cloud_status.py` 的運行帳本不是帳單，不能乘一個假定價格就回報實際台幣花費。未來若需要設billing export或調整資源，再依使用者當時授權、成本與資料範圍決定，不由日常狀態查詢自動設定。

## 資料契約與本輪變更

- jobs metadata 在 `work/jobs/jobs.sqlite3`，每個job的音訊／診斷在`work/jobs/<id>`。人工結構、根音、和弦、學習筆記各有獨立來源指紋與版本檢查，不能拿新分析直接重建它們。
- 重新分析只接受failed/cancelled的本機上傳來源。`POST /api/v1/jobs/<id>/retry`建立新job，從保留原音檔**從頭執行**，保留分析選項、標題；不複製或覆寫人工稿。缺檔與YouTube拒絕不假裝可恢復。
- `retry_of`記來源；`can_retry`是當下能力提示。`job_retries(parent_id PRIMARY KEY, child_id)`將一次重試持久去重：回覆丟失／重複點選返回同一child；child再失敗時，從child明確重試。
- 新表是向後相容的附加schema，不改既有jobs rows。**發布前後不能只要求整個SQLite dump hash相同**：核對既有tables/rows不變，新增表允許且應為空；回退程式不刪表、不還原舊DB。完成過重試後，備份須包含新表和新job音檔。
- task取消前可能尚未進入coroutine，回收由完成callback涵蓋；只有取得semaphore者釋放它。CPU thread無法強殺，重複取消也需等到結束再清來源及釋放容量。
- 上傳大小檢查最多讀limit+1 bytes；舊同步入口先驗大小才建暫存檔，避免超限漏清理。
- 相對級數只讀個人主音／調式假設和已填和弦，不寫資料、不自動判斷調性。小調採同主音大音階參照，局部假設不延伸到其範圍外；來源／版本不符時停止換算。
- Capo建議API新增選填 `preferred_fret`，回傳完整覆蓋數、換把／把位成本與逐和弦 `voicing_plan`。非標準調弦拒絕；不完整root-note備用品不算完整和弦。計算移至worker，原稿只讀；明確採用後先核對所選指型仍存在，再用既有revision／Undo流程更新編曲，原發聲和弦與獨立練習稿保留。這是工程啟發式，不是人體工學或音樂真值。

## 開發與驗證

目前可用Python：`/home/jonas/.cache/guitarscribe-runtime/bin/python`。本機`guitarscribe/.venv`與`.tooling-venv`未必有FastAPI；不要看到venv便當完整runtime。其他主機依backend `pyproject.toml`與CI安裝隔離環境；不要把登入憑證／runtime私檔打包成skill。

本輪環境核對：本機Python 3.12.3／Node 24.14.0；CI後端Docker及瀏覽器fixture是Python 3.11、Node 20，infra job是Python 3.12。雲端app包目標為Ubuntu 24.04 x86_64／CPython 3.12，主runtime在 `/srv/guitarscribe/runtime/main`、結構模型在獨立 `runtime/structure`；模型／原生插件清單由既有protocol與初始安裝紀錄管理。CI不是雲端的完整映像；一般改版只更新app，不順便升級Python、模型或原生依賴。

本輪5個後端warnings主要來自TestClient／audio解碼／pkg_resources的依賴棄用通知；另有pytest-asyncio loop scope提示。沒有把warning改成skip或放寬斷言。未來升級依賴時以相同音訊／事件及API契約重驗，不只以pip安裝成功判斷相容。

### 找到要修的程式

下表路徑分別相對 `guitarscribe/backend/app`、`guitarscribe/frontend/src`；配套測試在backend/tests與frontend/e2e，先用同名模組／功能搜尋。

| 功能 | 後端入口 | 前端入口 |
| --- | --- | --- |
| 上傳、進度、取消／重試 | `api.py`、`services/jobs.py`、`analyzers/worker.py`、`core/pipeline.py` | `App.tsx`、`AnalysisProgress.tsx` |
| 歌曲結構與候選工作 | `song_structure_api.py`、`services/song_structure.py`、`services/structure_analysis_jobs.py` | `SongStructurePage.tsx`、`StructureAnalysisPanel.tsx`、`useSongStructure.ts` |
| 根音／低頻與沿用 | `root_practice_api.py`、`services/root_practice.py` | `RootPractice.tsx`、`RootSpectrogram.tsx`、`useRootPractice.ts` |
| 鎖定段落、完整和弦及沿用 | `chord_practice_api.py`、`services/chord_practice.py` | `SectionChordPractice.tsx`、`useChordPractice.ts`、`ChordReusePanel.tsx` |
| 主音／調式、級數與組成音 | `learning_practice_api.py`、`services/learning_practice.py` | `TonalHypothesisPanel.tsx`、`ChordDegreeView.tsx`、`chordTheory.ts` |
| Capo、轉調及指型 | `services/capo.py`及`api.py`相關route | `CapoAdvice.tsx`、`ChordFingerings.tsx`、`App.tsx`的retuneScore |
| 個人雲端、備份、發布 | `guitarscribe/infra/on_demand`（相對repo） | 同目錄的gateway／toolbar；不從舊ngrok腳本部署 |

`root-practice.sqlite3`、`song-structure.sqlite3`、`chord-practice.sqlite3`、`learning-practice.sqlite3`各有獨立版本及來源契約；更改某層不應直接改另一層的資料。原Score revision與這些練習稿也不能互相當替代來源。

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
9. 完成驗證／完整備份後，確認沒有使用者活動或分析，才經IAP在自行喚醒的VM執行 `sudo systemctl poweroff`，再由 `/cloud/status` 核對停止及帳本結算。現用入口只有喚醒／狀態，沒有 `/cloud/stop` API；一般使用者關閉頁面後由閒置規則休息。不要刪磁碟來省錢。

**回退**：核對當下工作安全窗口，停止user service，把目前app/site移到保留目錄，再把本次release的`previous/app`、`previous/site`移回並啟動；只退程式，保留work和新schema。核對health、版本、原稿與backup timer後更新deployment紀錄。不可用初始personal-work.tar.gz回復人工進度。

上面是操作順序，不是允許無條件停機。若有使用者正在操作、分析或備份，先保護現況。完整資源名稱、帳本／CSRF入口與service細節見skill維護參考。

## 接手完成的判準

下一個 session 應能回答：線上是哪個app版本、服務是正常休息還是故障、最近可驗證備份是哪份、雲端人工稿在哪裡、哪些測試實跑／未跑、哪些功能尚未完成、現在下一個可執行項目是什麼。

當次收尾需更新本文件的版本摘要、總盤點R1–R9、Next_Decision／Autonomous_Development最新入口與驗證JSON；不能只留下聊天說「完成」。skill本身不是背景排程器，session結束後不會自行工作。

## 尚未完成的工程與後續切入點

這些是舊規劃的真實剩餘項，不因本輪R1–R9交付而自動完成，也不是都卡在人耳。逐項原始索引及處置依據見 [137條盤點](evaluation/backlog-inventory-2026-11-23.json)。

| 優先 | 後續項目 | 開始前固定的契約／首批測試 |
| --- | --- | --- |
| 1 | 完整stage快取與拍點／和弦單層重算 | 來源音訊SHA、裁切、engine/model版本、參數共同決定cache key；缺檔／損毀／參數變更必須miss。取消不得留下可用但未完成的cache。新候選存新分支，不覆寫原分析或人工稿；不重新啟用旋律。 |
| 2 | 指型套用範圍 | 明示單次／所選段／相同和弦範圍及影響數；先測重複名稱但不同低音、手動指型、來源變更、Undo／重開。現有單次及全曲最佳化不等於完整範圍選擇。 |
| 3 | 全層TempoMap與有限漂移 | 先明定單一版本／秒數契約，再測pickup、不完整小節、局部anchors、短和弦、跨變速、裁切與各匯出。現用手動拍格／受保護恢復保留，不一次替換全部時間層。 |
| 4 | 通用錯誤標註／資源baseline | 標記錯誤類別、錄音範圍、原始版本與人工意圖；標記不是核准參考。記CPU/RAM與各stage耗時需固定環境，不能由這次CI秒數推估真歌分析ETA。 |
| 5 | 次要閱譜擴充 | 全曲虛擬化、完整Nashville格式、錄音驅動刷奏型等仍未全做；目前已可用的選段級數與手動模板保留。 |

Q1代表性歌曲的獨立標註、Q2實體手機Safari／真實網路、實際月帳單屬外部證據；與上述工程分開。旋律、多人公開分享、ASR、演奏評分與PDF擴充維持停止／未納入範圍。

接手提示可直接使用：「使用 `$guitarscribe-autopilot`，先讀 `guitarscribe/docs/MAINTENANCE_HANDOFF.md`，核對Git、雲端版本與備份，再從最新故事盤點接續。保留雲端人工稿，工程自行驗證，不要求我先完成測試。」

## 換電腦或 session 的必要條件

Git內保存程式、故事、手冊與 `skills/guitarscribe-autopilot`；根目錄 `AGENTS.md` 也會引導支援該格式的開發代理先讀本文件。目前本機的skill安裝是指向它的連結。接手者需要能讀這個repo，並在可執行工具的環境讀取SKILL.md。只有相同帳號登入並不表示每個客戶端都已安裝本機skill或擁有這台電腦的檔案。

唯讀雲端檢查需要Python 3與已授權的gcloud身分；完整開發依CI準備Node 20、Python與依賴；實際部署另需GCP/IAP權限和既有授權檔。憑證走安全管道／Secret Manager，不放skill、Git或聊天。缺憑證時仍可讀文件與做本機工程，明列尚未查證的雲端部分，不能自行重設或重建服務。
