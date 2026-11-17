# Codex 自主開發工作表

**2026-11-17 自己的手機現場介紹已發布：** 使用者選擇由自己的手機向朋友示範。新增只查看／原曲播放的三步「手機介紹」（歌曲結構→聽一段→看低頻），原首頁／視覺／結構頁可進入；候選展示不套用，保留確認狀態，A/B 循環與背景暫停。原 ngrok 當月流量用完，已建立有原登入保護的 Cloudflare 臨時 HTTPS 入口。6 新瀏覽器＋13 原頻譜入口回歸＋15 隧道測試、build、三實曲與外網完整流程通過；六 DB 不變。programmer-session 負責隧道，partner-session 前端整合與統一部署。尚未實體手機／Safari 驗收，也尚未提供各朋友獨立帳號。[手機使用說明](Mobile_Demo_User_Guide_2026-11-17.md)、[故事地圖與驗證](Mobile_Demo_Stories_2026-11-17.md)、[現行連結與維運](Mobile_Demo_Tunnel_2026-11-17.md)。

**2026-11-17 歌曲結構與沿用工程已發布：** SS01新歌分析及ST8–ST11比較、確認後沿用、整批撤銷、反覆／完整順序匯出與暫不練偏好均可用。新曲《可惜不是你》17段待確認初稿已備妥；原138個根音區段不需先填滿。新reuse後端29＋既有root10、原根音瀏覽器50、新比較14、真API瀏覽器2與build通過。正式膽小鬼v1/v38、沒那麼簡單初始v2/v0及目前新曲入口已查核，六份資料庫保持。沒有獨立全曲真值，名稱／邊界品質仍awaiting_human；不再以此阻塞工程。人類只需有空時自然練習，不必重跑工程驗收。[使用說明](Song_Structure_User_Guide_2026-11-17.md)、[交付與限制](Song_Structure_Reuse_Delivery_2026-11-17.md)。

**2026-11-17 新歌結構分析已發布；ST8–ST11 開發中：** 任一完成且音訊可用的歌曲可從視覺根音頁啟動結構分析，離頁恢復進度、取消、預覽後明確套用。實際《可惜不是你》287.823秒錄音以固定模型完成17段待確認初稿，耗時1032.78秒；兩個相同錄音job共用經來源核對的候選，未算兩首新曲。正式入口可查看17段初稿，六份既有DB與Score保持不變。184後端回歸、2權重驗證、26結構前端案例、4相關根音案例、2真API隔離流程及build通過。受限工作使用2.5GiB／200%CPU／20分鐘上限；失敗不改舊稿。接續 programmer-session 後端沿用CAS/ledger與partner-session比較前端，音樂品質待回聽不阻塞工程。[使用說明](Song_Structure_User_Guide_2026-11-17.md)。

**2026-11-17 主畫面入口補接：** 原首頁仍使用較舊前端，未明確連到視覺練習；現於空白首頁與已載入原曲的工作區提供「視覺化練習」，將目前 source job 帶到視覺入口並開啟頻譜。首頁／視覺入口同步 build，後端不重啟；入口 2 測試與原產品編輯／保存／YouTube／預設 4 回歸通過，實曲與空白首頁查核見[驗證紀錄](evaluation/visual-main-entry-2026-11-17.json)。

**2026-11-17 ST4–ST7 工程已發布：** 歌曲結構可改名、移交界、分開／合併、分別確認、復原、自動保存、歷史及 JSON 備份；專用原曲回聽每次核對音訊 SHA 與來源 fingerprint。原視覺入口新增「歌曲大段」與「整理歌曲結構」，只篩選交疊根音、不重切或複製。膽小鬼 13 段（含既有回饋）／沒那麼簡單 14 段各建立獨立結構 v1；原 159／151 根音區段與進度、五份既有 DB 及 Score 不變。129 後端回歸＋21 seed、46 根音瀏覽器、21 結構測試、1 真 API／SQLite 隔離流程、build 與兩曲四尺寸正式唯讀驗證通過。programmer-session 負責後端與 seed，partner-session 整合前端及發布，沒有交叉部署。名稱／邊界品質仍 awaiting_human；ST8–ST11 沿用後置，新歌一鍵自動結構分析未接入；新曲可手動建稿。晚上只需自然使用正在練的一大段，不必重跑工程檢查。[使用說明](Song_Structure_User_Guide_2026-11-17.md)、[交付與限制](Song_Structure_Editor_Delivery_2026-11-17.md)、[測試數值](evaluation/song-structure-editor-2026-11-17.json)。

