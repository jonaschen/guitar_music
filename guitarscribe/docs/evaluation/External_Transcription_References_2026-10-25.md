# 現成轉譜工具：作比較系統，不把宣傳當成真值

使用者建議參考YouTube自動吉他譜軟體。本輪查核官方資訊，未登入、購買、上傳或取得第三方轉譜結果。此研究不阻塞現有試聽交付，也尚未證明任一服務比本專案準。

| 工具 | 官方能力說明 | 用於本專案比較的限制 |
|---|---|---|
| Guitar2Tabs／Klangio Studio | YouTube／音訊輸入；TAB、量化與未量化MIDI、MusicXML、Guitar Pro匯出 | 官網提供20秒demo；完整可機讀匯出與demo權限需區分，不把PDF當精確時間標註 |
| Songscription | YouTube／音訊轉譜；吉他TAB、MIDI、MusicXML、Guitar Pro | FAQ列免費30秒，Plus含匯出；吉他等非鋼琴仍標beta，混音較難 |

來源：[Guitar2Tabs官方](https://guitar2tabs.klang.io/)、[Klangio產品](https://klang.io/products/)、[Songscription官方FAQ](https://www.songscription.ai/faq)。避開搜尋結果中相似名稱的非官方網域。免費短片與完整版品質／匯出權限不能混稱。

Klangio另有[音樂轉譜API文件](https://api-docs.klang.io/)與[方案頁](https://klang.io/api/)，可研究beat/downbeat、和弦及刷奏能力。需API存取，尚未取得有效憑證或實測權限。不要混用另一家`klang.ai`的語音API。

固定比較方式：使用相同音訊片段／聲部目標／時間原點，保留第三方原始匯出、模式、版本、成本與人工設定；未量化MIDI評音符音高／起訖，量化輸出另評記譜，不混為來源時間正確率。完整混音與分離吉他必須分開標記，主唱旋律改編成吉他譜也不能冒充原曲吉他聲部轉錄。先以可核對標註的公開實錄檢驗，再用使用者原曲作聽感比較。

若第三方表現穩定且成本可接受，可評估外部辨識＋本專案編輯／播放／匯出的分工；現階段沒有品質證據，不能先承諾整合。使用者已表示這是參考方向，仍以完成目前可驗收版本為主。
