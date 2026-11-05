# Codex 工作交接：session-developer 接手開發

日期：2026-11-05。交接基準：`38243c9`（main，已推送）。

使用者指示：「請把工作交接給 session-developer. 你轉為顧問 持續監督開發進行」。本文件由原負責 Codex 整理；自此由 **session-developer 負責實作與交付，原 session 擔任顧問／審查者**。交接通知已送達；`session-developer` 已回覆完整閱讀及接手確認（讀取時 HEAD `784e76f`），首段計畫已由顧問審閱。

## 1. 接手先做什麼

1. 完整閱讀本文件，再讀 [最新決策](Next_Decision.md) 頂部、[工作表](Autonomous_Development.md)、[混音基準及同日否決結果](Mixed_Reference_Baseline_2026-11-05.md)。舊日期的「等待測試／帳號」不是新待辦。
2. 檢查 HEAD、工作樹及服務現況，保留其他 session／使用者的未提交檔。讀專案的 [自主推進 skill](../../skills/guitarscribe-autopilot/SKILL.md)；音樂診斷使用 [music-analysis](../../skills/music-analysis/SKILL.md)。
3. 在本文件末尾追加接手確認：session 名稱、實際 HEAD、開始的工作段落、回報管道。不要等待使用者重新講歷史。
4. 第一段先用既有參考與快取定位和弦錯誤，完成下面的具體交付；不是重新跑全部模型或繼續已否決的拍格閾值調整。

## 2. 產品目標與界線

- 手機／桌面貼 YouTube → 分析 → 看和弦譜、聽原曲＋吉他跟彈 → 少量修正、保存、Undo／Redo。大量手工重建拍格不算 MVP 達成。
- **主旋律停止、凍結並隱藏**。保持獨立產品；外部工具只作有範圍的校驗，不變成產品必要依賴。
- UI 保持簡單。已接受片段、原始分析與人工修訂不能覆寫；新音樂候選另存。
- 使用者希望工程、自動測試與跨曲檢查自主完成，持續 commit／push；只有必要試聽／主觀 UI 驗收集中交給他。現在沒有新的人耳待測項目。
- 家中電腦試用仍是目前選擇。GCP 已提出方案，**沒有授權建立付費資源**；24 小時／US$5 試部署只是提案。不要把「有 Google Cloud」視為部署批准。
- 交接期間另一個 session 轉來使用者的帳務更正：Google 帳號採月結後付費、目前可用。另一專案一次 Gemini 402 不能推論整個 GCP 不可用，也不應要求使用者儲值。已讀本機參考 `/home/jonas/gemini-home/long-term-care-expert/reports/model_update_2026-11-05.md`；它的 Hana 專案／服務不是 GuitarScribe 目標，請勿操作。日後 gcloud 操作明確帶 `--project`／`--region`，不要改共用預設或輸出金鑰；該文件舊沙箱核准步驟不適用目前環境。本次沒有操作雲端。

## 3. 已完成與未完成

| 工作 | 證據與狀態 | 接手含義 |
| --- | --- | --- |
| 自動評分器 | GuitarSet 六錄音、42 個控制案例符合預定檢查；16 份快取重評 | 校準評分器，不代表音樂變準。無標註部分仍未知。 |
| Klangio 免費校驗 | 3 個授權公開片段，共 9 個工作已完成；有半速、第一拍與和弦錯誤，full 詞彙未達改善條件 | 不是可靠裁判；停止該詞彙路線，不再提交同題。沒有上傳使用者 YouTube 音訊，餘額未知。 |
| 容器發布 | 13 份快取本機／容器完全一致；手機操作、短網址、274 秒歌曲分析、重啟、19 檔備份還原及後端換 IP 通過 | 部署工程可用，音樂 MVP 尚未達標；沒有換掉現行受邀站。 |
| 人聲＋鋼琴基準 | SWD HU33 三首固定 0–45 秒，既有 small0／Chordino；三段皆退時間表 | 原始和弦與產品分數相同，這三段誤差已存在辨識輸出。不能外推所有曲目。 |
| 內拍層級假說 | 固定 2 脈衝嵌入 4 拍、重拍與原脈衝不變；16 份輸出沒有新增可用案例 | **已否決**，不縮短區段、放寬容差或刪事件強求通過。 |
| 任選新歌 | 仍有整首退時間表、半速／第一拍錯、和弦名稱／邊界錯誤 | 這才是品質主線；不要以容器、測試數或範例可播宣稱已完成。 |

混音基準（不是流行歌泛化驗收）：

| HU33 作品 | minimal／DBN 重拍 F1 | 根音分數 | 大小調分數／可評涵蓋率 |
| --- | --- | --- | --- |
| 04 | 0.952／0.951 | 0.642 | 0.690／81.1% |
| 18 | 0.500／0.444 | 0.583 | 0.567／80.3% |
| 21 | 0.370／0.421 | 0.732 | 0.730／100% |

