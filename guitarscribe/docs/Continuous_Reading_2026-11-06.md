# 無局部拍格時的連續和弦閱讀

日期：2026-11-06。[盤點與驗證數值](evaluation/continuous-reading-results-2026-11-06.json)。本輪改善閱讀，不更正拍格或和弦。只有reading-candidate入口改預設，正式首頁保持。

## 兩首最新歌曲的只讀盤點

- 《沒那麼簡單》job `a3be29912a7045448765290d7cba2f6c`，304.472秒、165和弦、unmetered。現有局部preview為0、`no_agreeing_local_bars`。primary789拍／candidate479拍，primary median間隔0.30秒；158個重拍間候選中沒有單一bar同時過全部條件。非加總拒絕計數為3／4脈衝以外118、全局密度69、局部密度變化43、beat decoder不一致135、downbeat不一致27。3.88–11.0秒雖原有四個3拍bar，但約0.58–0.60秒間隔相對全局0.30被密度保護拒絕；281.8–292.72秒另有decoder變拍。缺共同可信拍格，不是調性是否相同的問題；這首推估F#；使用者另回報與自抓調性一致但未點名曲目，暫對應latest亦不是獨立標註或全曲伴奏驗收。
- 《天后》job `d8858077556b4403a5d00cb2c9e03a99`，322.553秒、146和弦、unmetered；已有4個region、74個bar／218.56秒可呈現：0.12–118.70（40bar）、121.64–148.24（9）、180.70–236.50（19）、274.66–292.24（6）。其他區段仍未知，不能擴充成全曲小節。

只重用兩份timing-recovery／rejection／health，沒有重跑模型或逐曲改規則。先完成盤點，再依使用者回報改善通用閱讀fallback；沒有調全局density保護或新增拍格候選。

## 閱讀行為

reading-candidate路徑不帶timingView也預設auto；有可用region仍用既有局部小節草稿，沒有則用連續和弦文字自然換行。沒有固定每列幾個和弦、推定段落、小節或等長格子；畫面明示「小節未確認」。文字與時間以留白排列，無卡片外框／圓角，只有hover／focus／active底線。

每個原和弦完整保留，包括同名重複、短和弦、slash與起訖；時間可見，title另有毫秒。偵測沒有標記的leading／中間／尾段顯示「未標和弦」，不冒稱原曲休止；明確N／NC保留名稱並標休止。這些時間也可點選seek，未合併或刪除資料。

「時間明細」可回原table；明確URL的time／table選擇及當前使用者選擇保留。編輯時顯示table，完成回原閱讀選擇；不更換歌曲、不重置播放選項。既有current／next、active、跟隨、跳轉與loop沿用；view切換不停止聲音、不重編manifest。晚到preview不能覆寫已選table，新job不會套舊job的preview。

原首頁無query仍是原table；正式有拍格的頁面、拍點可用條件、A19音量／根音／合奏及原始播放事件不改。沒有拍點的歌仍不能用閱讀排版冒充每拍演奏。

## 驗證及發佈狀態

TypeScript及21項必要UI回歸通過：320／390／1440、原局部預覽／明細編輯、missing／malformed／late preview／newjob與Undo、長譜中段seek後pause、跟隨可關閉、無query候選auto、明確time／table、短音／同名／N／未標區段全保留、view切換不新增manifest編譯或改score。沒有重跑不相關後端或模型。

兩真job發布前的原score／input.wav／base manifest SHA256保存在 `output/evaluation/continuous-reading-2026-11-06/sources-before.json`，發布後另核。顧問真job瀏覽器審查通過：無query自動compact165和弦／天后partial146個不同id、四尺寸無溢出、明確time遵守、編輯回原閱讀；view切換前後score POST及manifest完全一致，0使用者寫入／0頁面例外。證據 `output/evaluation/continuous-reading-2026-11-06/consultant-review.json`；最終候選build通過，19個必要檔；顧問截圖後要求hover中性、橘色只給current，已修正並重新build，發布待補。只更新同候選前端，不需重啟API；ngrok及正式首頁不動。
