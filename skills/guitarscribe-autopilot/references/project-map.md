# 專案導航

以下路徑相對 GuitarScribe Git 根目錄。這是定位入口，不是保證環境永遠相同；每次以目前檔案、使用者新指示與執行狀態為準。不要為一次小修改讀完所有文件。

## 決策與證據

| 要做的事 | 先讀 |
| --- | --- |
| 接續任務 | `guitarscribe/docs/Next_Decision.md` 頂部；`guitarscribe/docs/Autonomous_Development.md` |
| 核對產品範圍 | `guitarscribe/Roadmap_status.md`，較新決策優先 |
| 拍格恢復、控制組與已接受片段 | `guitarscribe/docs/Guarded_Timing_Recovery_2026-11-02.md` |
| 跨曲診斷與錄音／job 區分 | `guitarscribe/docs/Cross_Song_Health_2026-11-02.md` |
| 第一拍刷奏／和聲覆蓋 | `guitarscribe/docs/Downbeat_Rhythm_2026-10-31.md`；`guitarscribe/docs/Downbeat_Harmony_2026-11-01.md` |
| 手機、簡潔頁、編輯及和弦按法 | `guitarscribe/docs/Chord_Web_Mobile_2026-10-27.md` 對應小節 |
| 執行、部署及回退 | `guitarscribe/docs/OPERATIONS.md`；目前服務設定（避免輸出密鑰） |

2026-11-02 的「答答聲可以跟拍」只涵蓋文件指定的兩段 click；不是所有和弦／整曲驗收。`fixed-dbn-recovery-v1` 在現有主機明確啟用，但程式預設仍關閉。不能從預設值推論線上狀態，也不能把歷史「等待啟用」當現況。

## 程式與驗證

- 後端：`guitarscribe/backend/app/`；相關測試 `guitarscribe/backend/tests/`。拍格在 `analyzers/beats/`，診斷在 `services/analysis_health.py`，流程在 `core/pipeline.py`。
- 現有批次工具在 `guitarscribe/backend/scripts/`：`audit_song_batch.py`、`compare_beat_decoders.py`、`summarize_beat_decoder_batch.py`、`smoke_guarded_timing_recovery.py`。先讀介面，沿用工具而非另建平行框架。
- 前端：`guitarscribe/frontend/src/`。`ChordSongPage.tsx` 是小節頁，`ChordTimelinePage.tsx` 是無確認拍格的時間表；兩種都要考慮。和弦按法入口在 `ChordFingerings.tsx`。
- 測試指令以 `guitarscribe/frontend/package.json`、`playwright.product.config.ts`、後端 `pyproject.toml` 及 `.github/workflows/ci.yml` 為準。一般前端建置 `npm run build`，產品測試 `npm run test:product`；後端在 backend 工作目錄以現有相依環境執行 `python -m pytest`。按改動選測試，不為文件改動跑全套音訊模型。
- 本機既有 Python 環境位於 `/home/jonas/.cache/guitarscribe-runtime/bin/python`，依賴不一定在系統 Python；路徑不存在就查目前啟動方式，不任意重裝所有模型。
- 診斷產物多在 `guitarscribe/output/evaluation/`（未進 Git）；報告連結存在不代表其他 checkout 已有資料。沒有原始快取就記錄驗證缺口。

## 線上維運條件

目前受邀站與開發站是兩套資料：`guitarscribe/output/web-preview/work`、`guitarscribe/output/work`。重啟前核實兩邊受影響工作的 queued／running 等實際狀態；讀取失敗不是「沒有工作」。避免中斷使用者分析，可繼續離線開發等工作結束。

站點設定見 `output/web-preview/deployment.json`；邀請憑證在 `output/web-preview/access.json`，不可列印、提交或放報告。不要輸出整份環境或帶 token 的服務設定。服務名稱與回退方法見 OPERATIONS。

前端部署只取必要的 `index.html` 與 `assets/`，先保留回退版本，新增資產後切換入口，確認受邀網站實際載入新版本；不要把含歷史／私人試聽的整個 `frontend/dist` 或 `public` 搬上線。音樂候選用獨立產物／明確入口，不覆寫既有工作譜或已驗收音檔。

現有 ngrok 網站依賴主機開機連網；runtime systemd 設定可能不跨重開機保留。不要宣稱已完成永久代管，也不要為持續工作自行修改休眠設定。