沒有逐拍標註，所以不能插值出「真實拍點」或報逐拍正確率。04 重拍接近參考，不證明每個內拍正確，也不支持直接取消產品保護。

## 4. 不可遺失的人耳判決

- 《後來》B 能跟拍但慢一半、第一拍錯：全曲主速度連續性候選已拒絕並移出產品，禁止改名重問。
- 《你的樣子》final0 原 DBN 僅 15–55 秒的跟拍／密度／第一拍通過，不是全曲或全域引擎驗收。
- 《下一個天亮》偏好 A 每小節一下；約播放器 20 秒和弦仍不合。Am7 延音跨 F／C 是排程事實，**原曲真實和弦未定**。不要把減少刷奏當作和弦修好。
- 11-02 兩段 click 通過，受保護恢復已啟用；保持已有控制案例。對完整來源、和弦名稱或其他片段不可擴張宣稱。

詳見 [Timing_Feedback](Timing_Feedback_2026-11-05.md) 與工作表。每拍一下保留可選，沒有升預設的授權判決。

## 5. 第一個開發段落：既有和弦錯誤的可重跑定位

目的：用已有參考把下一項修正縮到可驗證的一層，避免再要求使用者替每首歌判斷整個流程。

輸入先凍結為三份 HU33 快取，加既有 GuitarSet 的好／壞控制（包含已記錄的 Funk2 根音 22.1% 失敗）；記錄錄音、區間、雜湊及評分涵蓋率。這些已參與分析的資料都叫開發／回歸集，不能改稱未見測試集。

可直接進行的工作：

1. 不重跑模型、不呼叫外部 API，對現有預測和參考的共同時間軸產出逐區間誤差表，分列根音錯、根音對但種類錯、轉位／詞彙不可評、邊界時間差。分類規則需清楚；有重疊分類時不要重複相加當總錯誤率。
2. 列每來源的錯誤秒數、可評秒數與實例；保留失敗錄音，不只報平均。原始／產品分數相同已經知道，不必再做一輪無新訊息的比較。
3. 若發現確定的解析、時間基準或排程工程缺陷，直接修正並以最小相關回歸驗證；若是辨識限制，提出**一個**有新證據的共同機制，不堆疊調參。
4. 新音樂實驗事前寫固定輸入、唯一變因、成功／失敗分支、已接受控制與資源上限。升為共同設定前，另凍結至少兩份未用來改規則的來源作確認；不可看完分數再挑錄音。

交付：可重跑腳本／必要測試、逐來源結果、是否有可修工程缺陷、唯一建議下一步。定位段以兩小時為初始上限；不足時報缺哪一項證據，不能自動演變成新模型搜尋專案。這是顧問提出的起始工作範圍，不是使用者追加的截止承諾；若接手後發現更直接的已證實缺陷，可記錄理由調整優先序。

## 6. 開發與顧問分工／監督方式

- **session-developer**：實作、測試、版本管理、交付紀錄與已授權部署；每個完整工作段落更新工作表並 commit／push。不要為例行可逆修正重新向使用者請示。
- **原 session／Codex 顧問**：審查假說、證據、跨曲退步、停止條件與產品採用建議；原則上不與 developer 同時改同一份產品程式。必要修正先說明檔案所有權。
- 每段完成回報：`commit 範圍 / 改了哪一層 / 每來源結果與涵蓋率 / 測試與 artifact 路徑 / 失敗與未知 / 下一步 / 是否真需要人耳`。準備升音樂預設或擴張外部費用／上傳範圍前，先提供可審查結果；顧問意見不替代使用者對費用或新增外傳的授權。
- 顧問對每份回報給明確結論：可繼續、補哪項證據、或停止哪個假說，並追加於本文件「接手與顧問紀錄」。一般工程不必為每個小 commit 等顧問，避免創造新的阻塞。
- **通訊現況（同日更新）**：重新發現工具後，`mcp__codex_tui__send_message_to_thread` 已可用；已成功送出交接通知。developer thread：`01a1ab73-ec8d-7861-bfd3-2d5aa75b02bc`；顧問 session-product-owner thread：`01a11662-f018-7bd1-875c-452646cd7608`。直接傳送段落回報即可，無須使用者轉貼。先前 collaboration 子代理介面無法處理此既有 session，該失敗不代表目前傳訊不可用。
- developer 以跨 session 訊息通知顧問接手與每段成果，長篇證據放文件再附路徑。文件更新本身不會喚醒 session；尚未建立定時監看排程。不要另開同名代理冒充使用者指定的 session。

## 7. 執行環境與資料保護

