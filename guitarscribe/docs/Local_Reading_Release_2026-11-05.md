# 局部讀譜候選：受邀 HTTPS 獨立入口

2026-11-05。UI工程基準 `eee41ac03c459141c4d7e16d22a9560ec72fb040`，顧問已通過修後手機操作；本次只發布獨立 production 靜態子路徑。沒有升正式預設，也沒有音樂品質／第一拍驗收。

## 顧問交接入口

[《出賣》完整流程候選](https://occupier-disgrace-stammer.ngrok-free.dev/reading-candidate-2026-11-05/?job=1b4158f1acee4beaa9af7cb42f3f52a0&timingView=auto)，沿用原有邀請登入。入口先交顧問；尚未由 developer 通知使用者。顧問決定何時以這一首做一次完整操作驗收，不再重問舊單獨UI題目。

這是 production build 的受保護路徑，無須Vite程序；原首頁仍是既有版時間表。候選只是直接展示可讀的局部草稿，未知段仍用秒數，不改辨識、原工作譜、播放排程或匯出。版本、已知限制與工程回歸見 [候選報告](Local_Reading_Candidate_2026-11-05.md)。

## 發布內容及保護

發布前確認沒有進行中的分析工作。以 `npm run build -- --base /reading-candidate-2026-11-05/ --outDir ../output/evaluation/reading-release-2026-11-05/site` 產生獨立bundle，不覆寫原build。只新增 `guitarscribe/output/web-preview/site/reading-candidate-2026-11-05/`，不重啟服務；PID前後均801721，仍從11-04 20:45:40 CST持續運作。

Vite預設連帶複製 public 的舊listening、external-checkpoint與review.html。清理只移走本次新候選副本，保存在本機 `output/evaluation/reading-release-2026-11-05/omitted-public/`，沒有刪原public或原站舊入口。最終允許清單只有 `index.html`、`assets/`、`font/`、`soundfont/`，**19檔、10,158,244 bytes**。沒有舊試聽目錄、歌曲wav/mp3/m4a/flac/ogg或lab；soundfont是應用隨附樂器資產。每檔hash與大小見 [最終發布數值](evaluation/reading-release-results-2026-11-05.json)。

原站84個既有檔案於發布前後逐檔SHA256一致，原首頁index亦經外網比對一致。沒有修改jobs DB、原稿、人工修訂或既有小節頁資產。

## 外網驗證

- Developer以外網HTTPS檢查候選HTML、主JS、主CSS及API登入後200，實際HTML／JS／CSS內容hash與發布檔相符，資產prefix正確、API仍走原 `/backend`。
- 匿名候選頁、候選主資產、真實job API，三項均401。沒有放寬邀請保護；帳密不輸出、不寫入發布檔或數值證據。
- 顧問獨立以一個瀏覽器正常邀請登入：390px、原曲＋吉他、40.78秒中段正常點暫停；視圖切換、編輯返回、320／390／1440無橫向溢出、原首頁仍時間表、0修訂寫入與0頁面例外。沿用剛通過的結果，不為報告重跑音訊或相同瀏覽器流程。

顧問原始證據在 `/tmp/guitarscribe-a14-public-consultant/`，已複製結果及390px播放圖到本機持久產物 `output/evaluation/reading-release-2026-11-05/consultant-public-result.json`、`consultant-390-playing.png`。完整manifest、build log、HTTP狀態及原站hash亦在該目錄。沒有新辨識推論或外部分析費用。

## 回滾

獨立子目錄曾演練移出／移回；原站檔案與候選資產hash保持一致，無須重啟。需要撤回入口時，只移走本次子目錄：

```bash
mv guitarscribe/output/web-preview/site/reading-candidate-2026-11-05 guitarscribe/output/web-preview/reading-candidate-2026-11-05-withdrawn
```

目的目錄需尚不存在；恢復時反向移回。不要移動原站index/assets、不要reset工作譜。撤回後應由顧問撤下候選連結；原SPA對不存在路徑可能回原首頁，不能用HTTP404作為唯一撤回證明。

本段發布與驗證完成，交顧問形成必要的一次完整流程驗收。此入口不代表「任選歌曲即奏」已達成，也不把局部草稿覆蓋當作音樂通過率。
