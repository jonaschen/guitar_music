# Codex：第三來源固定流程檢查

日期：2026-10-25。使用者提供新影片並明確確認可進行本機分析；無需操作分析UI。

- 正規化來源：https://www.youtube.com/watch?v=0rpbhqZI0hc 。移除重複貼上的URL及播放清單參數，僅分析此影片。
- 網頁顯示標題為「庾澄慶 Harlem Yu / 情非得已〖歌詞〗」；標題不能證明錄音室來源或無混響。是否較乾淨仍待檢查／試聽。
- Job：`f303ec8a86834633b060920fa85430af`。
- 輸入範圍：前60秒，vocal模式、standard和弦、啟用既有分離。人聲分離與pYIN沿用服務設定，旋律離線使用凍結的 `decode_bounded`（G）。不啟用已拒絕的起音候選，不使用AnthemScore，不逐曲調參。
- 試聽範圍在新contour完成前固定為20–40秒及40–60秒；未依結果好壞挑選。兩段均保留，裁切邊界的音符只裁到片段範圍，不填休止、不伸縮。
- 檢查原音訊、人聲stem、contour的來源hash與時間原點，再核對G事件與compiler起訖／音高完全一致。不同歌曲間的短音比例只能描述輸出，不能當作準確率或回音因果證據。

## 交付方式

每段三個按鈕：原曲、分離人聲、G旋律。G沿用先前A的triangle音色與每聲部0.12增益，不用音色變化營造改善。保存原G與先前失敗案例，沒有覆寫既有修訂。

試聽入口：`http://localhost:5173/listening/third-source-2026-10-25/index.html`（完成渲染與頁面測試後才交付）。

回報只需：分離人聲有無明顯雜音／回音，以及G旋律的音高、拍長、連貫性是否可用。若仍明顯零落，不再無限換來源或逐曲修補；整理方法／適用範圍決策。


## 完成的工程檢查

Job由08:10:06至08:14:02 UTC，約3分56秒，包含下載與前60秒分析。G共260音，所有音符與compiler的音高、起訖逐項相符；stem hash與contour來源相符。

| 固定範圍 | G音符數 | 其中短於100ms | 短於10ms |
|---|---:|---:|---:|
| 20–40秒 | 112 | 59 | 0 |
| 40–60秒 | 109 | 57 | 0 |

短音仍很多，不能宣稱換來源已解決零落；也不能只靠音符數認定錯誤。上述片段數含裁切邊界，仍待集中試聽。

本次和弦設定standard，前失敗job為full，分析長度也不同；不可稱整個job設定完全相同。pYIN依vocal profile取人聲F0，不使用和弦或beat參數；G直接解碼contour，本次試聽不含伴奏。固定的是旋律方法，不是相同歌曲或完整實驗條件。

可重現入口：`backend/scripts/prepare_source_checkpoint.py` 讀取此job並建立hash與compiler核對；`frontend/scripts/render-source-checkpoint.mjs` 以先前A的播放器產生音訊。完整本機產物位於 `output/evaluation/third-source-2026-10-25/`；原音訊及譜未加入git。數值證據見 `docs/diagnostics/2026-10-25/third-source-results.json`。

播放頁工程驗證：Playwright 1 passed（3.9s），核對兩段各三軌、快速切換、互斥播放、全部停止與g-1.wav模擬404。初次測試誤用4173而拒絕連線，改用已運行的5173後通過；交付網址已確認HTTP 200。桌面畫面檢視完成。這些檢查不代表人耳驗收通過。

另一session的獨立來源／固定實作核對見 [Third_Source_Audit_2026-10-25.md](Third_Source_Audit_2026-10-25.md)。
