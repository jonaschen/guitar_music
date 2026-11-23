# GuitarScribe 接手入口

這個 repository 是已供使用者練習的 GuitarScribe。開始維護、開發或檢查雲端前，先讀 `guitarscribe/docs/MAINTENANCE_HANDOFF.md`，再依其中連結選讀最新故事盤點、發布證據與操作手冊。不要依歷史聊天、舊 Roadmap checkbox 或舊隧道網址推定當前狀態。

可用的專案 skill 在 `skills/guitarscribe-autopilot/SKILL.md`；它提供接續工作與維運流程。若客戶端沒有安裝 skill，仍可直接讀取 repository 內的文件。Skill 不會在 session 關閉後持續執行。

## 工作規則

- 先查 `git status --short` 與近期提交。使用者私人音檔、output、顧問筆記及他人修改可能同時存在；只提交自己負責的檔案，不使用整庫清理或覆蓋。
- 產品主線是歌曲結構、鎖定段落、原曲／低頻回聽、人工根音與和弦，以及比較後沿用。主旋律方向已停止並隱藏；個人雲端不自動擴成公開多人平台。
- 正式人工稿以雲端 `/srv/guitarscribe/work` 為準。本機資料是獨立副本；程式發布不得回灌本機 work 或初始遷移快照。
- 原曲／低頻練習預設不混入人工和弦聲；理論參考音必須明確開啟。工程測試不等於音樂正確率或實體手機驗收。
- 重現有風險的行為缺口後，以適當測試先證明失敗，再修正與驗證。完整環境／指令以 `.github/workflows/ci.yml` 和交接文件為準。
- 服務更新由單一負責者進行。先核對活動、分析、備份與版本，再按 `guitarscribe/docs/APP_RELEASE_RUNBOOK.md` 執行；保留資料與可回退程式。沒有當下證據時不宣稱已通知其他 session 或已部署。
- 不輸出或提交 `access.json`、SSH key、token、完整環境、私人錄音／截圖。缺憑證時記錄查核限制，不重設帳密或重建資源。

## 每次交付留下的內容

更新交接入口指向的工作表與驗證紀錄：實際 commit／部署版本、已完成項、真正未完成項、測試通過與跳過／失敗範圍、備份與回退位置，以及下一個可以執行的步驟。不要將尚未驗證的功能、研究假說或歷史待聽項批次標成完成。
