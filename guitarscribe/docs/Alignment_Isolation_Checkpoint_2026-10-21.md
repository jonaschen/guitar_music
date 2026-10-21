# 合奏驗收失敗後的分項定位 · 2026-10-21

使用者對原曲／G 合奏回報「有明顯錯位」。合奏音樂跟隨驗收**未通過**；先前排程回歸只驗證實作符合保存資料，不能證明資料本身的節拍、和弦或編配正確。已通過的 G 獨聽保留，本輪沒有修改產品播放程式、G 音符、拍點或和弦。

## 查證

- helper-session 核對來源鏈：分析來源逐取樣等於原檔去掉 18 秒；本次 source.wav 逐取樣等於該來源的 Bar28–35 裁切。舊 eval source 與本次僅增益／PCM 量化不同，相關係數約 0.999999997。沒有選錯段落或重複 crop 的證據。
- partner-session 與主線分別核對編譯事件。Bar30、31、32 分別長 1.8576、1.6254、1.8460 秒；Bar31 局部壓縮確實存在於保存拍點，編譯忠實跟隨。這仍可能是實際速度變化、拍點偏差或拍位跳轉，未由音訊確定。
- Bar30 第3拍 G→Em 的保存邊界為 54.6017 秒；刷奏型該格空白，Em 第一刷為 54.8223 秒，約晚 221ms。這是既有「等下一刷換和弦」語意，不能直接當成 bug 改掉。
- 原曲與分離伴奏在 47–67 秒的 HPSS／onset strength 離線核對：Bar31 第3拍最近聲音起音約早 102–107ms；前後小節多數拍點接近聲音起音。然而伴奏在 Em 邊界附近的最近起音約為 54.7903 秒，反而接近延後刷奏。聲音起音不等於正拍，也不能辨認和弦名稱，因此不支持直接平移整段或強制讓和弦邊界立即起奏。

可重現的純讀取稽核入口：

```sh
python3 guitarscribe/backend/scripts/audit_saved_alignment.py --revision db8c657e-62a5-4fad-a33e-cde25a9e1c0d --output guitarscribe/output/evaluation/alignment-audit-2026-10-21/audit.json
```

它核對每小節拍距、和弦邊界到第一刷的差值、manifest 旋律是否與保存音符一致，以及修訂前後是否不變。聲音起音探索的程式與結果另保存在同一 ignored output 目錄，不當成已驗證的 beat detector。

## 下一個唯一人工判斷

使用者對「有明顯錯位」的可選補充問題不構成工程阻塞；不要求其重聽或找出精確小節。改以同一段原曲同步疊加兩種聲音：

1. 原曲＋保存拍點的節拍聲。
2. 原曲＋保存和弦與刷奏型的吉他。

兩段都是問題定位控制，不是改善候選。原曲與添加聲音在同一 OfflineAudioContext、同一零點合成；沿用產品 `createMetronomeVoice` 與 `createPluckedVoice`，未另建辨識／和弦演算法。移除 G 合成旋律這個變項，先分辨拍點與和聲。

本機連結：http://localhost:5173/listening/alignment-isolation-2026-10-21/index.html 。按「依序播放兩段」，約30秒。只回報哪段明顯不對：**1／2／兩段／兩段都還好**。

若只有1或兩段都錯，優先查拍點；若1可用但2不對，優先查和弦及刷奏；若兩段都還好，再查G旋律與合奏的相對關係。這是診斷順序，不是由單項聽感直接判定唯一原因。不將任一改動寫回已保存G。

## 產生與驗證

frontend 目錄執行：

```sh
node scripts/prepare-alignment-isolation.mjs db8c657e-62a5-4fad-a33e-cde25a9e1c0d
```

需要既有 ensemble packet 的相同 source.wav／config、目前 UI/API。產物為 ignored `public/listening/alignment-isolation-2026-10-21/` 的兩個 WAV、頁面與 report.json。兩檔各318976 frames／22050Hz，約14.466秒；來源固定增益0.45，節拍32個、吉他288個聲音事件，峰值約0.563／0.577，無削波。產生前後保存譜逐欄相同。未修改產品程式，無須重跑全部產品回歸。

瀏覽器自動驗證兩檔各14.466032秒、依序切換、互斥播放、停止及重播均通過，無 pageerror；已檢視簡化頁截圖。人類音樂判斷尚待上述單項回報。