**2026-11-17 使用者結構回饋已套用，繼續 ST4–ST7：** 《膽小鬼》原1/2前奏合併、原8/9改副歌、原12保留收尾段（較接近主歌）、原13/14只確認尾奏名稱。來源＋原candidate hash綁定的sidecar另存，原模型與根音稿不改；修正版13段顯示原段號、名稱／邊界分開確認。60後端／9瀏覽器及兩曲四尺寸／零寫稿驗證通過，同核對入口已更新。使用者晚上才方便測試並要求持續推進：programmer-session 接 ST4 獨立保存/API/TDD，partner-session 接 ST5–ST7 前端編輯、回聽與根音導覽；統一部署／提交，不等待人耳才能開發。此回饋是看過候選後的局部修訂，不作獨立盲標。[回饋與驗證](Song_Structure_Feedback_2026-11-17.md)。

**2026-11-15 歌曲結構首輪已交付：** 依「先做好名稱辨識，再做沿用」及 go，ST1 固定協定／ST2 隔離推論完成；ST3 回聽／評分工程完成、音樂品質 `awaiting_human`。兩首各14個歌曲段落初稿，耗時846.84／921.89秒；《沒那麼簡單》有3.852秒未判定，兩曲分別7／4個相鄰同名邊界，不能當正確率或已減少根音填寫。獨立 `/structure-review-2026-11-15/` 已可選兩曲、聽整段／交界，極短段引導聽交界；尚無修改與保存。發現並拒絕移植版48kHz／正規化前處理差異，改用原Demucs4.0.1 CLI四聲部→固定fold0，保留v1／v2及停止證據。48後端／8瀏覽器測試、兩曲四尺寸／播放中切歌／零寫稿與合成音通過；根音稿、Score、原186網站檔案不變、服務未重啟。programmer-session 唯讀審查，partner-session 單一整合。ST4–ST7 結構保存／修正／導覽仍未做，ST8–ST11 沿用與反覆仍在後；不將初稿升正式預設。[故事地圖](Song_Structure_Stories_and_Plan_2026-11-15.md)、[結果與手冊](Song_Structure_Candidate_2026-11-15.md)、[驗證數值](evaluation/song-structure-results-2026-11-15.json)。


**2026-11-14 視覺操作更新已完成：** 依使用者最新回饋，點頻譜／方向鍵會同步右側段落，保留精確游標秒數、A–B 與縮放；拖曳仍只改回聽範圍。新增常顯 A 開始／B 結束說明、兩次點選標記按鈕與圖上標籤；目前段落快捷鍵改用右側選定段落。圖預設 2 倍高、可選 1–4 倍，桌面加寬並新增 60／120 秒時間窗。T6–T8 已依 TDD 完成，45 項完整回歸、TypeScript／build、兩曲四尺寸真瀏覽器驗證通過；每曲 1 source／0 tone、0 寫稿與頁面例外。programmer-session 已唯讀審查。沿用原視覺入口，166 個其他網站檔案不變，服務未重啟。[本輪驗證](evaluation/root-cursor-follow-2026-11-14.json)、[操作說明](Root_Visual_Practice_User_Guide_2026-11-14.md)。回退：`output/backups/root-cursor-follow-2026-11-14/`。目前無剩餘工程待辦，使用者已肯定開發方向，主觀順手程度待自然使用回饋。


**2026-11-14 最新工作已完成：** 使用者要求故事清單、故事地圖、排序代辦及 TDD 全部完成，暫時無法測試。partner-session 統一實作／發布，programmer-session 唯讀審查。[故事與代辦](Root_Practice_Stories_2026-11-14.md) T1–T5 全部 `done`，涵蓋採用目標、原曲播放、工具折收、持續練習、保存與交付。41 項完整回歸、最終文字標示重查、TypeScript／build、兩曲真音訊四尺寸通過；每曲 1 source／0 tone、0 寫稿，166 其他網站檔案不變。[驗證摘要](evaluation/root-workflow-2026-11-14.json)。同 `/visual-practice-2026-11-14/` 已更新，回退在 `output/backups/root-workflow-2026-11-14/`。本輪沒有剩餘可驗證開發待辦；主觀操作是否順手單列 `awaiting_human`，使用者方便後自然使用回饋即可，不要求立即試用。主旋律與新自動辨識未擴張。

