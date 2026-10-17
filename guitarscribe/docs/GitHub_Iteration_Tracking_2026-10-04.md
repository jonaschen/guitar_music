# GitHub 迭代追蹤

使用者已授權發布 issue，2026-10-04 已建立並核對：

| Issue | 優先序／狀態 | 驗收目的 |
| --- | --- | --- |
| [#6 總追蹤](https://github.com/jonaschen/guitar_music/issues/6) | 迭代控管 | 每次 checkpoint 記錄 commit、工程測試、聽感、下一步 |
| [#2 器樂主旋律](https://github.com/jonaschen/guitar_music/issues/2) | P0 / 待 MELODIA 聽感 | 隔離 benchmark 工程子項完成；I1／I2 停止調參，未關閉 issue |
| [#3 時間軸與合奏](https://github.com/jonaschen/guitar_music/issues/3) | P1 / 待來源可辨認 | Bar 30–31 前後小節／旋律／和弦一致 |
| [#4 候選編輯整合](https://github.com/jonaschen/guitar_music/issues/4) | P1 / 下一個產品 checkpoint | 比較、明確接受、獨立保存，不覆蓋人工修訂 |
| [#5 品質 gates](https://github.com/jonaschen/guitar_music/issues/5) | P1 / 持續 | 區分來源／分音／拍點／產品操作，累積跨歌證據 |

不自動關閉任何 issue；單次 benchmark 完成只能勾工程子項，不能代表音樂驗收通過。Issues 是持續追蹤入口；本地 `docs/issues/` 是初始發布內容，後續狀態以 issue 留言與總追蹤為準。

WIP 限制一個主要辨識假設。每輪工程可重現 → 短片段人工聽感 → 有改善才擴段及整合；失敗即記錄停止，不靠無限微調維持虛假進度。維持「充分辨識歌曲 → 忠實轉譜 → 人工可修 → 同步播放與匯出」的產品方向。


## 2026-10-17 本地 checkpoint：旋律連續性

使用者回報普遍零落／音長不自然，其他部分尚可；當前優先處理播放連續性，再依聽感判斷辨識切分。固定 G，不覆蓋修訂。新增連續／逐音對照、移除旋律最短播放限制；63 項回歸與 2 項真實 G 驗證、型別／建置通過。唯一待人工項為同段短試聽，不能因此關閉品質 issue。詳見 [旋律連續性 checkpoint](Melody_Continuity_Checkpoint_2026-10-17.md)。本節為本地紀錄，未同步 GitHub。

## 2026-10-17 本地 checkpoint：G 與編輯器版本一致性

使用者澄清 G/H 試聽都不錯，編輯器結果較差，並肯定簡單試聽頁。停止擴大切分候選；修正明確保存／恢復修訂後重整卻回原分析的流程，以 revision URL 固定版本。partner-session 審查播放與競態，helper-session 提供 7 項版本連結回歸，主線完成整合與真實編輯器音訊排程驗證。詳見 [編輯器 G 一致性](Editor_G_Parity_Checkpoint_2026-10-17.md)。不是 H 勝出、不是全部音樂品質通過；未同步 GitHub。
