# Codex：另一來源的伴奏拍長對照

2026-10-27。已收到人耳回覆：「感覺都蠻好的 我聽不太出來差異」。結論為兩版初步可接受、無可辨識差異；不宣稱 B 較好，不改全域預設，不要求重測。以下試聽計畫保留為歷史紀錄。

小手拉大手的八分拍格候選獲「有好一點了」；本次固定另一首《情非得已》現場來源原曲 10–40 秒。先寫 protocol，再生成。A 使用先前 continuous 演奏，B 使用同一 continuous 規則＋nearest-eighth-v1 邊界。不重新辨識、不改和弦標籤、拍點、旋律、音色或個別正規化。

注意這是隔離時值影響的診斷；工作區套用時會回到原版刷奏，所以本對照不代表工作區預設演奏通過。整理後首刷、延音與安全略過判定可能隨時值改變，沒有另外切換演奏方案。

A manifest 事件與先前 continuous B 完全相同，renderer 驗證 PCM 差異不超過一個量化單位後重用舊 WAV，hash 相同。兩版 sourceGain=0.45、guitarGain=0.88929955445293、commonGain=1，各 450 弦音；完整譜各 118 刷奏事件。

自動檢查：原輸入未改，旋律、拍點、和弦非時值屬性保持。WAV 無削波、尾音結束，各 30.35 秒含尾音。MIDI 各 1480 個音符開關事件，與 manifest 最大誤差約 1ms。瀏覽器確認音檔解碼、播放互斥、跳轉 22 秒、窄版面及無頁面錯誤。網址必須帶 index.html，Vite 的目錄網址會回主工作區。

## 唯一待驗收

http://localhost:5173/listening/grid-cross-source-2026-10-27/index.html

A、B 各聽一次，回覆「A 較自然合拍／B 較自然合拍／差不多／都不對」。聽不清楚可直說；秒數為選填。不追加 UI 或旋律測試。

B 退步則不推廣；差不多則不為求偏好而調參；改善也只記固定片段證據，不宣稱通用抓歌完成。全域預設不變，旋律仍未解決。

[固定計畫](diagnostics/2026-10-27/grid-cross-source/protocol.json)、[處理報告](diagnostics/2026-10-27/grid-cross-source/report.json)、[渲染](diagnostics/2026-10-27/grid-cross-source/render-report.json)、[瀏覽器](diagnostics/2026-10-27/grid-cross-source/browser-check.json)、[MIDI](diagnostics/2026-10-27/grid-cross-source/midi-check.json)。音檔留本機，不加入 git。

重現：backend/scripts/prepare_grid_cross_source_review.py 拒絕覆寫輸出；使用 frontend/scripts/render-chord-attack-diagnostic.mjs，輸入本次 evaluation 目錄、slug grid-cross-source-2026-10-27、模板 scripts/grid-cross-source.html。
