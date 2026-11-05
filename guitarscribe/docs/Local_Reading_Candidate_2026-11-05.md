# 新歌先讀局部草稿：隔離 UX 候選，待顧問驗收

2026-11-05，A14。本次改善的是**開啟歌曲後直接看到可用的局部草稿，再按播放跟彈**的操作流程，不是新增拍格或改善辨識。正式網址保持原時間表預設；只有 `timingView=auto` 開啟候選。有局部證據時不必先找勾選框，未知段保持秒數，一鍵切回時間表。沒有新增使用者驗收要求。

## 現行問題與本次差異

11-04 的局部小節預覽已存在，但現行 `ChordTimelinePage` 僅在手動勾選或 `timingView=partial` 才展示；一般新 job 仍先落在整首長時間表。因此本段沿用 `PartialTimingSheet` 與 `observed-local-bars-v1`，只新增隔離的自動讀譜選擇及直接切換按鈕，沒有重做後端或調參。

候選載入有效證據後，先顯示「局部譜 · 待確認」，保留一句短提示；開啟後一次播放操作即可開始，切回時間表也只需一次。數字只表示草稿覆蓋秒數，不表示已確認第一拍、主副歌或整曲正確。若資料缺失、壞資料、來源／裁切不合、沒有局部區域，沿用時間表；已 metered 保持原完整小節頁。

選擇以來源 job／長度／裁切為範圍，切歌不把舊來源的選擇或編輯狀態帶入新歌。既有 fetch 的 AbortController 與來源 key 保護保留；新增回歸覆蓋延遲舊預覽、切保存版本與 Undo。編輯入口明示「到時間表編輯」，仍編輯完整來源和弦，而非草稿中的切片；完成可返回草稿。跨小節延續及既有 Undo／自動保存語義保留。

同時補足 API 結構防護：區域／小節／拍點需有限、順序正確、落在音訊內，覆蓋總秒數一致，否則不用該預覽。這只拒絕損壞資料，不改後端政策、不修拍點、不從 UI 插值。

## 真實《出賣》與可開頁面