更新：2026-11-06。這是接續工作用的短表；最新產品決策仍見 [Next_Decision.md](Next_Decision.md)。

**負責人變更：** 使用者指定 `session-developer` 負責開發交付，原 session 轉顧問；接手狀態、第一段工作及每段審查方式見 [交接文件](Session_Developer_Handoff_2026-11-05.md)。已收到接任確認與首段計畫，後續透過跨 session 訊息直接回報顧問；未建立定時監看排程。

## 使用方式

在本專案的 Codex session 呼叫 `$guitarscribe-autopilot`，例如：

```text
$guitarscribe-autopilot 我暫時沒空測試。請持續完成可自行驗證的改善，保持 commit 與 push，把必要的試聽集中留下。
```

Skill 原稿在 [skills/guitarscribe-autopilot](../../skills/guitarscribe-autopilot/SKILL.md)，本機安裝於 `~/.codex/skills/guitarscribe-autopilot`，以連結指向原稿，避免兩份規則不同步。其他機器須另行安裝這個目錄；若目前 session 尚未列出新 skill，重新開啟 session，或直接要求讀上述 SKILL.md 執行。

此 skill 不建立定時任務，也不能讓已停止的代理自行醒來。它負責執行期間的工作選擇、驗證、紀錄及接續；尚未設置無人值守排程。單一 session 足夠，額外 session 可在取得並行授權後負責獨立回歸檢查。

## 目前範圍

- 目標是任選 YouTube 歌曲後看譜、聽原曲跟彈；主旋律維持停止及隱藏。
- 已接受拍格、和弦按法與既有人工修訂保留。音樂候選須獨立，不用工程通過代替聽感。
- 人耳待測只阻塞該候選的採用，不阻塞其他工程與離線診斷。

## 待辦與接續

以下保留每項實際狀態，依新使用者問題調整優先序；本次已實際執行 skill，不只是建立工作規則。

