# Codex：外部辨識比較準備

查核日：2026-10-25。這是取樣與可行性盤點，未證明任何產品較準；不先開發API整合。

## 已準備的相同輸入

`output/evaluation/external-comparison-2026-10-25/`：

- `vocal-1.wav`：失敗曲原Bar8–15，17.940秒，3,164,660 bytes。
- `vocal-2.wav`：保存G原Bar28–35，14.466秒，2,551,852 bytes。
- `baseline-1.json`／`baseline-2.json`：同段目前G音符，相對片段零秒；不是正解。
- `manifest.json`：來源位置、音訊SHA256及大小。
- `comparison-inputs.zip`：上述資料與README，供本機審閱。擬轉譜輸入僅兩個WAV，不含整曲、資料庫、帳號或其他檔案。

## 最多兩個候選

| 候選 | 為何適合比較 | 免費與匯出限制 | 查得的付費價格與界線 |
|---|---|---|---|
| Sing2Notes／Klangio | 明確以主唱旋律為目標，可輸出未量化MIDI | Demo限20秒、只匯出PDF，不能預設免費拿到MIDI；需雲端上傳 | Instrument Pro官方比較表列US$14.99/月；實際結帳稅額／地區價格仍待確認，不選年繳、不自動購買 |
| AnthemScore桌面版 | 官方FAQ明列可辨識唱出的旋律；本機Linux版可比較另一辨識路線 | 官方下載頁稱不需帳號、預設Professional試用、每段最多30秒；首頁另列總計100次限制，首頁「unlimited」文案與此不一致，採較保守限制 | 官網當次顯示Professional US$39買斷；地區價格可能不同。免費試用的實際MIDI匯出須以執行結果確認 |

