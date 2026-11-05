# 工具選擇與證據判讀

這些是底層工具的原始來源，不是可直接安裝的官方 Codex skills。新增依賴、權重或採用新 API 前查閱原始專案的當前文件、版本相容性、資源需求與授權；不要把本表當作依賴鎖檔。

| 工具及原始來源 | 適合用途 | 判讀限制 |
| --- | --- | --- |
| [Spotify Basic Pitch](https://github.com/spotify/basic-pitch) | 音訊到多音音符／MIDI | 官方建議一次處理單一樂器；完整混音的多音輸出不等於主要旋律 |
| [librosa pYIN](https://librosa.org/doc/0.11.0/generated/librosa.pyin.html) | 單旋律 F0、voicing 與其機率 | fmin/fmax、frame/hop、centering 會影響結果；乾淨的人聲也仍需音符分段 |
| [Demucs 原始研究專案](https://github.com/facebookresearch/demucs) | 將混音分為聲部，供後續分析 | 分離輸出會有滲漏與失真，other 也可能含多樂器；使用前核對目前維護狀態與實際來源 |
| [Essentia PredominantPitchMelodia](https://essentia.upf.edu/reference/std_PredominantPitchMelodia.html) | 有顯著旋律聲部的複音錄音，輸出主要 F0 軌跡 | 是可比較的候選工具，不保證每段旋律歸屬，也不直接完成節奏記譜 |
| [music21](https://music21.org/music21docs/about/what.html) | 符號音樂、樂理及記譜處理 | 適合已取得音符後的處理；不能單靠轉檔恢復漏掉的音符 |
| [mir_eval melody](https://mir-eval.readthedocs.io/latest/api/melody.html)、[transcription](https://mir-eval.readthedocs.io/latest/api/transcription.html)、[beat](https://mir-eval.readthedocs.io/latest/api/beat.html)、[chord](https://mir-eval.readthedocs.io/latest/api/chord.html) | 估計結果與獨立參考的分層比較 | 評分器不產生真值；記錄版本、容差、時間區段及有效覆蓋 |

## 旋律與音符

分開回答「在哪些時間有主旋律」「音高是否正確」「何時起音與結束」。有參考輪廓可報 raw pitch accuracy、raw chroma accuracy、voicing recall／false alarm、overall accuracy；chroma 忽略八度，因此不能單獨證明音高正確。有可靠音符標註才計算 note precision／recall／F1，區分僅 onset 與含 offset 的結果，明列 pitch/onset/offset 容差。

不要將平滑輪廓、少量音符或高 voiced probability 當成準確率。若參考只包含部分音符，未標註區段不得當作已確認無聲；模型漏掉整個聲部也不得由平均信心掩蓋。

## 節奏與和弦

拍點規律不等於拍速層級正確；分開報 BPM 偏差、beat F1、CML／AML 與 downbeat。AML 容許某些替代拍速層級，半速／倍速仍可能很高。小節相位錯一拍可能不影響 beat F1，必須另看重拍。

和弦比較兼顧時長加權正確率、切換邊界及過度切碎；說明根音、大小三和弦或更細詞彙的評分層級與覆蓋。不能用刪除短和弦、忽略未知區域或擴張容許標籤集合來事後提高分數。

## 可重現記錄

沿用專案 schema；缺少欄位時用獨立分析 manifest 記錄，不為一次分析修改產品資料模型：

- input：來源路徑／SHA256、原始及解碼後 sample rate、channels、duration、片段範圍、局部到來源時間映射。
- run：程式 commit 與是否有未提交變更、實際套件／模型版本或權重 hash、引擎／聲部、參數、seed（適用時）、裝置、耗時、警告及 fallback。
- evidence：原始輪廓、原始音符、後處理 score 與匯出檔位置；有轉調或量化時記錄轉換。
- evaluation：參考來源與 hash、人工審核狀態、標註覆蓋、資料集／訓練重疊、評分版本及容差、逐片段結果。無參考以 unknown 表示，不填入假分數。

模型 metadata 與雜湊不包含帳號憑證、API keys 或完整環境變數。一般本機分析不需外部音訊上傳。
