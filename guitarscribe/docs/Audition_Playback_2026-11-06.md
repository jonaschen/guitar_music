# 和弦／根音試聽、即時音量與共通跟彈

日期：2026-11-06。使用者需要用原曲核對修改後的和弦，也希望不同來源音量容易平衡。這輪提供播放工具，不更正辨識結果、不把局部拍點視為音樂已確認。

## 播放行為

- 撥奏內容可選「和弦／只彈根音」。根音來自目前實際發聲的和弦名稱，`C/E`仍彈C；不把slash bass當根音，也不重加Capo。根音放在E2–D#3的低吉他音域。
- 頻率預設「沿用原刷奏」，另有每小節一次、每兩拍一次、每拍一次、每拍兩次。起音使用已辨識拍點，每拍兩次取相鄰真拍點中點；不因換和弦加刷，不用BPM補點或外推最後半拍。每兩拍保持跨3/4小節的兩拍間隔及弱起相位。
- 無完整拍格但有既有局部草稿時，明示「依待確認拍點試聽」；只在已知區段演奏，未知段暫停伴奏，原曲繼續。沒有可用拍點才禁用新頻率，原刷奏及根音仍可用。後端核對來源job身分、實際音長、來源offset後才讀該job拍點，拒絕同長度不同歌曲。
- 撥奏及頻率是播放專用選項，不存進SongScore、Undo／修訂、原分析或MIDI；舊預設manifest完全不變。改選項會停止舊播放並取消尚未完成的編譯，循環、跳轉及暫停沿用原排程。
- 兩個滑桿「原曲音量／和弦／根音音量」位於播放控制旁，初值0.45／0.24；播放中平滑即時調整兩個master gain，不停播、不重建原曲。零音量仍排程，使歸零後可以即時恢復；sample、振盪器及撥弦瞬態共用吉他master。原始音檔不改，進階吉他音量亦共用同一狀態。

## 依使用者補充的調性與跟隨行為

使用者明確要「原曲保持不變，聽看看改後是否更合」。因此移調後保留原曲＋吉他選項，原曲仍原調、原速，吉他使用目前和弦；明示可能不同調、供核對，不做source pitch shift、不把估計調性改稱真值。Undo／還原及Capo既有行為保留。這項明確新決定取代A15先前的mix mismatch禁用。

新分析《下一個天亮》有完整拍格，原本只亮小節；《出賣》時間表已有逐和弦跟隨，造成體驗差異。兩種頁面現在都有sticky播放器、目前／接著和弦、當前和弦高亮及可關閉的自動跟隨；保持真小節與局部草稿區別。為保留手機譜面空間，調性與Capo位於播放器下方，不塞入sticky；自動捲動把和弦放在控制列下方。

## 驗證與發佈狀態

後端新12項、既有downbeat／MIDI38項通過：不等長拍點、中點、無尾端外推、跨3/4與弱起、休止／gap、局部未知段、Capo／移調／slash root、來源身分反例、預設及原稿不變。產品回歸61個獨立案例全過：先28過，協調中斷後補餘33項；其中31先過，兩個斷言（舊頻率文案及Playwright對option原生disabled的判定）修正後針對重跑3項全過，不重跑已通過案例。最終build及發布見下方紀錄。

顧問已用兩首真job獨立驗證：`6ea8733485f74db6a5443a3b9d7e829a`完整拍格、`1b4158f1acee4beaa9af7cb42f3f52a0`局部草稿；改調後保mix、原曲rate1、原曲gain0.16、吉他零→0.72即時生效而source不重建；320／390／844橫向／1440無溢出、active chord及提示可讀，零頁面例外。390px實播截圖另經顧問檢視。工程證據 `/tmp/guitarscribe-a19-engineering.json`、瀏覽器證據 `/tmp/guitarscribe-a19-after.json`會存入本段隔離產物目錄。

曾因主機記憶體／swap壓力發生冷載等待；初次5秒UI等待逾時但snapshot已有正確region，改為15秒初始載入等待，未放寬功能斷言。顧問首次navigation20秒逾時及其腳本range字串'.72'不合法均保留，之後以DCL／元素等待及合法'0.72'完成。兩邊先後交錯開Chrome造成競爭，協調後結束自家回歸讓真job先驗；原回歸28項通過、1項被SIGINT中斷、32項尚未跑，後續只補餘33項，不把中斷當功能失敗或已通過。

預定只更新本機5273的 `reading-candidate-2026-11-05/` 與必要的API路由；正式首頁／其84檔保持。發佈前核無active job、備份一致SQLite與舊候選，短restart後檢查資料／原靜態hash。ngrok月流量ERR725不在本輪修復，不重啟、付費或改連線；由顧問交付實際可用入口與使用者驗收。

完整原稿、文字旋律筆記及A15待測保留；本輪功能不能視為和弦準確率提升。

最終TypeScript與候選base正式build通過；19個必要檔，共10,168,413 bytes（7個build檔＋12個hash核符未變的font/soundfont資源），不複製public/listening。驗證manifest見 [數值](evaluation/audition-playback-results-2026-11-06.json)。已完成備份與發佈，正式入口顧問煙霧核對通過。

## 本機候選已發布

功能提交 `dc62004`。入口為 `http://127.0.0.1:5273/reading-candidate-2026-11-05/?job=1b4158f1acee4beaa9af7cb42f3f52a0&timingView=auto`；完整拍格新job可換成 `6ea8733485f74db6a5443a3b9d7e829a`。同一Basic邀請保護；ngrok的ERR725仍未修復，這是本機入口發佈，不能稱外網已恢復。

發佈前後無active分析，先以SQLite backup API對三資料庫各自取得一致快照並通過integrity_check；舊candidate完整備份。備份位於 `output/backups/audition-controls-2026-11-06/`，目錄700、DB600。原首頁84個檔案SHA256全部保持，三資料庫各table logical row內容／數目在短web restart前後完全一致；沒有還原、寫入或覆蓋使用者資料。

先放新hashed資產、短restart既有web單元啟用API，兩真job POST根音每拍預覽分別產生576／657個單音事件；通過後才原子換candidate index。19個新必要檔共10,168,413 bytes，另保留原3個hash bundle供既有開啟頁面相容，因此實際candidate為22檔；無歌曲音訊或listening資料發布。匿名GET401，受邀candidate index與build完全相同。服務與隧道設定未改，未重啟ngrok。

發布數值／manifest見 [結果](evaluation/audition-playback-results-2026-11-06.json)，本機細節於 `output/evaluation/audition-controls-2026-11-06/{before-release,release-results}.json`。回滾可將備份 `candidate/index.html`恢復（舊hashed資產仍在），或恢復整份備份candidate；新的API為額外路由，舊預設manifest端點未改。不要回滾DB覆蓋之後的使用者修改。

顧問已用正式5273入口完成兩真job完整煙霧驗收：原曲rate1、改調保mix、根音每拍兩次產生1313／1152 events、吉他即時mute→0.72及原曲0.16且source不重建、跟隨／active、四尺寸無overflow、0頁面例外；2次修訂請求攔截，未寫使用者資料。正式證據為 `output/evaluation/audition-controls-2026-11-06/consultant-production.json`。A15的主觀驗收仍集中保留，不增加重複音樂試聽。
