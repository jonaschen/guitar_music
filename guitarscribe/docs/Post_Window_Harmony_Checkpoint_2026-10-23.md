# 後段拍點與和弦切分核對 · 2026-10-23

使用者在Y延伸後回報「又開始偏掉」，詢問是否因硬切太多和弦。記錄為**延伸候選失敗**，不動局部Y偏好，不再用全段快慢／固定偏移追趕錯位。使用者授權繼續；本輪只做唯讀診斷與隔離試聽，未寫保存譜。

## 三項交叉核對

helper-session核對64.423764–71.877370秒：12筆region合併成5段，C(4拍)、D(2)、Am(2)、G(2)、C(6)，共24刷。連續同名處指型及音高相同，不因原始region重設刷奏phase。Am及後段C邊界在第3拍空刷，第一次新和弦刷奏分別較保存邊界晚約209ms、226ms。

partner-session以固定librosa起音設定比較16個拍點，沒有調參挑結果：

| 來源 | 原拍點最近起音中位絕對差 | +378.641ms候選 |
| --- | --- | --- |
| 原曲混音 | 8.53ms | 76.88ms |
| 分離伴奏 | 14.69ms | 81.27ms |

起音不等於音樂拍點，密集起音／弱拍可能造成歧義，不能稱為節拍真值或整段已過關。但不支持把前段Y的累積位移帶入後段，因此本次固定原保存拍點。

主線新增可重現的`backend/scripts/audit_harmony_evidence.py`，對原曲與分離伴奏直接計算CQT及STFT chroma，不按beat切分或重跑和弦decoder。記錄每個保存和弦內部的模板偏好與前後120ms持續跨越；不將結果當精確邊界。

關鍵疑點為 **67.256598639–68.185396825秒、chord-96/97的Am**：

| 來源／表示 | 區間首選 | 保存Am排名 |
| --- | --- | --- |
| 原曲 CQT | Am | 1 |
| 原曲 STFT | Am（與C接近） | 1 |
| 伴奏 CQT | D（0.878） | 9 |
| 伴奏 STFT | D（0.799） | 17 |

相鄰原D區段兩軌兩種表示都以D為首選。這支持「可能受人聲影響、D被切成短Am」作為候選；分離也可能移除真實和聲，且兩種chroma不是獨立真值，**不能直接刪掉Am**。C/G等其餘轉換亦未因此被宣告正確。

## 僅改一次和弦的控制

`frontend/scripts/prepare-harmony-count-probe.mjs`固定原revision及manifest hash，在記憶體副本中僅將chord-96/97從Am改成前段D的同一指型；仍由正式manifest API編譯，不加時移、不放慢，不沿用失敗的Y外推。

- M：原C→D→Am→G→C。
- N：同時間／同刷奏安排，讓D延續兩拍，再進G→C。

所有刷奏事件的start與stroke逐項相同，非吉他事件完全相同；只有目標內3刷的音高變化及合併D後的end/sustain改變。指型由Am的5弦變D的4弦，因此完整渲染弦音383→380，音量沿用產品每刷按弦數平方根正規化；不能說逐根弦數或包絡完全不變。這是實際和弦／指型控制，不是純粹刪除刷奏。

兩版取分析65.5–70.5秒，加350ms尾音，共各5.350秒。前1.9秒及3.1秒後波形在1 PCM16 LSB內相同，差異只在目標附近。峰值0.545／0.548無削波、末500 samples在1 LSB內為靜音；每根弦實際起音逐筆檢查。Chrome驗證M→N播放順序／結尾、重播、停止、中途切換，無pageerror。保存譜與來源hash前後不變。

初次產生器因手填預期起點最後兩位小數與保存值不同而拒絕；已改成API的精確值67.25659863945579，沒有放寬版本／錨點保護。修正後全部上述檢查通過。

## 唯一人工項

http://localhost:5173/listening/harmony-count-2026-10-22/index.html

按「依序播放 M → N」，約12秒。回報 M更貼合／N更貼合／差不多／都不對。不要求找拍點或秒數、不再比較速度。

若N較好，只支持這處Am或其和聲持續方式不合適，不支持全段刪減和弦，也不驗收整首。若相近／都不對，保留不確定性，回到來源和聲與刷奏語意，不直接套N。

## 重現

repo根目錄：

```sh
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/audit_harmony_evidence.py \
 --revision db8c657e-62a5-4fad-a33e-cde25a9e1c0d --start 62 --end 73 \
 --output guitarscribe/output/evaluation/post-window-audit-2026-10-22/harmony.json
```

frontend：`node scripts/prepare-harmony-count-probe.mjs`。來源沿用既有pace-continuation packet的原曲音檔，不沿用其合成吉他。

ignored報告：`output/evaluation/post-window-audit-2026-10-22/{structure.json,beat-audit.py,beat-audit.json,harmony.json}`；音訊與生成report在`frontend/public/listening/harmony-count-2026-10-22/`。目錄沿用開工日期10/22，驗證及文件完成於10/23。產品程式、G與保存資料未變，未重跑無關的產品回歸測試。
