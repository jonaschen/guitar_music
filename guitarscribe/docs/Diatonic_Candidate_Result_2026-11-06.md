# A21：固定自動估調＋調內硬限制未通過

日期：2026-11-06。[顧問事前方案](Diatonic_Candidate_Plan_2026-11-06.md)、[凍結計畫](evaluation/diatonic-ablation-plan-2026-11-06.json)、[逐來源數值](evaluation/diatonic-ablation-results-2026-11-06.json)。只重播既有九份開發／回歸快取，非未見保留集；零音訊模型推論／下載／產品修改。

三份HU33 root等權平均 **−2.628百分點**，**0/3**達到各+5百分點。所有HU33漏＋多和弦秒數都增加，控制組另有明顯退步；依事前規則停止這組固定介入，不調key／門檻／HMM，不加入I／IV／V行進，不交新的使用者A/B、不改線上預設。

## 原版與單變因工程證據

九份未改emission用原作者ViterbiPath重播，原path每frame index完全一致；全部raw事件（含相同標籤不同profile切換、最後timestamp的N）及historical／score projection逐項符合（時間容差1e-9）。這九份gate全部通過後，才各執行一次candidate。217個state、原init N=1、self=.99／off=(1-.99)/216保持；同一double二進位輸入，不換解碼器／索引／timestamp。

唯一改動是把調外profile emission歸0，其餘保留原值、不renorm；N永遠保留。全部24個bass／treble正值bin都算音級，bin0=A；小調profile須完整符合自然或和聲小調其中一套，沒有拼成八音集合。候選path無excluded state。

六份GuitarSet舊score／raw key=C major是舊基準欄位，沒有採作有效推估，也沒有讀reference key。對A12未改raw events按現行audio-intersection，以現行estimate_key_from_chords計算一次後凍結；候選後不反覆估key。這仍由原和弦回推、可能有循環與估錯限制，不能冒稱獨立調性證據。

14項工程測試通過：5個新案例驗A-origin／bass音、小調兩套而非union、N／空profile／索引、同名state事件與terminal N、作者C++ tie及mask合成；9個既有比較／回歸護欄測試。總計9次baseline＋9次candidate replay，耗時7.375秒，在原60分鐘／2CPU／循序上限內；不是18次音訊辨識。計畫、runner、作者原碼、wrapper、編譯器與全部trace／事件／原音訊／標註hash均在前後核符。

## 逐來源結果

root可評覆蓋九份皆100%；majmin只在其可表示域計分，覆蓋另列。Δ為百分點，漏多Δ為秒；分母沒有因candidate N或漏和弦縮小。

| 來源 | 固定key | 保留profile含N | rootΔpp | majminΔpp／覆蓋 | 漏＋多Δs | 邊界P／R Δpp |
| --- | --- | ---: | ---: | --- | ---: | --- |
| 00_SS2-88-F_comp | F minor | 55 | +0.213 | +0.310／68.745% | +0.000 | +3.158／+0.000 |
| 01_Rock1-90-C#_comp | C# major | 37 | +0.000 | +0.000／100.000% | +0.000 | +0.000／+0.000 |
| 02_Funk3-112-C#_comp | C# major | 37 | +3.885 | -86.533／12.500% | +1.486 | +6.566／-6.667 |
| 03_SS3-84-Bb_comp | Bb major | 37 | +0.000 | +0.000／87.498% | +0.000 | +0.000／+0.000 |
| 04_Rock2-142-D_comp | D minor | 55 | -0.343 | +5.496／81.250% | +0.000 | -7.143／-7.692 |
| 05_Funk2-119-G_comp | C minor | 55 | -4.462 | -4.607／49.991% | +11.610 | -6.429／-23.077 |
| SWD_HU33_04 | A minor | 55 | +0.055 | +9.256／81.051% | +2.926 | +8.113／+2.632 |
| SWD_HU33_18 | D minor | 55 | -9.851 | +3.621／80.320% | +7.802 | +3.715／-19.565 |
| SWD_HU33_21 | F major | 37 | +1.912 | -0.035／100.000% | +0.836 | +0.000／-13.333 |

Funk3的majmin由86.533%降到0，僅覆蓋4.286／34.284秒（12.500%），不能說全曲86.5%突然消失；root反而略升，仍不符合種類、漏和弦與邊界護欄。HU33_04雖majmin上升9.256百分點，但漏多增加2.926秒；HU33_18 root下降9.851百分點、漏多增加7.802秒。不能只報變好的一項。

以下是同全時間域的root救回／損失、原先可嚴格表示但被mask全排除的reference秒數（原本即無strict候選的秒數另存數值，不算本次排除）：

| 來源 | 改變label秒 | root救回／損失秒 | N增減秒 | 本次失去strict候選秒 | reference含調外音秒 |
| --- | ---: | --- | ---: | ---: | ---: |
| 00_SS2-88-F_comp | 0.511 | 0.093／0.000 | +0.000 | 2.727 | 2.727 |
| 01_Rock1-90-C#_comp | 0.000 | 0.000／0.000 | +0.000 | 0.000 | 0.000 |
| 02_Funk3-112-C#_comp | 11.529 | 1.703／0.372 | +1.486 | 4.286 | 6.429 |
| 03_SS3-84-Bb_comp | 0.882 | 0.000／0.000 | +0.000 | 0.000 | 2.857 |
| 04_Rock2-142-D_comp | 2.926 | 0.000／0.093 | +0.000 | 0.000 | 0.000 |
| 05_Funk2-119-G_comp | 21.409 | 0.046／1.486 | +11.610 | 2.017 | 12.101 |
| SWD_HU33_04 | 10.217 | 2.305／2.280 | +2.926 | 1.200 | 4.860 |
| SWD_HU33_18 | 18.344 | 0.315／4.499 | +7.802 | 1.180 | 11.760 |
| SWD_HU33_21 | 9.938 | 0.854／0.000 | +0.836 | 6.280 | 9.080 |

這些reference數值只在候選完成後作評估，沒有回饋改key或候選資格。硬限制可能同時排除合法調外和聲、轉位或原估調不合的和弦，本輪無法分離哪個是唯一原因。它只否決「這次固定自動估調＋完整profile調內硬限制」，不否定人工正確指定調性或所有功能和聲方法；後續若有不同機制，須另立證據與範圍，不能直接混入本輪補考。

## 產物與狀態

完整原始path／raw／診斷／before-replay manifest與編譯binary保存在 `output/evaluation/diatonic-ablation-2026-11-06/run/`；音訊、trace及compiled binary不公開。精簡結果保留兩路全域metrics／覆蓋／類別、邊界、固定key／舊key及全部overlay，完整逐區間與confusion留本機。跨機重評須先取得相同快取，不假稱repo附帶音訊或模型。

最終plan SHA256 `fd8dfba02d708689aa9824c74950760f82958603dcbcb244adb61a8537d21ba4`，runner `f6bbe95abb3cb9ce01d3e9d131ad9ae4ee3d046cf08693a8783198a12a744801`。顧問已獨立驗收：NumPy逐序sum重寫recurrence，全九份baseline及candidate每個index精確符合作者C++；另自行重算固定key、24-bin mask、raw events、18份完整diagnostic、所有來源／實作hash及停止決策均相同，沒有重跑音訊。證據 `output/evaluation/diatonic-ablation-2026-11-06/consultant-review.json`。候選停止，現有A19／A20閱讀與播放工具、原稿與人工修訂保持。
