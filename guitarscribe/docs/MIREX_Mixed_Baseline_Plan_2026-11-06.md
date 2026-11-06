# A17：完整多樂器混音的固定原版基準計畫

日期：2026-11-06。僅可行性與方案；先完成 A16 結果及提交，再執行本段。這是補足評估材料，不是 A16 補考、候選或模型搜尋。

## 來源與用途

顧問已保存 [MIREX2026官方示範](https://futuremirex.com/demos/audio-chord-estimation-2026/) 的 discovery 證據於 `output/evaluation/mirex-mixed-reference-2026-11-06/discovery/`。取目前 index 全部兩首完整錄音，不按辨識結果挑選：

| ID／作者 | 來源／範圍 | 原始metadata SHA256 |
| --- | --- | --- |
| puppet_master／Stefan Kartenberg feat. ScOmBer & Scomberella | [You were a puppet master](https://ccmixter.org/files/JeffSpeed68/71274)，女聲acoustic jazz全編制，約253.315秒 | a62e4b038904b6450fd6c10ef30aca9c140f30debf000b7bd66215167b2658c5 |
| electra_glider／Martijn de Boer (NiGiD) | [Electra Glider](https://ccmixter.org/files/NiGiD/71255)，bossa/jazz器樂，約357秒 | 51695f1499c998122c672d0a1a1bbdd40c0aa9c063e7057d42d4a065da00fe14 |

音訊與 Junyan Jiang 的人工和弦／重拍標註列為 CC BY-NC4.0；保留作者、來源、標註者及授權連結，只作本機非商業研究，不包入網站、範例或repo音訊，不訓練。不把兩首視為華語流行或任選歌曲的代表；不讀官方systems成績或將系統輸出當真值。

唯讀可行性已確認：兩份各91／39段，16／11種獨特label；現有 `diagnostic_label`、完整音集合語義及歷史mir_eval投影均解析成功，無需擴大labelparser。標註連續無gap，audio_offset皆0。原始JSON保留，但adapter只取metadata/reference/downbeats，不取systems欄位。

## 凍結方法

1. 下載這兩個示範原始MP3至隔離目錄，最多兩個音訊請求；記錄URL、bytes、SHA256與HTTP結果。不得改用另一錄音、搜尋模型或補分離stem。metadata先驗hash符合才處理。
2. 使用既有ffmpeg轉44100Hz單聲道s16 WAV，記錄ffmpeg hash、命令、原始與解碼後sample rate／frames／實際音長及hash。不做音量調整、時間平移或輸出依賴的裁切。兩首共同規則：評分域 `[0,min(實際解碼音長,最後參考end))`。puppet標註尾253.33秒略超metadata約15ms，依實際音長共同裁切，不shift。原始標註與裁切後標註分存，報告被排除秒數。
3. 原版Chordino固定既有library SHA256 `fb7d75cf816d3eab3d97da8e6df51f5642b008a49ff4ec6bc2695c42dfded998`，原defaults，每首一次。保存所有Vamp原始label／時間戳及現行audio-intersection解碼，不平滑、不量化、不刪短和弦、不修人工標註。
4. `QualityAnnotation` 使用現有smoke tier承載全曲診斷，不將30–60秒quality_gate規則改掉。明列人工外部reference的出處；未知拍號用空字串，僅保存原downbeats，不補beat/BPM。`SongScore` 使用unmetered、bpm0、空拍號／beat，無產品／DB寫入。
5. 沿A09同一評分器，保留root／majmin及各自scored/unscored覆蓋、完整label錯誤秒數、錯根音／品質／bass／漏多和弦、轉換邊界250ms一對一matching與interior overlay。逐首完整報告，不以平均遮蔽失敗，不按結果選段；核秒數守恆、未知label與時間越界。沒有拍點推論，不報節拍準確率。

## 成本、停止與交付

45分鐘總上限（下載、adapter、驗證及兩次原版推論），2CPU、循序、零付費／上傳／產品修改。網路取得或音訊解碼失敗、來源hash變動、原始label不支援、參考有重疊／無有效域即停，留下具體缺口；不隱性改來源或放寬解析。實際下載前不假稱已有音訊hash；推論前再凍結audio／annotation／runner／library manifest。

這輪完成條件是兩首全曲可重評的原版錯誤基準及明確限制，不預設某個分數就代表產品通過。若錯誤有共同且可反駁的新機制，再另提一次受控修正；不把低分直接當換模型或分離補考的授權。A16確認組01／02仍只在A16原九份通過時才啟用。

預計只需小型adapter與既有Chordino worker，無新增模型／套件；目前未下載音訊或執行這兩首辨識。來源授權與offset仍以已保存的一手證據和實際解碼結果為準。