- 專案：`/home/jonas/gemini-home/music_analysis`；remote：`https://github.com/jonaschen/guitar_music.git`，main。
- Python：`/home/jonas/.cache/guitarscribe-runtime/bin/python`。DBN／Chordino 依賴與執行方式見 [OPERATIONS](OPERATIONS.md) 及既有腳本，不自行升模型套件。
- 現行受邀站：`https://occupier-disgrace-stammer.ngrok-free.dev`；上次檢查使用者服務 `guitarscribe-friends-web`（5273）、`guitarscribe-friends-tunnel` active。接手請重新確認，勿將此記錄當即時健康結果。
- 正式服務仍是本機 Python web，非此次容器。引擎 small0＋已接受受保護 DBN 恢復＋Chordino，旋律 off；final0 與已拒絕連續性機制沒有升預設。
- live DB：`guitarscribe/output/web-preview/work/jobs/jobs.sqlite3`；dev DB：`guitarscribe/output/work/jobs/jobs.sqlite3`；各自 work 下另有 revisions。重啟前看進行中工作；備份採已驗證停止／一致性流程，不把運作中的 SQLite 直接複製稱為完整備份。
- 網站登入資料位於 `guitarscribe/output/web-preview/access.json`，API key 位於使用者私有 config；不可輸出／提交秘密。不要把網站或歷史音訊批次外傳。
- 容器檢查用 project `guitarscribe-mvp-check` 的服務已清理；資料卷／候選 image 留供回溯，切勿因看見它們就替換 live。
- 約 8GiB RAM，重工作循序，推論限制執行緒；不要同時堆疊模型、Docker build 與多個瀏覽器，也不要關掉使用者 Chrome。
- 交接時已有無關變更：前端兩個 `tsconfig*.tsbuildinfo`；大量歷史文件／音訊／截圖及 listening 目錄未追蹤。禁止 `git add .`、清空或 reset 這些內容。只提交自己擁有的檔案；共用工作目錄的 git 操作循序進行。

## 8. 證據索引

| 用途 | 文件／本機 artifact |
| --- | --- |
| MVP 交付原則 | [實驗／發布計畫](MVP_Experiment_and_Release_Plan_2026-11-05.md)，其中未更新的 E3／主機下一步以本交接及最新決策為準 |
| 自動評分 | [交付報告](Automatic_Validation_Delivery_2026-11-05.md)、`docs/evaluation/validator-*.json` |
| 外部校驗 | [Klangio 結果](Klangio_Validation_Result_2026-11-05.md)；`output/evaluation/external-validation-run-2026-11-05/` |
| 容器交付 | [驗證報告](Container_Release_Verification_2026-11-05.md)；`output/evaluation/container-release-2026-11-05/` |
| GCP 提案 | [台灣區方案](GCP_Deployment_Proposal_2026-11-05.md)；尚無付費資源，採購前重核價格與目標主機 YouTube 可用性 |
| 混音基準 | [報告](Mixed_Reference_Baseline_2026-11-05.md)、[可提交數值](evaluation/mixed-reference-baseline-2026-11-05.json)；`output/evaluation/mixed-reference-2026-11-05/{plan.json,input-manifest.json,results/}` |
| 被否決假說 | [固定計畫與16份結果](evaluation/meter-level-audit-2026-11-05.json)；`output/evaluation/meter-level-audit-2026-11-05/` |

上表 `output/` 路徑相對 `guitarscribe/`，原始音訊與完整本機證據未提交 Git。換機接手不能假設 clone 就含全部快取。SWD 只取 HU33 許可來源，沒驗證完整 ZIP MD5；不要混入另有再散布限制的 SC06 錄音。

最近實作提交：`197504b` 容器／代理；`2bf3b52` GCP 提案；`d5c4557` helper 提交 music-analysis skill；`cdcb3f3` 混音參考讀取器及 19 測試；`38243c9` 內拍假說否決紀錄。本次只交接，不跑新音訊實驗、不更動網站。

## 接手與顧問紀錄

- 2026-11-05，原 session：交接整理完成；角色改為顧問。等待 `session-developer` 接手確認及第一段證據回報。尚未啟用跨 session 自動監督。

- 2026-11-05，同日重試：跨 session 傳訊成功，已請 session-developer 確認接手與首段計畫，並直接回報顧問。原先「無法直接傳訊」限制解除；尚待接手回覆。

- 2026-11-05，session-developer 已確認接手：完整閱讀，讀取時 HEAD `784e76f`，web／tunnel active。首段依固定 HU33＋GuitarSet（含 Funk2）快取做逐區間分類、每來源秒數／涵蓋率／邊界差，不跑模型／API；維持兩小時初始上限。developer 負責程式、工作表與結果文件，顧問負責此交接狀態。顧問已回覆可開始，提醒避免重複計入錯誤秒數、不插值創造逐拍真值、保留失敗來源；完成後直接傳訊審查。
