# A18：作者低音聲部能否提供可用的獨立反證

日期：2026-11-06。顧問已審查通過以下修訂，凍結runner/hash後執行；本段只驗證產品機制的必要條件，不重排和弦、不跑分離或Chordino，也不將bass強迫當root。

假說：原預測和弦完全不含一個穩定、可信的低音音級時，該訊號可能區分「上方和弦音被誤作root」與正確和弦。A17 Electra的Amaj7→C#min是具體可推翻案例，但採全曲共同規則，不挑選該片段。人工reference只用於評估，不能作產品觸發條件。

## 來源及對齊先決條件

作者 [Electra Glider](https://ccmixter.org/files/NiGiD/71255) 頁及公開links_dl API明列CC BY-NC4.0與兩包檔案，顧問已保存於A17 discovery的 `electra-author.html`／`electra-author-downloads.json`。保留Martijn de Boer (NiGiD)署名、來源與授權，只作本機非商業研究。

只下載以下兩包（總57,760,575 bytes），依API byte長度與base32 SHA1核符，再額外記SHA256。使用固定安全目標檔，僅讀取指定member，不extractall；清單的leading slash不當作實際解壓路徑。

- `https://ccmixter.org/content/NiGiD/NiGiD_-_Electra_Glider_2.zip`，29,921,846 bytes，API SHA1 `YX45TVW23KWQXYOXZG7JFTEAYQXN4TEE`；只取Fretless Bass.flac。
- `https://ccmixter.org/content/NiGiD/NiGiD_-_Electra_Glider.zip`，27,838,729 bytes，API SHA1 `DIZIDTFS4T4S5G7NJOSYT5IQDKLKU67W`；只取Piano.flac。

A17示範MP3 base32 SHA1 `YNWV3EE7FXF2Y72EIOOJY5UAIHQZNJCH`，與作者API原MP3的 `O3EJCXLS5LQ5ELM2EQT4PB4W4TPB5L2G` 不同；不能用檔名宣稱同版，可能重新編碼但尚未證明。

先把原示範混音及兩個FLAC以同一既有ffmpeg轉4000Hz mono FLOAT作時間診斷，原檔保留。每軌須覆蓋共同357秒，與混音音長差不超過0.1秒。全曲、前／中／後等長三段分別作帶通後互相關（bass35–180Hz、piano200–1800Hz；4階Butterworth SOS零相位），固定只搜尋±2秒。每段估計lag絕對值須≤25ms；整曲正規化相關bass≥0.5、piano≥0.25，每個三分段bass≥0.3、piano≥0.15。不得因結果改band／門檻、移動stem或標註。任一未達即停止，報同版／對齊未證實，不花音高估計成本。來源API的共同upload_id＋實長＋四段零lag證據通過後才稱同錄音可對齊，仍不是完美重建證明。

## 固定估音與訊號

只對作者真bass用既有librosa pYIN（DSP音高估計，不下載模型），sr4000、frame_length1024、hop400（100ms）、center=True、fmin=C1 32.7031956626Hz、fmax=C4 261.625565301Hz；n_thresholds100、beta(2,18)、boltzmann2、resolution0.1、max_transition_rate35.92、switch_prob0.01、no_trough_prob0.01、fill_na NaN。不手工修pitch／octave，不從參考調range。原始f0／voiced_flag／voiced_prob全部保留；prob是估計器數值，不是校準準確率。

每個frame須自身及前後各1frame（共3點、中心跨度0.2秒，三個100ms cell共覆蓋0.3秒）皆voiced、voiced_prob≥0.9，四捨五入MIDI的pitch class相同，每點離最近半音≤35cents；中心frame RMS≥全曲最大frame RMS的1%（−40dB振幅）。不補邊緣frame，不以其他訊號替補NaN。通過才是「穩定可用bass」，其餘保留為未知；pitch class對octave不敏感，但仍不據此宣稱f0為真值。取樣cell為中心±50ms，共同域裁切後按與原diagnostic區間的實際重疊秒數加權，不重對齊。

observable flag僅為「穩定bass的pitch class不在原estimate完整和弦音集合」，包含slash bass語義、保留擴展與省略。reference僅評估flag：有效TP需同時原wrong_root且reference包含該bass；其他已知reference的flag均計FP，包括合法非和弦bass、正確root但不同品質及reference N。明列reference不含bass秒數／未知／無穩定pitch，不挑選或刪掉這些區間。

## 必須同時滿足的產品機制門檻

- 全曲已知reference chord時間的穩定bass涵蓋≥30%；原root正確及錯誤兩類各自涵蓋≥20%，避免只在好辨識片段通過。
- flag有效TP precision≥80%；對所有已知root錯誤秒數的TP recall≥20%，且TP≥10秒（未估出pitch仍留在recall分母）。
- 在原root正確秒數的誤觸flag≤5%，未估pitch仍留在該分母；reference不含bass的flag計入總FP，不當漏標排除。
- 授權／同版對齊／來源與程式hash先決條件全部成立。對齊不過列為同錄音對齊未證實、實驗無法判定；coverage不足列為此估音規則證據不足。只有coverage充分而訊號門檻未過才否決此固定訊號；皆不改pYIN、窗口、門檻或挑曲重試。

本段成功僅表示有值得恢復的訊號，不是產品改善。成功後才准提A16九份既有分離bass的可恢復性（含六份單吉他誤觸控制）及最多一個固定和弦候選，另行凍結品質門檻；不在Electra選段重排補考。未達標保留完整證據並區分不可判定／訊號否決，停止此固定試驗，不以更多分類或新模型代替改善。

總上限1小時、2CPU、循序；兩個作者ZIP、兩個FLAC抽取、三個4000Hz時間診斷轉檔、至多一次全曲pYIN。零新分離／Chordino／模型下載／付費／上傳／產品修改。凍結manifest在下載前記URL/API大小SHA1、原混音與原score/reference hash、對齊與音高參數、runner及依賴hash；實際ZIP／FLAC hash於音高運算前增列。

## 取得層修訂（音訊／音高結果之前）

原計畫第一次urllib預設header GET收到HTTP403（1.04秒），沒有取得音訊；原 `run/` 與 [原計畫](evaluation/independent-bass-plan-2026-11-06.json) 保留。以標準瀏覽器User-Agent與作者頁Referer對同一公開URL作HEAD，回200且Content-Length29,921,846符合API；不涉及登入或驗證繞行。顧問允許一次客戶端相容性修訂。

[修訂計畫v2](evaluation/independent-bass-plan-v2-2026-11-06.json) 只固定 `User-Agent: Mozilla/5.0` 與 `Referer: https://ccmixter.org/files/NiGiD/71255`，同URL／SHA1、全部音樂／對齊門檻及原絕對截止2026-11-06T10:02:24.156179+00:00保持；額外1個403 GET、1個metadata HEAD及最多2個payload GET皆列明。GNU timeout按原截止剩餘秒數執行，啟動前四個thread環境值皆2，manifest保留實際parent launcher與argv。新輸出僅寫 `run-v2/`，再次HTTP失敗即停，不替換來源。

## pYIN參數域相容修訂（未產出真實f0之前）

v2成功下載並核符兩ZIP大小／SHA1及抽取FLAC；八個對齊檢查皆0lag，bass／piano全曲相關0.6701／0.6770。但pYIN原實作在回傳f0前，因既定35.92、100ms hop產生431點三角transition prior，而音高範圍只有361 states，`pad_center`拒絕較大的窗。v2 failure與runner快照保留，不把工程錯誤當音樂判決。

顧問通過 [v3相容修訂](evaluation/independent-bass-plan-v3-2026-11-06.json)：保持原431點三角窗及rate35.92，列i／欄j權重取 `window[215+j-i]`，越窗索引為0，限制於合法目的state後逐row正規化。只在此離線程序對361／431／triangle／nonwrap呼叫特例處理，`finally`還原函式，不修改site-packages。合法窄窗與原API逐項相等、超寬窗rowmass／邊界及55Hz同規格合成pYIN已驗證；共7測試過。這是明示工程擴展，不宣稱原函式本來可執行，也不改用rate30或依歌曲結果調先驗。

v3按hash重用v2兩ZIP、兩FLAC、三WAV及對齊manifest，零新下載／轉檔／對齊重跑；原絕對截止保持。真實pYIN兩次attempt（一次無法解碼，至多一次成功f0），另列一次合成可行性，不將失敗attempt隱去。原有音高範圍、hop、信心、穩定及產品機制門檻完全不變。