來源：[Sing2Notes](https://klang.io/sing2notes/)、[Klangio方案比較](https://klang.io/help/compare-apps-and-subscriptions/)、[Demo匯出限制](https://klang.io/help/difference-demo-full/)、[AnthemScore下載／試用](https://lunaverus.com/download)、[AnthemScore版本價格](https://lunaverus.com/)、[人聲支援FAQ](https://lunaverus.com/faq)。這些是廠商功能說明，不是本案品質證據。

## 實際執行界線

先查AnthemScore本機免費試用，因為可避免先上傳或付費。官方Linux下載216,013,304 bytes，存於專用cache，未加入專案依賴。當次試用執行檔拒絕 `--help` 與 `-a`，不能承諾無介面自動批次；已透過隔離Xvfb桌面完成兩段GUI分析及MIDI／CSV匯出，未繞過授權。試用版可完成本次短片段比較，但仍未證實可無介面批次整合。

桌面版亦可能傳送授權／更新識別資訊；不能把「本機辨識」誤寫成完全無網路行為。官方[隱私說明](https://lunaverus.com/privacy)區分桌面授權／更新資訊與線上服務的音訊儲存。

若轉至Sing2Notes，先由使用者決定兩段音訊的雲端上傳及任何付費，不因一般「繼續開發」而代購訂閱。免費PDF預覽只能作初步觀察，無法替代機器可讀事件比較。

## 一旦取得結果，如何判斷

保留原始MIDI／MusicXML，使用未量化MIDI作時間比較；若服務只能給量化結果，明確標記。只對齊已知片段零秒，不用逐音移動或任意伸縮去配原曲。與相同來源／相同G片段使用同音色、同增益播放，沒有證據就不做整合；需使用者一次集中判斷旋律音高、時值與連貫性。商業服務結果同樣不是正解。

## 本機實際結果（同日更新）

AnthemScore 6.3.0 Professional試用完成兩段：GUI顯示分析時間分別10.246秒、9.814秒（不含下載、啟動與匯出）。本次未購買、未註冊、未使用雲端音訊上傳服務。

- AppImage SHA256：`3e6b7758423c6b46e8b71dffa16f8b1cf09d295757c4d93227012c5fc257af9d`。
- 全片段、Find notes開；Auto instrument及Percussion detection關；未人工改音符。
- MIDI：transpose皆0、Constant tempo、Use musical (rounded) timing關。CSV另行原樣保存，不能預設CSV時間就是未量化時間。
- `anthem-1.mid/.csv`、`anthem-2.mid/.csv` 保留外部原始輸出；所有音高／重疊聲部保留，不挑最好聲部或逐音修補。
- 比較使用相同triangle音色、每聲部0.12增益、固定velocity，保留休止、起訖及重奏；不拉伸或人工對齊時間。人聲為原片段。
- 現有G來自整曲分析；外部工具輸入短片段。這是成本受控的方向判斷，不能據此宣稱跨曲勝率或整曲精度。

試聽僅需兩組，判斷音高、拍長與連貫性。結果尚待人耳判斷，音符數較少不等於較正確。伴奏未在此次更動或驗收。


### 匯出核對與已知限制

兩段分別43、47音，MIDI與CSV的音高數量相同，全部起音在1個MIDI tick內一致（最大0.259ms）。這只證明兩種匯出相符；CSV不含音尾，不能驗證時值保真。

GUI log明列 `RhythmQuantize`、`grid 8/beat`及各一次beat repair。即使MIDI匯出未勾選rounded timing，也不能稱為保留原始聲學起訖的未量化結果。本比較明確採用工具實際輸出的節奏，不另修正。

最大同時音數為3／2；各有一處同音重疊note-on，解析採FIFO且保留歧義紀錄。片段1最後音尾19.866秒（來源17.940秒），片段2最後音尾14.949秒（來源14.466秒）。兩條合成比較軌均延長至該組最晚音尾加100ms，未刪去外部的超長尾音；原人聲保持原長度。

## 重現與驗收入口

1. 原始輸入hash見 `docs/diagnostics/2026-10-25/external-inputs.json`，外部輸出與匯出設定hash見 `external-midi-inspection.json`；音訊、原始MIDI、截圖及log留在本機evaluation資料夾，不加入git。
2. `python backend/scripts/inspect_external_midi.py INPUT.mid --csv INPUT.csv --output NEW_DIR` 匯出原始事件與獨立核對報告。解析器6項手寫fixture測試通過。
3. 把已核對事件以 `anthem-1.json`、`anthem-2.json` 保存於比較輸入資料夾；於frontend執行 `node scripts/render-external-comparison.mjs`。需本機Vite 5173，產生固定兩組音檔及渲染hash；不修改工作譜。
4. 試聽網址：`http://localhost:5173/listening/external-checkpoint-2026-10-25/index.html`。每組依序「原人聲 → A → B」，只回報較接近者，或「都不好」。可分別指出音高／拍長／連貫性，不需逐音標註。

A為現有G，B為AnthemScore匯出。同一組使用相同音色及每聲部音量；外部多聲部可能使總音量較大，不能把較響誤當較準。此試聽是辨識方法判斷，不是新UI或整個產品驗收。

工程驗證：起音／評分既有控制13 passed；獨立MIDI解析6 passed；比較頁Playwright 1 passed（17.8s），涵蓋兩組六按鈕、快速切換、互斥播放、全部停止及模擬404音檔。桌面及窄螢幕截圖檢查完成。工程結果不代表聽感已通過。


## 使用者試聽回饋與來源測試決策

使用者回覆：「A 還是比較接近，但是似乎太敏感了，似乎受一些麥克風的回音影響」，並願意提供其他來源。

- A是現有G，B是這次AnthemScore比較版本，與早期已認可的伴奏B不同。
- 這是整體偏好，使用者未分別評定兩組；不推論兩組均通過，也不視為A達到可用標準。
- 本輪沒有支持替換為AnthemScore的證據，停止其產品整合。使用者提出回音假說，尚未證實；分離殘留、F0換音邊界及音符切分仍是其他可能因素。
- 接受一次固定參數的新來源測試，保留目前G，不重新啟動能量谷候選或逐曲調參。

下一份輸入只需一個連結或音檔；有方便的話提供20–40秒代表段落，否則由Codex選段。優先同一首歌較清楚、回音較少的錄音，便於減少曲目差異；沒有同曲版本時，另一首主唱清楚的歌也可，只能評估不同來源的適用性，不能據此證明回音是根因。不要求使用者製作音符正解或先操作產品。

收到後固定現有流程，保留來源hash及原點，依序檢查原音訊、人聲分離、F0與音符事件，與目前失敗片段並列，不覆寫舊譜。工程檢查完成後才提供最多兩組簡單試聽。若較清楚來源仍明顯零落，下一步討論方法／產品範圍，不無限更換歌曲尋找成功案例。
