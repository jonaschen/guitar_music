# 固定局部 Y 與後段銜接 · 2026-10-22

**後續驗收失敗：**使用者回報「又開始偏掉」，並懷疑過多和弦切分。此延伸候選不得升為預設或繼續外推；局部Y偏好仍保留。後段原拍點比+378.641ms更接近兩軌起音，主線已回到和聲切分核對，見 [2026-10-23 checkpoint](Post_Window_Harmony_Checkpoint_2026-10-23.md)。以下為歷史工程紀錄，試聽不用重做。

使用者明確更正：「由快到慢，而且也是最不合拍到最合拍」。因此速度X>Z>Y，**合拍Y>Z>X**。Y為以B為基準、從分析54.957732426秒起起奏間距1.04的局部偏好，沒有證明整首應放慢。

## 銜接風險

partner-session用真實manifest確認：原測試終點64.423764172秒映射為64.802405442秒，累積378.641ms。最後F上刷由64.226395移到64.597141秒；下一個原C首刷在64.423764秒。直接接回原時間會先C再F，破壞和弦順序。只移C首刷會使它與下刷只隔約74ms，也不是已獲偏好的結果。

因此沒有把Y硬接或寫回原修訂。`LocalGuitarTiming`使用連續映射：anchor前不動、anchor到end間縮放、end後保持累積位移並恢復原間距。**後段固定平移政策是新增的診斷假設，未被前輪Y排序驗收。** 沒有宣稱它是正確全曲時間軸。

## 工程交付

- `accepted-pace-recipe-2026-10-22.json`固定原score revision、基底manifest、B候選hash、兩處首刷修正及局部伸縮窗口。
- Backend評估函式建立獨立manifest hash，保留音高、弦間offset、力度、刷向及所有非吉他事件；過期版本、非有限／越界參數、無效窗口、截斷刷弦拒絕。來源／score與B保持不變。
- 仍由相同candidate manifest匯出MIDI；這是evaluation checkpoint，未新增SongScore欄位、未啟用產品預設、未保存新revision。後段所有吉他會帶固定偏移，不能把完整產物標成整首已通過。
- 助手新增獨立單元測試；主線審核發現兩個預期算術錯誤及一個超範圍fixture，請助手修正後再執行。43項相關測試通過。
- 真實MIDI獨立解碼5558個note-on，音高／力度相同、起音與manifest相差不超過1tick；吉他事件順序一致、旋律與metronome逐事件不變。

重現（repo根目錄；輸出目錄必須不存在，保護既有產物）：

```sh
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/build_strum_checkpoint.py \
 --recipe guitarscribe/docs/accepted-pace-recipe-2026-10-22.json \
 --output guitarscribe/output/evaluation/accepted-pace-2026-10-22
```

已有產物時請保留並改用新目錄，不覆蓋。播放候選manifest及performance.mid位於上述ignored目錄。

## 唯一人工項：新的後段銜接

http://localhost:5173/listening/pace-continuation-2026-10-22/index.html

播放約18秒，留意**第10秒以後**。回報仍跟得上／又開始偏掉／不確定；若明顯可補太早或太晚。不重測已完成的X/Y/Z排序。

前段保留Y，後段增加4小節至原Bar40起點。原曲固定，既有來源PCM前綴逐byte相同。Y前9.4秒（舊片fade前）與前輪音檔在1 PCM16 LSB內一致；不能比較原片末尾淡出與新的後續音樂並要求整個WAV相同。完整音檔17.648秒、408個弦音逐筆排程核對、峰值0.523無削波、末500 samples在1 LSB內為靜音，Chrome播放／重播／停止無錯誤。

frontend重現：

```sh
python3 scripts/prepare-ensemble-listening.py --revision db8c657e-62a5-4fad-a33e-cde25a9e1c0d --last-bar 39 --packet-name pace-continuation-2026-10-22
node scripts/prepare-pace-probe.mjs --continuation
```

產生器會核對完整後端candidate與recipe逐事件相同才渲染，來源與保存譜前後不變。生成音訊使用同一產品pluck合成函式，不依瀏覽器playbackRate變速，不改原曲或音高。

若後段仍偏，保留局部Y結果，重新核對伸縮終點／後段拍點；不能藉再次全局平移掩蓋局部誤差。正式編輯器保存及播放／匯出一致的時間修正功能仍待此銜接語意收斂。
