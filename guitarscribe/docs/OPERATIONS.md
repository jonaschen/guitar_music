# GuitarScribe operations guide

朋友直接使用維護者提供的 HTTPS 網址與邀請帳密，不需要安裝環境，見 [中文入門指南](../../README.md)。以下先說明 2026-10-30 已運行的受邀網頁試用；舊 Docker 章節保留供開發參考。

## 目前的受邀網頁試用（2026-10-30）

- `guitarscribe-friends-web`：systemd 使用者暫時服務，既有 Python 環境執行 `app.web:create_app`，只監聽 `127.0.0.1:5273`。
- `guitarscribe-friends-tunnel`：使用既有 ngrok 設定建立 HTTPS 入口；網址見本機 `output/web-preview/deployment.json`。首次訪問可能顯示 ngrok 確認頁，再進入邀請登入。
- 整個網站與 `/backend` API 皆需邀請帳密。`output/web-preview/access.json` 只有維護者可讀，不能提交到 Git；所有受邀者仍共用同一資料空間，沒有逐人隔離。
- `output/web-preview/site` 放 production `index.html` 與 `assets/`，另明確加入本輪受邀驗收的 `review-2026-10-31/`（兩組40秒片段、對照頁與對應修訂連結）。全部仍經邀請保護，不掛載開發用 listening 歷史音檔或本機文件。請勿將整個 `frontend/public` 複製對外。
- 分析與修訂在 `output/web-preview/work`，與開發用 `output/work` 分離。`GUITARSCRIBE_WORK_DIR` 必須在啟動前設好。
- 使用既有 Chordino／Beat This，旋律關閉；同時分析一首，提交限制每小時 20 次。不是無限制多人服務。

```bash
systemctl --user status guitarscribe-friends-web guitarscribe-friends-tunnel
journalctl --user -u guitarscribe-friends-web -n 60 --no-pager
# 維護前先確認沒有分析工作；停止對外入口與後端
systemctl --user stop guitarscribe-friends-tunnel guitarscribe-friends-web
# 啟動仍存在的暫時服務
systemctl --user start guitarscribe-friends-web guitarscribe-friends-tunnel
```

暫時服務不依附開發 shell，但**沒有設定開機自動啟動**；主機關機、休眠或斷線便無法使用。重開機後須重建服務，不能保證上述 `start` 仍有效。目前完整啟動參數可用 `systemctl --user cat guitarscribe-friends-web guitarscribe-friends-tunnel` 查看；不要輸出或分享 ngrok 帳戶 token。後續常駐部署需另行完成。

備份前停止 web 服務，再複製整個 `output/web-preview/work`；邀請檔另以受限權限備份。不要將運行中的 SQLite 檔直接複製當作一致備份。修改邀請檔後需重啟 web 服務，舊瀏覽器快取帳密也需更新。

`compose.web.yml` 是後續容器部署配置；`compose.trial.yml` 只供維護者本機開發試跑。兩者使用獨立 named volumes，不能套用下方舊 Compose 的 `./output` 備份路徑。目前 Docker build／設定檢查通過，但**尚未完成容器端到端啟動與分析驗證**；線上試用使用的是上列既有 Python 環境。

For the current non-Docker local installation, use the startup instructions in
[the Codex closeout guide](Closeout_2026-10-27.md). The Compose commands below
apply only to a Docker deployment; `docker compose stop backend` does not stop
a backend launched with `run_local_preview.sh`. For that local installation,
stop the running backend in its own terminal (Ctrl+C), confirm it has exited,
then copy the data directory and restart with the same launcher. Do not copy
a live SQLite database as if it were a consistent stopped-service backup.

GuitarScribe is designed for a single trusted host running Docker Compose. The
analysis worker is intentionally limited to one concurrent job by default;
long audio and optional vocal separation can use substantial CPU, RAM, and
disk.

## YouTube 下載環境（2026-10-30 修正）

