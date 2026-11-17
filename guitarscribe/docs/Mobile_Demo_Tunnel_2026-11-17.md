# 手機示範隧道維運

更新：2026-11-17。供使用者在自己的手機上介紹 GuitarScribe，沿用既有邀請登入與已保存的歌曲。原 ngrok 外網入口目前回傳 403，新增獨立 Cloudflare Quick Tunnel 連到同一個受保護的本機網站。

## 目前入口

- HTTPS：<https://undergraduate-touched-participating-jane.trycloudflare.com>
- 膽小鬼手機示範：<https://undergraduate-touched-participating-jane.trycloudflare.com/?practice=demo&job=83a3643ab3814172a046cebf709f3413>
- 執行期紀錄：`output/web-preview/mobile-deployment.json`，包含 `url`、`demo_url`、版本、雜湊、驗證結果及時間。重新啟動後以此檔的新網址為準。

入口與音訊已完成外網驗證；手機三步導覽也已同步部署到首頁與視覺入口，正式 HTTPS 瀏覽器回聽及頻譜流程通過，見 [交付紀錄](Mobile_Demo_Stories_2026-11-17.md)。本文件不把入口驗證等同於 iPhone Safari 實機驗證。

Quick Tunnel 不需 Cloudflare 帳號或自有網域，網址在該隧道程序停止後失效；重新建立會換網址，沒有可用時間保證。目前官方限制為最多 200 個同時處理中的請求，且不支援 SSE。既有頁面使用一般 HTTP 請求及輪詢。[官方說明](https://developers.cloudflare.com/tunnel/get-started/quick-tunnels/)

## 固定版本與服務

| 項目 | 設定 |
| --- | --- |
| cloudflared | `2026.11.0`，Linux amd64 |
| 官方資產 | `cloudflared-linux-amd64`，40,283,099 bytes |
| SHA-256 | `51f7c68b57ed7269164075d7e789efce5b59355982f06392deeb037d982a51fd` |
| 本機快取 | `~/.cache/guitarscribe-cloudflared/2026.11.0/cloudflared` |
| systemd 使用者服務 | `guitarscribe-mobile-tunnel.service` |
| 來源 | `http://127.0.0.1:5273` |
| 連線 | HTTP/2；metrics 只監聽 loopback 隨機埠 |
| 重啟政策 | `Restart=no`，避免故障後悄悄換成另一個網址 |

版本、下載來源及完整雜湊固定於啟動腳本。雜湊與官方 release 的資產 digest、發布說明一致，下載後再次核對；既有快取不符時拒絕執行與覆蓋。關閉自動更新，明確使用空設定檔，避免讀取其他 Cloudflare 登入或隧道設定。[官方版本](https://github.com/cloudflare/cloudflared/releases/tag/2026.11.0)

## 啟動與停止

在 `/home/jonas/gemini-home/music_analysis` 執行：

```bash
python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py start
python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py status
python3 guitarscribe/backend/scripts/start_mobile_demo_tunnel.py stop
```

`start` 先檢查本機登入保護，再下載或重用已驗證的程式。已有同名、同版本路徑與同來源的服務時直接重用；若配置不符，保留原服務並報錯。使用鎖避免同時啟動兩份。

只有外網登入與音訊驗證全部通過，才原子寫入 `mobile-deployment.json`。新啟動的服務驗證失敗時會停止，且不發布新網址；發現匿名可讀網站或音訊時立即停止該次新服務。已存在的服務驗證失敗時不擅自重啟。

`status` 檢查目前服務 invocation 的網址與記錄一致，重新驗證登入及音訊。請勿連續高頻執行：匿名驗證也會計入既有登入防護的每個來源位址每分鐘 10 次失敗限制。

`stop` 只停止新手機隧道，確認停止後把新記錄標為 `stopped`。原網站與 ngrok 服務保持原狀。主機重啟或隧道失效後，執行 `stop`、`start` 取得新網址；臨時服務不會自動隨主機開機恢復。

檢查服務狀態或故障原因：

```bash
systemctl --user status guitarscribe-mobile-tunnel.service --no-pager
journalctl --user -u guitarscribe-mobile-tunnel.service -n 60 --no-pager
```

## 登入與資料範圍

既有 `InvitationGate` 仍保護首頁、靜態檔案與全部 `/backend` API。腳本只在記憶體讀取既有邀請，用 Authorization header 驗證，不把帳密放進網址、程序參數、發布記錄或輸出。驗證請求禁止跟隨重新導向，避免把登入資料送往其他來源。

入口連到既有 `output/web-preview/work`，沒有建立新帳號、個人工作區或獨立的朋友進度。同一邀請可存取同一份資料，現階段用途是本人手機現場操作。三步示範頁的只讀介面不會改變其他 API 原有權限。

本次未改帳密、原 `deployment.json`、ngrok 服務、網站服務或歌曲進度。音訊經既有網站與隧道提供；未建立外部歌曲儲存或上傳獨立歌曲副本，未申請付費服務。

## 驗證證據

首次外網驗證時間為 `2026-11-17T12:22:01Z`（台灣時間 20:22）。`status` 亦重新通過相同檢查。

| 請求 | 結果 |
| --- | --- |
| 未登入首頁與 `/backend/health` | 401，Basic challenge |
| 原邀請登入首頁與 `/backend/health` | 200 |
| 讀取膽小鬼歌曲結構 | 200，來源仍相符 |
| 未登入音訊 Range | 401 |
| 雙來源雜湊音訊，`Range: bytes=0-1023` | 206，`Content-Range` 正確，讀取 1,024 bytes |
| 新隧道、原 ngrok、原網站服務 | 皆為 active；舊 ngrok 的外網 403 仍存在 |

`backend/tests/test_mobile_demo_tunnel.py` 共 **15 項測試通過**（0.62 秒），涵蓋：

- 固定雜湊、快取重用、竄改與錯誤下載拒絕執行。
- 禁止登入重新導向；網站、API、來源與音訊 Range 驗證。
- 本機登入防護失敗時不下載或啟動；新隧道驗證失敗時只停止該新服務。
- 既有同配置服務不重啟；陌生配置保留不動。
- 僅接受 Quick Tunnel HTTPS hostname；發布原子寫入且保留原部署檔。

測試先因尚無腳本而失敗，再於實作後通過。測試使用隔離目錄及假請求；正式檢查僅發出 GET，沒有保存或代填練習。`git diff --check` 通過。
