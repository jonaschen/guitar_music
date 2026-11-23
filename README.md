# GuitarScribe — 看低頻、聽原曲，練習自己抓和弦

GuitarScribe 協助整理歌曲結構，鎖定主歌／副歌等段落，看低頻圖、回聽原曲，記下自己的根音與和弦判斷，再比較及沿用重複段。自動分析提供可修改的初稿，不能保證每首歌都正確。

目前使用**個人 Google Cloud 工作室**，以同一個介面跨裝置練習或向朋友說明判斷；尚未開放多人帳號。主旋律轉錄已停止並隱藏。雲端的已保存進度是主要版本，本機舊站不會自動同步。

## 開始練習

1. 開啟 [個人工作室](https://guitarscribe-324350766154.asia-east1.run.app)，使用既有個人帳密。休息時按「啟動工作室」。
2. 從「我的歌曲」選既有歌曲，或從主畫面加入音檔／YouTube來源。雲端曾遇YouTube下載驗證限制；來源拒絕時改用自己有權分析的音檔，既有歌仍可使用。
3. 進入「視覺化練習」，查看並確認歌曲結構初稿，合併不必要的邊界，再鎖定要練的一段。
4. 產生低頻圖，圖上定位或設定A–B，回聽原曲並填寫根音與和弦。低頻回聽不混入人工和弦聲音。
5. 已完成重複段時先比較再沿用，保留不同結尾；不必重新填寫每一段。等「已保存」後再離開。

操作說明：[低頻／A–B](guitarscribe/docs/Root_Visual_Practice_User_Guide_2026-11-14.md)、[歌曲結構](guitarscribe/docs/Song_Structure_User_Guide_2026-11-17.md)、[鎖定段落與和弦](guitarscribe/docs/Section_Chord_Practice_2026-11-17.md)、[調性與組成音](guitarscribe/docs/Learning_Practice_2026-11-21.md)、[中斷恢復／級數／Capo](guitarscribe/docs/Recovery_and_Degrees_2026-11-23.md)。新功能的實際部署版本以交接文件為準。

## 維護與下一個 session 接手

從 **[維護交接入口](guitarscribe/docs/MAINTENANCE_HANDOFF.md)** 開始，接著讀 [故事與待辦總盤點](guitarscribe/docs/Backlog_Review_2026-11-23.md) 和 [發布／回退手冊](guitarscribe/docs/APP_RELEASE_RUNBOOK.md)。現用版本與資源在 [deployment.json](guitarscribe/infra/on_demand/deployment.json)。

專案skill是 [guitarscribe-autopilot](skills/guitarscribe-autopilot/SKILL.md)。它提供接手流程與只讀狀態工具，仍需要repo、可執行環境及相應雲端權限；密碼與私人音檔不在Git。不要拿初始快照或本機舊資料覆蓋雲端工作。

回報問題時提供歌曲／錄音來源、時間範圍與操作或聽感即可。工程錯誤、音樂判斷與實體裝置驗證會分開記錄，不要求使用者逐小節填滿才可繼續開發。

<details>
<summary>維護者：本機開發與歷史容器配置</summary>

### 網頁試用部署

目前正式個人服務已在 Google Cloud；維護從 [交接入口](guitarscribe/docs/MAINTENANCE_HANDOFF.md) 與 [程式發布手冊](guitarscribe/docs/APP_RELEASE_RUNBOOK.md) 開始。以下 Docker／ngrok 是本機開發與歷史試用配置，不能取代雲端 work 或視為現用部署。歷史容器驗證見 [2026-11-05 報告](guitarscribe/docs/Container_Release_Verification_2026-11-05.md)。

`compose.web.yml` 提供靜態 production 前端、反向代理與邀請密碼；後端採與已驗證流程相同的 Chordino／Beat This。使用獨立 Docker volumes，不掛載既有 `output/work`。建立邀請檔後：

```bash
cd guitarscribe
python3 backend/scripts/prepare_web_access.py output/web-preview
export GUITARSCRIBE_WEB_AUTH_FILE="$PWD/output/web-preview/friends.htpasswd"
docker compose -f compose.web.yml up -d --build
```

維護者本機入口預設 http://localhost:5273。只有前端代理綁定 localhost；對外必須再接 HTTPS 入口。邀請資料存在 `output/web-preview/access.json`（不進 Git）；受邀使用者是共用空間，不是個人帳號。首次部署會下載依賴與拍點模型，伺服器暫以 8 GB RAM、10 GB 空間作試用建議，並非最低規格。

### 維護者的本機測試環境

需要[安裝並啟動 Docker](https://docs.docker.com/get-started/get-docker/)（含 Docker Compose）。不必另外安裝 Python、Node、Chordino 或申請 API key。第一次建置會下載數 GB 的依賴；建議先預留 10 GB 磁碟與 8 GB 記憶體，這是試用配置建議，並非量測最低需求。

1. 在 GitHub 按 **Code → Download ZIP**，解壓縮；或執行：

   ```bash
   git clone https://github.com/jonaschen/guitar_music.git
   ```

2. 在解壓縮／下載的資料夾中開啟終端機，進入 `guitarscribe` 資料夾：

   ```bash
   cd guitar_music/guitarscribe
   ```

   ZIP 下載的外層資料夾通常叫 `guitar_music-main`，請依實際名稱調整。

3. 啟動試用版：

   ```bash
   docker compose -f compose.trial.yml up -d --build
   ```

4. 建置完成後開啟 **http://localhost:5173**。不用建立 `.env`，也不用本機開發者的資料庫。請使用此試用配置；舊 `docker-compose.yml` 是不同引擎的開發配置。

目前優先驗證 **Linux x86_64 + Chrome**。平台條件分開看：

| 環境 | 條件與目前狀態 |
|---|---|
| Linux x86_64 | 已驗證既有 Python 環境，以及 `compose.web.yml` 的獨立資料空間、分析、保存與還原；模型快取重用。 |
| Windows Intel／AMD | 需 Docker Desktop 的 Linux containers。WSL 2 路徑需開啟硬體虛擬化；本專案尚未做 Windows 實機驗收。 |
| Intel Mac | 需 Docker Desktop；本專案尚未做 Mac 實機驗收。 |
| Apple Silicon／Windows ARM | 不在這輪驗證範圍，CPU 套件與原生插件相容性不能先保證。 |
| 手機／平板 | 直接開啟維護者提供的試用網址；不必安裝分析引擎。 |

Windows 的 WSL／版本條件與 Mac 支援版本，以 [Docker Windows 文件](https://docs.docker.com/desktop/setup/install/windows-install/)及 [Docker Mac 文件](https://docs.docker.com/desktop/setup/install/mac-install/)為準。Docker 支援某個系統不等於 GuitarScribe 已在該系統驗收。

## 關閉、再開與更新

在 `guitarscribe` 資料夾執行：

```bash
# 關閉；保留分析與修改
docker compose -f compose.trial.yml stop
# 下次開啟
docker compose -f compose.trial.yml up -d
# 檢查服務與分析紀錄
docker compose -f compose.trial.yml ps
docker compose -f compose.trial.yml logs --tail=80 backend
```

Git 下載者更新時執行 `git pull --ff-only`，再執行 `docker compose -f compose.trial.yml up -d --build`。ZIP 下載者下載新版並保留同一個 Docker 專案名稱。資料放在 Docker 的 `guitarscribe-trial_trial-data` volume，模型另存 `trial-models`；不要使用 `down -v`，那會刪除這些資料。分析來源保留期在試用配置設為一年，保存的修訂另存在資料庫。

## 常見問題

- **localhost 拒絕連線**：先確認 Docker 已啟動，再執行上述 `up -d` 與 `ps`。`localhost` 指使用者自己的電腦，不是分享給別人的公開網址。
- **5173 已被占用**：停止舊的 GuitarScribe，或設定 `GUITARSCRIBE_TRIAL_PORT=5273` 後啟動（PowerShell：`$env:GUITARSCRIBE_TRIAL_PORT="5273"`；bash：`export GUITARSCRIBE_TRIAL_PORT=5273`），改開 http://localhost:5273。
- **YouTube 無法取得音訊**：特定影片、地區、登入要求或 YouTube 端變動可能阻擋下載。改用另一個可存取來源或上傳本機音檔；不必提供帳號密碼或 cookies。更新下載器可執行 `docker compose -f compose.trial.yml build --no-cache backend`，再 `up -d`。
- **第一次分析停在拍點階段較久**：先看 backend logs 是否正在下載模型；不要連續重送。若網路下載失敗，保留錯誤訊息回報。
- **短時間大量送出被限制**：試用配置每小時最多 20 次提交，同時分析一首；等待佇列結束後再試。

`compose.trial.yml` 僅供維護者本機試跑。對外試用改用 `compose.web.yml` 的正式前端與邀請密碼，API 不直接暴露，資料 volume 與開發機分離。


</details>

## 開發與驗證

- [應用程式與 API 文件](guitarscribe/README.md)
- [資料保存與維運](guitarscribe/docs/OPERATIONS.md)
- [最新開發決策](guitarscribe/docs/Next_Decision.md)
- [產品進度與已知限制](guitarscribe/docs/Chord_Web_Mobile_2026-10-27.md)

試用版採 [Chordino](https://github.com/c4dm/nnls-chroma) 與 [Beat This](https://github.com/CPJKU/beat_this)，YouTube 下載使用 [yt-dlp](https://github.com/yt-dlp/yt-dlp)。分析在維護者的伺服器執行；來源下載與首次模型下載需要網路。試用 Docker 固定 Chordino 原始碼修訂與已驗證的 CPU 拍點引擎版本，避免悄悄退回不同引擎。