目前非 Docker 服務應在**同一個 Python 環境**安裝 `yt-dlp[default]>=2026.10.26`；這包含 EJS 支援。伺服器 PATH 需有 Node 22 以上，程式會明確傳入 `--js-runtimes node`。依據 [yt-dlp 官方 EJS 說明](https://github.com/yt-dlp/yt-dlp/wiki/EJS)，只安裝 yt-dlp 或只有未啟用的 Node 並不足夠。這些是伺服器依賴，朋友手機不用安裝。

下載器預設優先選用執行中 Python 同目錄的 `yt-dlp`，找不到才使用 PATH；`GUITARSCRIBE_YTDLP_BINARY` 指定的自訂路徑仍優先。若環境內已安裝新版卻仍錯誤，不要只檢查互動 shell 的 `yt-dlp --version`，須確認服務實際選用路徑與 JS runtime。可用 `GUITARSCRIBE_YOUTUBE_JS_RUNTIME=node:/absolute/path/to/node` 指定絕對路徑；目前 systemd 試用服務以暫時 drop-in 指向 `/home/jonas/.nvm/versions/node/v24.14.0/bin/node`，重建服務時也要保留此設定。互動 shell 的 nvm 設定不會自動傳給背景服務。

本次發現既有主機 PATH 指向 `~/.local/bin/yt-dlp` 2026.08.19，且未啟用 JS 支援；同一影片的長／短／手機分享網址均在來源下載失敗。背景服務另讀到系統 Node 18，與互動 shell 的 Node 24 不同；已改用分析環境中的 2026.10.26、EJS 0.8.0 並指定 Node 24.14.0，無需登入 cookies。舊失敗 job 保留，不改寫成功；修正驗證使用新 job。

## 拍格恢復啟用（2026-11-02）

使用者通過兩段 click 跟拍後，受邀網站及本機預覽已明確啟用 `fixed-dbn-recovery-v1`；程式庫預設仍關閉。只恢復通過結構／密度／原連續拍點與重拍保護的新分析，原有有效拍格保持，舊 job／修訂不改寫。驗收與驗證見 [紀錄](Guarded_Timing_Recovery_2026-11-02.md#已驗收與正式啟用)。

目前的 runtime drop-in：

```ini
# /run/user/1000/systemd/user/guitarscribe-friends-web.service.d/beat-recovery.conf
[Service]
Environment="GUITARSCRIBE_BEAT_RECOVERY_ENABLED=true"
Environment="PYTHONPATH=/home/jonas/.cache/guitarscribe-beat-dbn/python:/home/jonas/.cache/guitarscribe-chordino-diagnostic/python"
```

`guitarscribe-preview-api.service.d/beat-recovery.conf` 同樣設定開關，`PYTHONPATH` 只需加入 DBN 隔離目錄；`run_local_preview.sh` 會保留它並補上 backend 與 Chordino 路徑。這些 `/run` 設定不跨重開機保留，重建暫時服務須重建 drop-in。不要直接改 transient unit 本體，也不要在有分析進行時重啟。

本機依賴檢查：Beat This 1.1.0、madmom 0.17.dev0（既有固定 source build，見 [DBN 依賴](Downbeat_Rhythm_2026-10-31.md)）、Chordino 可載入；沒有新的套件安裝。恢復開啟但解碼依賴失效時，仍完成原有時間表和弦分析，原因保存在 `timing-recovery.json`。

回退：將 drop-in 中恢復開關設為 `false`，確認工作已完成，再 `systemctl --user daemon-reload` 及重啟對應 API 服務。已完成的工作譜不因回退而變更。GitHub／Docker 安裝不會自動取得上述本機隔離依賴或設定，不能把本次主機啟用當成所有安裝皆已啟用。

## 11-04 的可選主模型恢復（尚未啟用）

**11-05更正：使用者拒絕後來連續性候選（半速、第一拍錯）。目前原碼policy改為`fixed-main-dbn-v2`，產品不再嘗試全曲主速度限制；以下連續性描述為11-04歷史。正式服務仍為small0，未啟用此可選主模型。**

程式新增 `GUITARSCRIBE_BEAT_ENGINE=beat_this_main_dbn`；應與既有 `GUITARSCRIBE_BEAT_RECOVERY_ENABLED=true` 一起使用，保留原small0及已接受固定DBN恢復。只有原流程拒絕才載入final0，再按固定全曲工程閘門決定使用原DBN或主速度連續性候選。依賴仍是本機既有Beat This及隔離madmom；首次載入final0會下載官方權重。本機已下載，權重與政策見 [結果](Timing_Batch_Result_2026-11-04.md)。

**本輪只部署程式與三組試聽，沒有修改上述正式引擎設定。** 新模型及連續性機制尚待必要人耳驗收；不得單憑工程通過數啟用。切換只影響新分析，舊job與修訂保持。需要退回時設回 `beat_this_small`，保留原恢復開關；先確認無排隊／進行中工作再重啟服務。runtime保存完整拒絕與恢復報告；可選恢復依賴故障仍沿用時間表路徑。

試聽發佈目錄：`output/web-preview/site/timing-batch-review-2026-11-04/`，只有本輪公開給受邀者的index、packet及11個40秒WAV，未複製整個public或本機診斷目錄。原碼的`frontend/scripts/check-timing-batch-review.mjs`可檢查邀請保護、手機寬度、實播、切換位置與候選原曲播放；帳密只從本機檔案讀入，不輸出。

## Start and check

```bash
cp .env.example .env
make build
docker compose up -d backend frontend
docker compose ps
curl --fail http://localhost:8000/health
```

The web app is served on port 5173 and the API on port 8000. Run
`docker compose logs -f backend` to follow a job through its stages. A failed
or cancelled job exposes its message through `GET /api/v1/jobs/{job_id}`.

## Persistent data and backup

The Compose configuration maps `./output` into the backend. It contains the
SQLite job metadata, SQLite score/revision database, and short-lived job
artifacts under `output/work/`. Do not use `make clean` on a host whose
revisions you need to retain.

For a consistent simple backup, stop the backend before copying the directory:

```bash
docker compose stop backend
tar -C . -czf guitarscribe-output-$(date +%F).tar.gz output
docker compose start backend
```

Keep backups access-controlled: saved revisions can contain user-provided
lyrics and analysis metadata. To restore, stop the backend, replace only the
intended `output/` directory from a known backup, then start it again. Never
restore untrusted SQLite files onto a production host.

## Resource and retention controls

Set these in `.env` and rebuild/restart the backend after changing build-time
options:

| Setting | Default | Purpose |
|---|---:|---|
| `GUITARSCRIBE_MAX_DURATION_SECONDS` | `600` | Reject audio beyond this duration. |
| `GUITARSCRIBE_MAX_UPLOAD_BYTES` | 100 MiB | Reject oversized upload bodies. |
| `GUITARSCRIBE_MAX_CONCURRENT_JOBS` | `1` | Maximum simultaneous analyses on this host. |
| `GUITARSCRIBE_MAX_QUEUED_JOBS` | `3` | Maximum waiting analyses; later submissions receive HTTP 503. |
| `GUITARSCRIBE_SUBMISSION_RATE_LIMIT` | `5` | Per-client submissions during the window; set `0` only for trusted development. |
| `GUITARSCRIBE_SUBMISSION_RATE_WINDOW_SECONDS` | `3600` | Rate-limit window. |
| `GUITARSCRIBE_MELODY_SEPARATOR` | `off` | Enable `demucs` only after building its optional dependency. |
| `GUITARSCRIBE_YOUTUBE_ENABLED` | `false` | Enable the restricted, rights-confirmed YouTube resolver. |

Completed-job artifacts are cleaned according to the backend job TTL. The API
does not accept downloader cookies, credentials, playlists, or arbitrary
download arguments.

## Updates and verification

Before updating a host, create an `output/` backup, pull the desired commit,
then rebuild and run the checks:

```bash
git pull --ff-only
docker compose build
docker compose run --rm -v "$PWD/backend:/app" backend pytest -q
cd frontend && npm ci && npm run build && npx playwright test --workers=1
```

The repository CI performs the backend test suite and frontend build/E2E on
push and pull request. The optional `guitarscribe evaluate` command is useful
for quality-gate thresholds on legal golden fixtures; it is not a guarantee of
accurate transcription for arbitrary music.

## Exposure and security boundaries

The included CORS policy permits only local development origins. If exposing
the app beyond localhost, place it behind an authenticated TLS reverse proxy,
keep ports 5173/8000 private where practical, set an appropriate CORS allow
list in a deployment-specific build, and use a shared rate limiter for
multiple backend workers. Do not treat the in-memory submission limiter as a
distributed production control.

## Verify the existing local installation without Docker

Use the already installed runtime for backend tests and for the MusicXML reader
fixtures used by Playwright. Without `GUITARSCRIBE_TEST_PYTHON`, that fixture test
falls back to Docker Compose and may try to build an image.

From the `guitarscribe/` directory, run these in order:

```bash
cd backend
"$HOME/.cache/guitarscribe-runtime/bin/python" -m pytest tests -q
cd ../frontend
GUITARSCRIBE_TEST_PYTHON="$HOME/.cache/guitarscribe-runtime/bin/python" npx playwright test --workers=1
npm run build
```

The local browser configuration expects Google Chrome at `/usr/bin/google-chrome`.
Tests use their own browser profiles; tests requiring an explicit saved revision
are opt-in and are skipped without `GUITARSCRIBE_RECOVERY_REVISION`. Historical
listening-packet tests may also skip if their local audio packet is absent. A
passing automated suite checks software behavior, not transcription quality.
These commands assume dependencies are already installed; do not use them as a
fresh-machine setup procedure.
