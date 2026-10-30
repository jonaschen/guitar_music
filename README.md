# GuitarScribe — 選首歌，聽著原曲跟彈

貼上 YouTube 歌曲連結，分析後取得可播放、可修改的和弦稿，一邊聽原曲、一邊看和弦跟彈。目標是讓不擅長聽音抓歌的人，也能輕鬆開始彈喜歡的歌。

目前是**受邀網頁試用版**：需要等待分析，不能保證所有歌曲都準確。主旋律／吉他獨奏旋律轉錄已停止並隱藏。已試聽的六首歌、七個錄音中，多數和弦可跟刷、微調後可用；《小手拉大手》最好，《遇見》仍需改善。這不是通用準確率。

## 朋友如何開始

**正式方向是免安裝網頁版。朋友不必下載 GitHub、Docker、Python、模型，也不需要顯示卡或 API key。**

1. 開啟維護者提供的 **HTTPS 試用網址**，輸入邀請帳號與密碼。
2. 首頁可直接試《小手拉大手》範例，或貼上你想彈的 YouTube 歌曲。
3. 等待分析完成，再一邊聽原曲、一邊看和弦跟彈。

GitHub 是程式與說明文件，不是分析服務的網址。`localhost` 也不是能傳給朋友的網址。首版使用獨立的受邀朋友共用空間；不要把它當成具有個人帳號隔離的公開服務。臨時試用網址由維護者另行提供，不把邀請密碼放進 GitHub。

朋友需要能連網、能播放音訊的瀏覽器；目前以 Chrome 驗證，手機完成響應式工程檢查，實機體驗仍待試用。分析算力、模型與來源下載由後端負責。首版若由維護者的電腦承載，該電腦必須保持開機與網路連線，之後才轉常駐主機。

## 先試《小手拉大手》

首頁按 **「開啟範例：小手拉大手」**，立即載入內附和弦稿，可播放系統吉他、修改和弦與復原，不需先跑模型。每次開啟都建立一份獨立工作版本（仍在受邀者共用空間），不依賴開發者機器上的網址或 revision ID。

範例含和弦與時間，不含歌曲錄音、影片或歌詞。按 **「用這首歌曲開始分析」** 可填入對應 YouTube 來源；再按「開始分析」，完成後便可原曲跟彈。這會重新分析來源，不是替範例直接附上任意音檔；不同錄音不共用時間對齊。

## 換成你喜歡的歌

1. 貼上單支 YouTube 影片網址，保留「整首」，按 **開始分析**。請使用你有權分析的來源；帶播放清單的連結只處理其中一支影片。
2. 等待分析完成。第一次會下載拍點模型；耗時取決於歌曲長度、網路與電腦，並非即時出譜。
3. 歌曲頁按 **播放**，選「原曲＋吉他」跟彈。時間表會顯示目前／下一個和弦並跟隨播放位置；點任何和弦可跳到該處播放。調性與 Capo 在播放旁。
4. 有需要才展開 **練習與編輯**，循環一段或修改和弦。「復原」可以撤銷修改，修改會自動保存。
5. 要試另一首，按 **分析新曲目**。保留歌曲頁網址可回來繼續；也可在「下載與備份」備份完整工作檔。

若拍格足夠一致，顯示小節譜；若拍格未確認，顯示**和弦時間表**，依實際秒數排列，吉他每次換和弦彈一下。時間表仍可跟原曲核對，但不是完整刷奏節奏譜，也不提供需要拍格的 MIDI／MusicXML。不要把每個顯示格當成一小節。

移調後原曲音高不會跟著改，請切「吉他」練習或回到原調合奏。主旋律功能不在這次試用範圍內。

## 回報只需三項

請試不同歌曲，不必每首逐小節標註：

- **歌曲連結**。
- **能否跟彈**：大致可以／需少量修改／大部分不合。
- **最明顯的問題**：時間位置（例如 1:20）、換和弦太早／太晚／和弦不搭，或操作卡住的位置。

音樂品質與軟體故障會分開處理；一次歌曲失敗不會被說成所有鋼琴／現場來源都不適用。

<details>
<summary>維護者：伺服器環境、部署與排錯（朋友不用操作）</summary>

### 網頁試用部署

目前運行的網址使用既有 Linux 分析環境、`app.web:create_app` 與 ngrok HTTPS，並非 Docker 部署；已驗證登入、範例編輯保存與 YouTube 30 秒分析／混合播放。啟停、資料位置及重開機限制見 [維運文件](guitarscribe/docs/OPERATIONS.md)。下列容器配置已完成建置與設定檢查，完整容器啟動／分析驗證尚未完成，不應視為已驗收的安裝流程。

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
| Linux x86_64 | 已驗證既有 Python 環境＋獨立空資料目錄；Docker 完整運行尚待驗證。 |
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