顧問可在同主機開啟 [隔離候選](http://127.0.0.1:4181/?job=1b4158f1acee4beaa9af7cb42f3f52a0&timingView=auto)。這是暫時 Vite 開發程序，使用既有受邀 API；不是已部署正式前端，重啟環境不保證程序仍在。正常正式入口及預設不變；尚未發布給使用者驗收。

真實 job `1b4158f1acee4beaa9af7cb42f3f52a0`，315.2 秒、137 段和弦。按未修改的後端政策，共有 **144 個小節草稿、272.30 秒**：

| 原歌曲秒數 | 草稿小節數 |
| --- | ---: |
| 15.22–26.60 | 6 |
| 40.78–243.06 | 107 |
| 244.96–262.00 | 9 |
| 265.80–292.20 | 14 |
| 296.96–312.16 | 8 |

其餘仍是未確認時間段；各區重新編號，沒有補未知小節。107 是主要區段的數量，不是整首總數。初次真實瀏覽器驗證硬寫總107而停止；保留該失敗紀錄後，改以獨立後端／凍結既有政策生成的 preview 為預期值，未改任何演算法。

真實頁面截圖： [320px](../output/evaluation/reading-candidate-2026-11-05/new-job-320.png)、[390px](../output/evaluation/reading-candidate-2026-11-05/new-job-390.png)、[1440px](../output/evaluation/reading-candidate-2026-11-05/new-job-1440.png)。截圖是候選前端直接載入現行 API 的真實工作稿，不是設計 mockup。已視覺核對手機390px。頁面例外0、修訂寫入嘗試0；真正點草稿和弦呼叫原播放編譯，請求中的和弦與拍點和原稿逐項相同，沒有改演奏排程或匯出。

## 固定跨曲與資料保護

以原11-04的15份凍結局部證據，加本次新來源，合計16個錄音（不是16首成功歌曲）。後端政策檔 hash 固定且不變；原15份使用原 batch preview，新增來源由同政策在前端比較之外生成。`sources.json` 在成功真實瀏覽器比較之前保存；其 hash 與每來源 preview／score／播放 manifest hash 保存在 `frozen-preview-manifest.json`。沒有用 UI 自己的數字互相比較當獨立證據。

全16份在320／390／1440px檢查實際元件輸出的草稿數量、無水平溢出；已 metered 控制保持完整譜。批次使用真實保存稿與凍結預覽的隔離 API fixture，不觸碰 live 寫入；上面的新來源另跑了直接真實 API 的跳播檢查。

| 來源 job | 顯示局部草稿數 | 視圖 | 寬度檢查 / 寫入 / 頁面例外 |
| --- | ---: | --- | --- |
| 227fa0db8dc5435b9c942a37e093dd96 | 117 | 局部草稿 | 3 / 0 / 0 |
| 656a21b59b9a4b7e990a8bd586276c28 | 50 | 局部草稿 | 3 / 0 / 0 |
| 97501dc47be041be94e391a42dd4c562 | 128 | 局部草稿 | 3 / 0 / 0 |
| c06705428794481cb54b75541dc03ece | 129 | 局部草稿 | 3 / 0 / 0 |
| ebdc481345494b95832391262188defb | 37 | 局部草稿 | 3 / 0 / 0 |
| efa50acf438348829dce46dba5df97bd | 105 | 局部草稿 | 3 / 0 / 0 |
| fe26276f754d4578849081cf2490064f | 132 | 局部草稿 | 3 / 0 / 0 |
| 043d276fe27347d58e6b6b207841b7ab | 43 | 局部草稿 | 3 / 0 / 0 |
| 3c4baeb1c84447e6aabf72fa1bd064fd | 124 | 局部草稿 | 3 / 0 / 0 |
| a64671ebdd124f908ae46bfb62684647 | 52 | 局部草稿 | 3 / 0 / 0 |
| 605ac74e02b5460fbe253179ed3d3e30 | 0 | 原完整小節譜 | 3 / 0 / 0 |
| 62127ad66a4342a799153c4861617387 | 22 | 局部草稿 | 3 / 0 / 0 |
| e9bfab84ed9d49bf88b9be2753353c94 | 19 | 局部草稿 | 3 / 0 / 0 |
| cd754fa6b231407290c076c2351e917c | 52 | 局部草稿 | 3 / 0 / 0 |
| 10de4472b18247d99326c42f41d04b0d | 75 | 局部草稿 | 3 / 0 / 0 |
| 1b4158f1acee4beaa9af7cb42f3f52a0 | 144 | 局部草稿 | 3 / 0 / 0 |

完成後，從兩份現有 jobs DB 以唯讀方式再次取得這16份稿，逐份 score 與實際 `compile_playback_manifest` hash 與前值一致。這是來源範圍內資料保護，不宣稱整個可同時接收新工作的資料庫檔案完全不變。播放、匯出、拍格政策與既有人工修訂無修改。

## 驗證與限制

前端正式 build 通過，既有 AlphaTab 大型 chunk 警告仍在。相關子集10項通過；完整產品44項首輪為43通過、1失敗。失敗是新增版本切換 fixture 遺漏每歌曲保存版本索引，因此找不到恢復按鈕；修正 fixture 並補上切來源離開舊編輯模式後，該項定向重跑通過。另加缺證據／已 metered 的候選保留原行為兩項測試，2項通過。**沒有宣稱一次46項全綠**。既有保存、匯出、編輯及播放測試均有通過紀錄。

完整本機產物在 `guitarscribe/output/evaluation/reading-candidate-2026-11-05/`；[可提交數值](evaluation/reading-candidate-results-2026-11-05.json) 含逐來源 hash、截圖 hash、真實及批次瀏覽器結果、初次失敗與驗證記錄。音訊、真實稿完整 fixture 與登入檔不提交 Git。

可重跑：在 `guitarscribe/frontend` 執行 `npm run test:product`／`npm run build`。既有隔離服務及本機 fixture 可用時，`node scripts/verify-local-reading.mjs` 驗真實頁面，`node scripts/verify-reading-batch.mjs` 驗固定16來源；前者從既有私有設定讀邀請帳密、不輸出，並攔截修訂寫入。

目前只送顧問看實際頁面、截圖及 diff。候選尚未升正式預設，也未重問11-04已取消的單獨UI題目。顧問通過後，才由顧問形成一次完整流程的必要驗收；音樂品質與局部草稿第一拍仍未因此通過。


## 顧問退回後修訂：手機暫停操作阻塞

初次提交 `d625fbe` 未通過顧問驗收。390×844、原曲＋吉他、點第二段40.78秒時，自動跟隨與播放控制的捲動互相競爭，正常點暫停30秒仍失敗；原先1440px／吉他／較前區段的驗證漏了此情境。

根因是 `.page-shell` 的 `overflow:hidden` 成為 sticky 的最近捲動祖先，但真正捲動的是文件。初次量測 transport 在 viewport 的 top −777.83px、bottom −622.83px；祖先 scrollTop仍0、HTML scrollTop983。跟隨播放每次更新又把目前和弦捲回，讓正常點擊不斷被拉走。

最小修正只有 `.page-shell.chord-product { overflow:clip; }`：保留裝飾裁界，不建立捲動容器，讓既有 `.timeline-transport` 黏在視窗頂端。未改跟隨演算法、播放、音訊、score、拍格或匯出，沒有用force／DOM click繞過問題。

獨立前圖與正常點擊失敗記錄保存在 `output/evaluation/reading-candidate-2026-11-05/sticky-before-reproduction/`，透過隔離頁套回原 `overflow:hidden` 再次重現，不依賴會被重跑覆寫的顧問 `/tmp` 圖。原顧問腳本在修正後完整通過，且是正常單一瀏覽器邀請登入。

真實新稿於320／390px、草稿／時間表四格，以原曲＋吉他從中段播放，再以滑鼠滾輪捲650px後正常點暫停，均通過。transport四格均為top0、bottom155px；正常點暫停分別約361／280／373／288ms，無橫向溢出、頁面例外或修訂寫入。每格播放編譯收到的和弦及拍點仍等於原稿。

修後播放截圖：[320草稿](../output/evaluation/reading-candidate-2026-11-05/mobile-pause-320-auto.png)、[320時間表](../output/evaluation/reading-candidate-2026-11-05/mobile-pause-320-timeline.png)、[390草稿](../output/evaluation/reading-candidate-2026-11-05/mobile-pause-390-auto.png)、[390時間表](../output/evaluation/reading-candidate-2026-11-05/mobile-pause-390-timeline.png)。已視覺核對390px播放中控制列。

擴充真實腳本期間有驗證環境中斷：保存的response觀測共12筆，9筆200、2筆206、1筆manifest 429。多個fresh context的匿名Basic challenge會耗用InvitationGate既有10次／60秒失敗登入預算；challenge重試總數沒有獨立計量，不把12筆當作全部匿名嘗試。保留失敗截圖／JSON，這次429不計入sticky通過。修正測試為只對精確本機代理 `/backend/**` 預送既有合法邀請認證，未改正式認證、限流，也不把認證送外站。正常單一瀏覽器原重現完整流程成功，目前未證實一般單次使用也會觸發這項限流；不在此段修改auth。

新增四項315秒長譜回歸，在兩視圖明確從120秒播放、手動捲動後正常點暫停，4項通過。另檢查既有完整小節控制：原MeteredChordSongPage的控制本來是static，本次保持原行為；長完整譜可點第60小節進入編輯，欄位可見可輸入、修改可套用、無橫向溢出，1項通過。正式build通過。原有16份score與實際播放manifest在這次真實回歸之後重新核對，仍與初始hash一致。

[本次修訂數值與hash](evaluation/reading-sticky-fix-results-2026-11-05.json) 保留前後量測、四格正常點擊耗時、截圖、429中斷與16來源資料保護。重跑真實手機檢查：`node scripts/verify-mobile-pause.mjs`；定向產品回歸：`npm run test:product -- --grep 'long-sheet pause|complete metered sheet retains'`。候選網址不變，仍未升正式預設，修後再次送顧問驗收。
