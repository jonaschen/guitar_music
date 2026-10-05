# 本輪集中測試：八小節修譜與譜面

目的：確認既有分析可以被可靠地人工校正、保存及讀譜。主旋律自動辨識尚未解決，本輪不要求重新分析或再次比較旋律候選。

## 前提

2026-10-05 本機服務以程式碼唯讀掛載模式啟動，保留已測試 backend 映像的分析依賴。完整重建因會重新安裝基礎系統／依賴而主動取消；沒有將未完成的 build 當成部署成功。已驗證實際 health、MusicXML 調音／附點／和弦、旋律時間與 MIDI header，且 demucs／torch／yt_dlp 仍可用。合成 smoke 不建立 jobs 或 revisions。

若之後需要重新啟動，在 guitarscribe 目錄執行：

```bash
docker compose -f docker-compose.yml -f docker-compose.code.yml up -d --no-build
```

此模式掛載 backend/app、scripts、tests 為唯讀，既有 output 與設定沿用主 Compose；Python 程式更新後需 `docker compose restart backend`，依賴改動則仍需完整建置。若不帶 code override 重新建立 backend，會回到舊映像內的程式，不能視為本輪修正已部署。

部署後另以 `GUITARSCRIBE_LIVE_SMOKE=1 GUITARSCRIBE_UI_URL=http://127.0.0.1:5173 npx playwright test e2e/musicxml-render.spec.ts` 驗證目前服務的 1280px／390px 預覽，兩項通過。分析 job 回應仍使用合成 fixture，MusicXML 由實際 8000 API 產生；不宣稱既有歌曲來源音訊已驗證。

- 以既有歌曲及自己的最新修訂測試；先記下原修訂 ID。
- 小節分界使用分析後的秒數，不是 MV 原始時間。若分析前略過 19 秒，不要再額外減一次。
- 修訂與來源音訊分開：舊 job 若已失效，仍可能載入修訂，但不能憑修訂恢復原曲音訊。遇到此情況請回報，不必為測試重新分析整首。

## 約 5–10 分鐘

1. 開啟 `http://localhost:5173`，重新整理並載入原歌曲／修訂。
2. Melody editor 選 Bar 28、8 小節（或任意有完整拍點的中段）。展開「所選小節分界校正」，用原曲按鈕確認時間能定位；不需精準判斷整首。
3. 先選一個內部分界，試改 +0.1 秒 → 套用 → Undo → Redo。這只測試操作，不代表 +0.1 秒是正確修正。先不要勾各拍等分。
4. 任選一個音符改品格或音長，Apply note，再「重播所選小節」。確認畫面留在編輯區，且能撤銷回原版本。
5. 確認要保留的修改後 Save new revision，記下新 ID；Undo 後 Load melody revision，確認音符與小節分界都恢復保存值，原 ID 仍可另行載入。
6. 展開「Melody & Tab previews · Experimental」，查看 Notation & Tab 不再空白；和弦、品格、延音線應可見。若手邊有手機或窄視窗，確認預覽不撐出畫面。

不需要為這次測試特別安裝第三方讀譜軟體。MusicXML／MIDI 可下載留存，但譜面沒有經過實曲完整驗收；不要用它判定來源旋律已辨識正確。

## 回報三點即可

- 八小節的定位／修改是否順手？哪一個操作仍容易迷路？
- Undo、另存與載入後，修改內容是否保持一致？
- 譜面是否可見、有沒有位置或音長明顯不合理的地方？可附截圖與小節號。

## 後續界線

本輪不宣稱八小節合奏編輯全部完成：旋律編輯器的重播仍是旋律試聽，完整旋律＋伴奏仍由 Compiled score playback 控制。後續需把段落合奏更直接整合到編輯區，並處理和弦事件時間編輯。自動辨識問題保留 #2，未關閉。
