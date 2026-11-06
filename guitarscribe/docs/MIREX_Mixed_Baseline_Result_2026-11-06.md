# A17：兩首完整混音的原版辨識基準

日期：2026-11-06。[事前方案與授權署名](MIREX_Mixed_Baseline_Plan_2026-11-06.md)、[凍結計畫](evaluation/mirex-mixed-baseline-plan-2026-11-06.json)、[逐來源數值](evaluation/mirex-mixed-baseline-results-2026-11-06.json)。兩首示範原MP3下載、兩次原版Chordino與診斷已完成，總耗時25.22秒；產品辨識未改善，沒有候選或試聽交付。

## 結果與可評範圍

| 來源 | 評分長度秒 | root／覆蓋 | majmin／覆蓋 | 完整label相同秒 | 錯根音秒 | 同根音品質錯秒 | 邊界P／R |
| --- | ---: | --- | --- | ---: | ---: | ---: | --- |
| You were a puppet master | 253.314717 | 91.730%／100% | 89.816%／93.877% | 192.134 | 20.762 | 39.999 | 70.000%／85.556% |
| Electra Glider | 357.000000 | 58.908%／100% | 57.642%／99.160% | 75.550 | 145.745 | 134.753 | 13.389%／84.211% |

majmin不是完整和弦正確率：對可評大小調類別作投影，且兩首分別有15.51／3秒不在該評分域，不能把它們當全曲分母。完整label保留擴展音與slash bass語義；正確無和弦另為0.232／0秒。puppet多和弦0.188秒、漏0；electra多0.720秒、漏0.232秒。完整類別加總及逐區間秒數均守恆，沒有未知reference或estimate label。

Electra有239個估計轉換對38個參考轉換，32個在250ms內配對；207個額外邊界，不能因recall高便說切換正確。錯根音145.745秒中140.780秒在轉換容差窗外，134.349秒的估計根音仍是參考和弦音。最大錯根音組是A:maj7→C#:min33.344秒及A:maj7(#9,13)→C#:min14.768秒；另有A:maj7→A:maj35.524秒的品質遺失。這是長時間和聲內容混淆，不只邊界抖動。

puppet錯根音20.762秒中12.422秒在轉換窗外；其中C#:min/b3→E:maj7／E:maj6共6.134秒。同根音錯誤包括B:maj→B:maj6 8.783秒、G#:min(#4)→Ab:min6.2秒。增減擴展音及共同和弦音的根音混淆並存，不能用一條固定移根規則處理：Amaj7與C#min、C#min與Emaj各自都可能是正確和聲。

## 時間、來源與工程核對

兩首audio_offset均0，不平移或對答案對齊。puppet解碼44100Hz實長253.3147165533秒，原參考尾253.33秒僅共同裁去0.015283秒；electra實長與參考均357秒。原始MP3、解碼WAV、原始metadata/reference、裁切標註分存，各有SHA256；不從ccmixter另抓不同錄音。

| 來源 | 示範MP3 SHA256 | 44100Hz mono s16 WAV SHA256 |
| --- | --- | --- |
| puppet_master | 11dd64ec121abd5394c1557bada72f340f65f727bead15c8a023f1ff1e3ed313 | 677e0f681e5b581835500ff2e08cfd2aff905f920eec2bdd337ac5e99c965910 |
| electra_glider | eaaf7b2aa87928160cfbfe40b8f428e257ebcba348c50695e13aa89570b2cd20 | bcd81ae9eceeec3bf61124020a71b0e705bebea5b085ae1a9b317b516006635b |

7項adapter測試通過，涵蓋完整擴展label／相同時間域裁切／未知meter及offset、gap、overlap、無效label、license、非有限數值拒絕。全曲使用smoke tier作診斷，不改30–60秒quality_gate限制。譜保持unmetered／bpm0／空拍號與beat，不由標註重拍補拍速。原版library、7個implementation、ffmpeg、兩metadata與實際音訊／標註hash前後一致；凍結plan SHA256 `635e9a9be4a987e8500546b6ac8acad1c5082223c91d509ed9f7a018b2105e10`。

只取metadata/reference/downbeats，不讀systems成績作比較或真值。音訊與標註限CC BY-NC4.0本機非商業研究，保留原作者及Junyan Jiang標註者署名；沒有公開音訊、上傳、訓練、分離、新模型或產品資料庫寫入。兩首是jazz／bossa，不代表華語流行或任選歌曲表現。

完整可重評產物位於 `output/evaluation/mirex-mixed-reference-2026-11-06/run/{puppet_master,electra_glider}/`，以既有 `diagnose_chord_errors(SongScore.model_validate_json(score), QualityAnnotation.model_validate_json(annotation))` 可零音訊推論重評；manifest記錄下載與實際時間域。

## 下一步的證據界線

資料新增了長時間、多樂器混音上的明確錯根音／過切分證據，沒有直接證明一個共同修正可行。暫不重開A16分離、bass／HMM調參或模型搜尋；也不把品質差異當聲樂有無的分類器。

若要繼續重複段落一致性方向，新完整錄音讓獨立聲學對齊成為可測條件：先以相同錄音的聲學特徵建立重複關係，再用現有人工標註核是否同和聲、是否會把錯根音傳播。禁止用預測和弦找重複再以一致度當準確率；在固定匹配規則、負控制及停止條件前，不做投票修正或升預設。顧問已獨立重算兩份完整diagnostic逐項一致，7測試及metadata逐row裁切／來源／實作hash核符（`output/evaluation/mirex-mixed-reference-2026-11-06/consultant-review.json`）；接受基準交付，沒有新的人耳驗收。
