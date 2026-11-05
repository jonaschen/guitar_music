# 移調播放與文字旋律筆記：同網址候選更新

2026-11-06。功能版本 `755b9d2`，含先前播放修正 `6fe644a`；兩段皆完成顧問獨立審查後發布。仍使用[原受邀候選網址](https://occupier-disgrace-stammer.ngrok-free.dev/reading-candidate-2026-11-05/?job=1b4158f1acee4beaa9af7cb42f3f52a0&timingView=auto)，重新整理即可載入新bundle；正式首頁預設與舊首頁資產保持不變。由顧問統一交使用者，不增加同題工程測試。

## 使用者可驗收的變化

- 明確顯示原曲由和弦估計為B小調、未確認；選單是伴奏移調，小調移到G仍是G小調，不宣稱更正成G大調。
- mix移調後明示改為吉他，可直接播放／暫停；若原本選原曲，繼續播原曲原調。移調後仍禁止與原錄音錯調合奏，原曲錄音沒有變調。
- 可收合「我的旋律筆記」，純文字記錄自己抓的調性／音名／片段，700ms自動保存，失敗可重試。獨立來源儲存、跨瀏覽器讀取；和弦Undo／還原原分析／移調不刪除或轉調手記。分頁草稿與多瀏覽器CAS保護明列於[筆記報告](Melody_Text_Notes_2026-11-06.md)。這是共用邀請空間，不是私人帳號，文字不會自動演奏；自動旋律仍凍結。

## 完整驗證

最終58項產品瀏覽器測試、46項後端相關測試及正式build通過。顧問另驗8執行緒競寫、雙tab離線草稿／衝突／連續刷新與明確接受最新版本；隔離真API的兩個browser context、中文多行持久化、移調／Undo／還原原分析等自存完成再刷新，筆記文字及版本不變。隔離原稿副本及DB與正式workdir分開，未用正式用戶筆記作寫入測試。

外網匿名候選與notes API均401；登入後新HTML／JS／CSS／notes GET／原首頁200，主要資產hash與發布檔一致，原首頁內容hash不變。runtime能力確認small0、Chordino、improved_accompaniment與YouTube可用，不執行音訊辨識。正式notes API唯讀檢查時記錄0列；沒有替使用者填測試字。

顧問外網唯讀驗證通過：移調自動吉他播放暫停、切source後再移A仍維持原曲播放、筆記載入不修改、320／390／1440無溢出、0頁面例外，攔截2筆工作稿修訂、0筆記PUT。**第一輪原曲播放等30秒未完成，第二輪45秒觀察上限通過，不能寫成首次全過。** 原曲完整WAV為60,516,082 bytes，較大冷下載是可能原因，但第一次沒有完整耗時證據，原因仍未知。原曲冷載效能列後續範圍，本段不再改動拖延交付。

## 備份、停機與恢復紀錄

發布前沒有活動分析工作。舊候選bundle與停止服務後的jobs／revisions一致副本保存於 `output/backups/key-notes-2026-11-06/`（目錄權限700）。原notes資料庫不存在，已記錄；啟動後產生空schema，再用SQLite backup API保留初始副本 `melody-notes-initial-poststart.sqlite3`。原資料庫每表資料hash與備份一致，不覆寫原稿／修訂。

本次實際遇到 transient unit在stop後被回收，原 `systemctl start` 回Unit not found，造成一次短暫服務中斷。立即依原factory/5273/backend工作目錄重建服務；tunnel未改，工作目錄、靜態／邀請檔、一年TTL31536000、small0／Chordino／DBN恢復、旋律off、Node／Python／Vamp／rhythm路徑核對保留，恢復後PID889603。沒有用會改成8000及不同TTL／旋律設定的run_local_preview.sh。

新增 `backend/scripts/start_invited_web.sh` 作可重建命令，已做bash語法及運行中不變更的檢查；[OPERATIONS](OPERATIONS.md)已更正stop/start假設並記錄notes備份路徑。

**限流限制須如實保留：** 停機前沒有取得submission rate直接runtime值，舊文件為20/hr；重建後因未指定而有效5/hr。顧問決定維持目前5/hr、不因舊文字擅自擴大。這一項停機前值未知，不能宣稱所有環境完全一致；後續如有新確定值或決策再調整。

## 發布清單與回退

新bundle只選 `index.html/assets/font/soundfont` 四個必要類別，共19個檔案；沒有舊public listening、歌曲音檔或歷史報告。原站84個非候選檔案hash一致。同候選舊檔已保存於備份的 `candidate-site/` 及本機發布產物 `previous-candidate-live/`。

[最終發布數值與hash](evaluation/key-notes-release-2026-11-06.json)包含清單、每檔大小／hash、HTTP驗證、備份／環境與已知限制。本機完整產物為 `output/evaluation/key-notes-release-2026-11-06/`；顧問外網原始結果／圖已複製到該目錄。登入資料與資料庫備份不提交Git。

若需回退UI，先將當前候選目錄移到新的保留路徑，再把 `previous-candidate-live/` 移回原候選名稱，原首頁不動。後端新增API與舊前端相容；保留新的notes.sqlite3，不以舊備份抹掉使用者已寫文字。若後端也須回退，先停止並一致備份所有現行資料，再按已驗證程式版本處理；不以reset資料庫代替程式回退。

本輪完成的是兩項具體使用者問題；沒有提升調性／和弦辨識準確率，沒有解凍自動旋律，也不代表整個音樂MVP已完成。