| ID | 狀態 | 問題／證據 | 下一步與完成條件 |
| --- | --- | --- | --- |
| A09-chord-errors | done | 固定九份快取已完成定位；產品尚未改善。顧問獨立 64 測試及九份重跑一致，驗收紀錄 e26f39c | [交付報告](Chord_Error_Localization_2026-11-05.md)、[計畫](evaluation/chord-error-plan-2026-11-05.json)、[數值](evaluation/chord-error-results-2026-11-05.json)。無新增人耳驗收；接續 A10 固定消融。 |
| A10-chord-bass | rejected | 固定 bass 1→0 消融：九份原版重現，但 Funk2／三份 HU33 內部錯根音皆增加，其他控制也退步 | [報告](Chord_Bass_Ablation_2026-11-05.md)、[修訂計畫](evaluation/chord-bass-ablation-plan-v2-2026-11-05.json)、[數值](evaluation/chord-bass-ablation-results-2026-11-05.json)。baseline／candidate 各九次，第一份格式比較修正後重用，5 測試與18份離線重評通過。固定消融停止、產品不採用、送顧問驗收；無新試聽。 |
| A11-chord-dictionary | done | 217 個實際字典項目完成稽核：錯根音中嚴格可表示 38.0%、候選模式缺席 39.6%，為混合限制 | 顧問已驗收 f76b0f3：[報告](Chord_Dictionary_Audit_2026-11-05.md)、[計畫](evaluation/chord-dictionary-audit-plan-2026-11-05.json)、[數值](evaluation/chord-dictionary-audit-results-2026-11-05.json)。零推論，7 測試通過；沒有產品修正證據。缺逐影格候選排名／HMM 前後證據，不繼續靜態細分或擴字典。 |
| A12-chord-decoder | done | 九份原版觀測事件完全不變；HMM 救回47.782s、損失6.626s，未達解碼修改分支 | 顧問已驗收 6fdbe3c：[報告](Chord_Decoder_Observation_2026-11-05.md)、[計畫](evaluation/chord-decoder-trace-plan-2026-11-05.json)、[數值](evaluation/chord-decoder-trace-results-2026-11-05.json)。3 測試、正規化重建與秒數守恆通過。停止定位段，不調參、不新增分類；下一產品方向需有新的可測機制。 |
| A13-ismir2019 | rejected | 固定作者五模型 ensemble：Funk2整段N，HU33平均root −5.53百分點，未達門檻 | [報告](ISMIR2019_Candidate_Result_2026-11-05.md)、[計畫](evaluation/ismir2019-plan-2026-11-05.json)、[數值](evaluation/ismir2019-results-2026-11-05.json)。45次音樂子模型forward＋5次合成可行性forward；5測試、原始碼/權重hash與評分域核對通過。候選停止、送顧問驗收，不搜尋下一模型、不改產品。 |
| A14-local-reading | awaiting_human | 顧問已通過eee41ac及受邀HTTPS手機完整操作；production候選獨立發布，原預設保持 | [發布入口／回滾](Local_Reading_Release_2026-11-05.md)、[最終manifest／驗證](evaluation/reading-release-results-2026-11-05.json)。19必要檔10.16MB，原84檔hash不變、無重啟，匿名401。由顧問交付《出賣》一次完整操作驗收；developer尚未通知使用者。音樂品質不因此通過。 |
| A15-key-notes | awaiting_human | 移調後可直接播吉他並完整標大小調；共用文字手記獨立來源自存，Undo/還原/移調保留 | 755b9d2已沿同受邀候選更新：[發布與備份/限制](Key_Notes_Release_2026-11-06.md)。58產品/46後端/build、顧問雙tab/隔離真API/外網唯讀驗證通過；由顧問交使用者。首輪原曲30s逾時、45s上限重測通過，冷載待查；重建transient後有效5/hr、停機前限流未知皆已記錄。 |
| A16-chord-stem | rejected | 全九份固定分離完成；HU33 root均值−1.804pp、0/3達+5pp，Funk3邊界recall−13.333pp，04／18另退步 | [結果／逐項護欄](Chord_Stem_Ablation_2026-11-06.md)、[數值](evaluation/chord-stem-ablation-results-2026-11-06.json)。九次分離＋27次Chordino，20.2分鐘；原版三層gate／hash／9測試過。停止固定介入，不調參、不跑確認組、不改產品；顧問27份獨立重評及54stem hash驗收通過（66d8bc7）。 |
| A17-mixed-baseline | done | 兩首完整原混音基準完成；root91.730%／58.908%，Electra有145.745s錯根音、207額外邊界，產品未改善 | [結果／覆蓋／限制](MIREX_Mixed_Baseline_Result_2026-11-06.md)、[數值](evaluation/mirex-mixed-baseline-results-2026-11-06.json)。兩次原版Chordino、25.22秒；顧問7測試、完整diagnostic重評、逐row裁切／域守恆／hash驗收通過。無新模型／分離／產品寫入／試聽，不代表華語流行。 |
| A18-independent-bass | done | 作者真bass/piano八段0lag核符；固定pYIN穩定涵蓋僅8.869%，證據不足，未能判定低音反證路線 | [結果／取得與相容修訂](Independent_Bass_Evidence_Result_2026-11-06.md)、[事前方案](Independent_Bass_Evidence_Plan_2026-11-06.md)。7測試過，2ZIP／成功1份全曲f0；原1h截止保持。coverage不足不當訊號否決，不調參、不進分離bass恢復性／候選，無產品修改或新試聽；顧問獨立7測試、NPZ逐frame／cell累計／hash與40ms錯位拒絕驗收通過。 |
| A19-audition | done | 和弦／根音、真拍點頻率、局部未知段停伴奏、即時雙音量；原曲保持原調與目前和弦合奏，兩種譜共通跟隨 | [功能／發布](Audition_Playback_2026-11-06.md)。dc62004已推送並發布5273候選；12新＋38既有後端、61產品、build及顧問2真job隔離審查過。三SQLite一致backup/內容不變、84首頁hash不變、匿名401；顧問正式5273兩真job完整smoke通過，0頁面例外／無使用者寫入。ngrok ERR725未改，A15待主觀驗收併同入口。 |
| A20-continuous-reading | done | 沒那麼簡單無共同局部拍格；天后有74bar／218.56s。無regions時候選auto用連續和弦文字時間、不假小節 | [盤點／發布](Continuous_Reading_2026-11-06.md)。f0c209c已推送並發布5273候選；21必要UI／tsc/build與顧問正式5273真2job smokes全過（含中性hover），0寫入／0頁面錯誤。原84檔與2job原稿/音訊/manifest完全不變，無API重啟/DB寫入/模型運算。 |
| A21-diatonic-mask | rejected | 原217-state HMM精確重播後，固定自動key＋調內硬限制：HU33 root均−2.628pp、漏多秒數全增，控制亦退步 | [事前方案](Diatonic_Candidate_Plan_2026-11-06.md)、[結果／覆蓋](Diatonic_Candidate_Result_2026-11-06.md)。9baseline exact path/raw/projected gate過、9candidate、零模型；14工程測試過。停止這組固定介入，不調key/HMM/門檻或加行進，不變預設；顧問獨立NumPy全18 path、key/mask/raw與完整diagnostic/hash重評通過，確認否決。 |
| A22-lyrics-worksheet | rejected | 保存等工程通過，但使用者指出歌詞／旋律筆記各自獨立且脫離小節，產品方式被否決 | 既有發布0a644e2保留至A23驗收替換；不再詢問原逐行填寫題。資料及既有筆記完整保留，由A23沿用。 |
| A23-song-notes-on-score | rejected | 譜下三層對照與資料保護工程通過，但逐句選小節／秒數太難，使用者已否決易用性 | caf8f40及發布紀錄保留；取消原待驗收題，A24取代。資料及微調能力沿用，不宣稱產品已符合需求。 |
| A24-listen-and-mark | awaiting_human | 貼整首一鍵加入先填簡譜；邊聽按句首，自動進句，不停播／不捲動 | [流程與時鐘接線](Listen_And_Mark_Lyrics_2026-11-07.md)。28不同UI／純函式案例及tsc/build過，顧問實際source-clock／保存三job通過；最後版slot／四尺寸及無格手機scroll差0複審過，d27b1e4已push／發布同候選；API及PID不變、4DB／3source／84原檔一致。正式三job四尺寸唯讀亦過，0寫入／0例外。和弦過密／準確性仍未解，不新增辨識功能。 |
| A01-view | done | 原局部視圖保留；使用者要求共同品質改善，取消單獨閱讀驗收 | 不再要求使用者驗收這一輪；原功能可選，不升預設。 |
| A01-density | rejected | 後來B人耳確認慢一半、第一拍錯；全曲主速度限制不能判定正確拍速 | 連續性方法從產品恢復程式移除，離線失敗證據保留；不直接加倍或改phase再問同題。 |
| A01-dbn | done | 你的樣子final0原DBN在15–55秒跟拍／密度／第一拍通過 | 紀錄局部通過，正式新引擎不自動開啟，不擴張全曲。 |
| A02 | done | 偏好A每小節一下，每拍一下保留可選；和弦仍未通過 | 不升每拍預設。約20秒Am7延音跨F／C已稽核；未判定原曲真實和弦，不新增同份試聽。 |
| A05 | ready | 1／3組反映音量小；第3組其實沒有click | 15個音量輔助／獨聽WAV本機備妥，原檔未改。依新優先序暫緩試聽頁擴充，不要求重聽。 |
| A06-local | done | 原有mir_eval補CML／AML及共同片段範圍；42控制案例符合預期，16份快取重評，47測試通過 | 有參考的檢查可重跑，無參考仍未知；無音樂準確度改善聲明。六錄音包含Chordino失敗基準，不以平均掩蓋。見 [交付](Automatic_Validation_Delivery_2026-11-05.md)。 |
| A06-external | done | 使用者提供key、確認未購買方案；已完成9工作（6基準＋3詞彙對照），全部取得結果 | 拍點有半速／第一拍錯；full未修好指定大小調錯誤，詞彙路線停止。涵蓋率已補，不當真值、不升產品預設。見 [實測](Klangio_Validation_Result_2026-11-05.md)。 |
| A07-container | done | 修正 DBN 依賴／開關、套件安裝範圍及後端換址後502 | 13快取完全一致；手機操作、短網址及274秒歌曲分析、重啟／19檔備份還原、代理自動恢復通過。現有站未動。見 [容器驗證](Container_Release_Verification_2026-11-05.md)。 |
| A07-host | done | 使用者先維持家中試用，已有Google Cloud；GCP台灣區成本已核實 | [方案](GCP_Deployment_Proposal_2026-11-05.md)：4GiB固定約US$35.97／月、8GiB約US$64.29／月，流量等另計；24小時試部署提案尚未執行。家中站維持，雲端決策不阻塞音樂主線。 |
| A08-mixed-reference | done | 三段固定人聲＋鋼琴參考已完成，19測試通過；原始和弦與產品分數相同，三段皆退時間表 | 04重拍F1約0.95但原始內拍多為2拍／小節，被連續拍格保護拒絕；18／21原始重拍也不準。見 [基準](Mixed_Reference_Baseline_2026-11-05.md)，不放寬預設。 |
| A08-meter-level | rejected | 固定2脈衝嵌入4拍且重拍／原脈衝保留的規則，在16份既有輸出沒有新增可用案例；04仍拒絕 | 依事前停止條件否決，不縮短區段／放寬容差／刪重拍；無新候選、無人耳測試。見 [基準後續](Mixed_Reference_Baseline_2026-11-05.md#同日後續內拍層級假說已否決)。 |
| A03 | done | 上傳時內部 input／裁切檔名取代原標題，已另存去路徑標題 | `3887684`；新上傳生效，舊稿不猜測改名。 |
| A04 | done | 時間表補拍格後，原檢查節奏空display令吉他消失 | 編譯器明確支援保留原檢查模式；兩個真實候選182／70吉他事件與原稿逐項一致，另有測試。 |

同時只由一名負責者更新同一任務；額外 session 使用獨立範圍，主 session 合併證據與決策。失敗假說改為 `rejected` 並留下原因，不刪掉失敗來源來改善統計。

## 必要人類驗收佇列

A22獨立面板與A23逐句選小節／秒數流程均被使用者否決，舊易用性待驗收題取消。A24改成貼詞即可填簡譜、聽到句首按一下即進下一句；先完成工程與真歌曲顧問審查。和弦辨識／密度與整體手動修正成本仍待改善，不請使用者重做既有音樂試聽，也不將測試通過當成產品接受。

使用者目前無法驗收，保留 A15「轉調後吉他播放＋我的旋律筆記」；下次使用者方便時，由顧問提醒一次並交付同一受邀入口，不建立排程或重複通知。A14局部小節閱讀併在同一流程，不另重開已取消的舊閱讀題。

來源為《出賣》(搖滾Live版)，job `1b4158f1acee4beaa9af7cb42f3f52a0`，315.2秒；候選 [受邀入口](https://occupier-disgrace-stammer.ngrok-free.dev/reading-candidate-2026-11-05/?job=1b4158f1acee4beaa9af7cb42f3f52a0&timingView=auto)，版本與限制見 [發布紀錄](Key_Notes_Release_2026-11-06.md)。最短操作是轉調後播放、寫一小段文字筆記，再判斷使用是否順手；工程保存／衝突／復原已驗證，不請使用者重做。只評播放與UI，不因此認定和弦或旋律辨識通過。文字筆記不含自動旋律辨識。

11-04三組已收到判決，見 [11-05回饋](Timing_Feedback_2026-11-05.md)；不以音量修正或新名稱重問相同音樂。待驗收只阻塞候選採用，A16和弦正確性評估持續；主旋律凍結、現有預設與人工稿保持。

## 本段交付

- 2026-11-04：建立自主開發 skill 與此接續表；屬開發流程交付，不宣稱音樂品質提升。
- 驗證範圍：skill 格式、資源連結、安裝連結及工作分流規則；未執行新音訊實驗、未改線上程式。行為規則仍需在後續實際開發中驗證並依失敗修正。
- 2026-11-04 接續實作：完成上述局部視圖、跨曲／資料保護檢查及上傳歌名修正；UI候選待主觀判斷，獨立修正已完成。全曲密度與刷奏仍未完成，不把局部改善當成專案達標。

- 2026-11-04 集中推進：完成固定15錄音批次、同快取runtime parity、原稿保護、規律刷奏、三組受邀試聽與獨立試驗譜；音樂判斷仍為awaiting_human，正式拍格引擎未切換。
