# GuitarScribe UI 追加規格：升降 Key 與替代和弦按法

> 文件類型：主交接文件的追加規格  
> 文件版本：v1.0  
> 建立日期：2026-09-04  
> 對應主文件：`GuitarScribe_Web_UI_AI_Handoff.md`  
> 閱讀順序：下一個 AI Session 必須先讀主文件，再讀本追加文件。  
> 整合狀態：需求已確認，尚未實作。

---

## 1. 追加需求摘要

GuitarScribe Web UI 新增兩項正式產品需求：

1. **全曲升降 Key／移調工具**；
2. **每個和弦的替代按法，包括不同把位與不同指型**。

這兩項功能不是單純的畫面裝飾。它們會影響：

- 和弦名稱；
- slash chord 的低音；
- 主旋律音名與音高；
- Capo；
- 和弦指型；
- ChordPro、MusicXML、MIDI、PDF 與 JSON 匯出；
- 使用者修改資料與 revision；
- 前後和弦之間的演奏難度。

一句話定義：

> 使用者可以把整首譜升降到適合自己歌唱或演奏的調性，並為每個和弦選擇最適合自己的把位與指型。

---

## 2. 與主文件的關係

本文件追加而不取代主文件中的產品方向、分析管線、法律限制與里程碑。

若本文件與主文件產生衝突，以本文件對以下範圍的描述為準：

- 移調；
- Key UI；
- Capo 與指型調性；
- 和弦圖；
- 替代 voicing；
- 和弦指型選擇；
- 相關資料模型、API、測試及驗收條件。

主文件仍是完整專案交接來源。本文件只負責深化這兩項新增功能。

---

## 3. 名詞與音樂語意

後端、前端及文件必須一致使用以下概念，避免把移調與 Capo 混為一談。

### 3.1 原曲調性 Source Key

音訊分析引擎偵測到的原始歌曲調性。例如：

```text
Source Key = G Major
```

這是分析結果，不應因使用者按下升降 Key 而被覆寫。

### 3.2 編曲目標調性 Target Key

使用者目前希望樂譜呈現及實際演奏發聲的調性。例如：

```text
Source Key = G Major
Target Key = A Major
Transpose = +2 semitones
```

### 3.3 指型調性 Shape Key

吉他手實際閱讀並按下的和弦形狀所屬調性。使用 Capo 時，指型調性與實際發聲調性可能不同。

例如：

```text
Target/Sounding Key = A Major
Capo = 2
Shape Key = G Major
```

### 3.4 實際發聲調性 Sounding Key

樂器最後發出的調性。在沒有音訊變調時，YouTube 播放器仍播放 Source Key；吉他則依 Target Key、Capo 與 Shape Key 的組合決定實際音高。

### 3.5 和弦符號 Chord Symbol

表示和聲語意，例如：

```text
C
Am7
D/F#
Cmaj9
```

### 3.6 和弦指型 Chord Voicing

表示吉他上具體彈哪些音、使用哪些弦與琴格。相同和弦符號可能有很多 voicing。

### 3.7 基本關係

```text
實際發聲和弦 = 指型和弦 + Capo 格數
指型和弦 = 目標發聲和弦 − Capo 格數
```

所有移調運算使用十二平均律的 pitch class；音名顯示則依調性與升降記號偏好決定。

---

## 4. 升降 Key 工具：UI 規格

### 4.1 常駐工具列

結果／編輯頁上方必須提供常駐 Key 工具列：

```text
原曲：G Major    編曲：A Major    [−] [+]    變化：+2    [回到原調]
Capo：2          指型調：G Major             [尋找較簡單按法]
```

桌面版應在不離開譜面的情況下完成所有常見操作。行動版可收合成底部工具列或設定抽屜。

### 4.2 必要操作

- `−`：全曲下降一個半音。
- `+`：全曲上升一個半音。
- 直接選擇十二個目標 Key。
- 顯示相對原曲的半音差，例如 `−3`、`+2`。
- 「回到原調」。
- 選擇 Major／Minor 時，不可只是切換標籤；若功能未實作，UI 不提供模式切換。
- 選擇 `Prefer sharps`、`Prefer flats` 或 `Auto`。
- 設定 Capo 0～使用者允許的最高格數。
- 自動尋找較簡單的 Capo／Shape Key 組合。
- 顯示移調是否仍與目前播放音訊一致。

### 4.3 移調後必須同步更新

- 全部和弦根音；
- slash chord 的 bass note；
- 目前調性名稱；
- 主旋律 MIDI pitch；
- 主旋律音名；
- 五線譜上的 Key signature；
- 可用和弦指型；
- 選用 voicing；
- Capo 建議；
- ChordPro；
- MusicXML；
- MIDI；
- PDF；
- JSON。

不得改變：

- 拍點時間；
- 小節時間；
- 和弦區段開始／結束時間；
- 原始分析 revision；
- Source Key。

### 4.4 移調不是重新分析

升降 Key 應是快速、可逆的純資料轉換，不應重新執行音訊辨識模型。

所有移調一律從原始模型結果或指定的基準 revision 計算，不可在目前畫面結果上重複累加，避免以下問題：

- 連續升降造成音名漂移；
- 人工修改和弦逐步累積誤差；
- 異名同音反覆轉換後拼字不一致。

建議資料欄位：

```text
transpose_semitones = target_pitch_class - source_pitch_class
```

範圍可正規化為 `−11..+11`；UI 常用顯示可限制為 `−6..+6`，但不應限制使用者直接選擇 Key。

### 4.5 升降記號與音名拼寫

`Auto` 模式應依目標調性選擇合理拼法，例如：

- F major 優先使用 `Bb`，而不是 `A#`。
- Eb major 優先使用 `Bb`、`Eb`、`Ab`。
- E major 優先使用 `F#`、`G#`、`C#`、`D#`。
- slash chord 的 bass note 使用相同拼字規則。
- 主旋律音名與和弦拼字保持一致。

MVP 不必完整處理雙升、雙降及高度古典和聲拼寫，但資料模型不可假設所有黑鍵都用 sharp。

### 4.6 YouTube 播放一致性

必須區分：

1. **譜面移調**：改變譜面，不改變原始 YouTube 音訊。
2. **Capo 換指型**：維持發聲調性，改變吉他手看到的和弦形狀。
3. **播放器變調**：實際改變播放音高，屬獨立功能。

如果 Target Key 與 YouTube Source Key 不同，而播放器沒有音高變換能力，UI 必須顯示：

> 目前譜面已移調至 A Major；播放中的原曲仍為 G Major。

不能暗示轉調後的譜仍可直接配合未變調的原曲。

若來源是使用者上傳的合法音訊，未來可透過 Web Audio、Rubber Band 或伺服器端產生變調播放版本。這不是本次追加需求的 MVP 必要條件。

---

## 5. Capo 建議工具

### 5.1 目標

Capo 工具不是單純把數字加在頁面上，而是尋找「維持目標發聲調性、同時讓整首歌比較容易按」的指型組合。

### 5.2 UI

顯示：

- Capo 格數；
- 實際發聲調性；
- 指型調性；
- 預估難度；
- 開放和弦數；
- 大橫按數；
- 與目前設定相比的難度變化。

範例：

```text
方案 A：Capo 0｜A Major 指型｜4 個橫按｜難度 4/5
方案 B：Capo 2｜G Major 指型｜1 個橫按｜難度 2/5（推薦）
方案 C：Capo 5｜E Major 指型｜2 個橫按｜難度 3/5
```

### 5.3 排名因素

Capo 建議至少評估：

- 開放和弦數量；
- 大橫按數量；
- 每個和弦的個別難度；
- 相鄰和弦的手位轉換成本；
- 使用者指定的最高 Capo；
- 使用者偏好的把位；
- 是否需要保留特定低音或 slash chord；
- 節奏以刷奏還是分解為主。

### 5.4 限制

- Capo 可能讓和弦容易，但使主旋律超出舒適把位；若同頁顯示主旋律 Tab，需重新映射。
- 某些 slash chord 使用 Capo 後難以保留指定 bass，必須警告。
- 推薦只是建議，使用者可固定 Capo 或固定 Shape Key。

---

## 6. 替代和弦按法：UI 規格

### 6.1 入口

使用者點擊和弦格、和弦標籤或和弦圖後，開啟「替代按法」抽屜／浮動面板。

### 6.2 面板內容

至少顯示：

- 和弦名稱；
- 構成音；
- 指定 bass；
- 目前指型；
- 其他候選指型；
- 起始琴格；
- 六弦圖；
- mute/open/fret；
- 手指編號；
- 橫按起訖；
- 最低音；
- 實際發聲音；
- 難度 1～5；
- 標籤。

建議標籤：

```text
Open
CAGED-C
CAGED-A
CAGED-G
CAGED-E
CAGED-D
Barre
Compact triad
Low position
High position
Strumming
Arpeggio
Beginner
```

### 6.3 使用者操作

- 點擊候選即可預覽和弦圖。
- 使用合成音短暫試聽 voicing。
- 套用到本次出現。
- 套用到本段所有同名和弦。
- 套用到全曲所有同名和弦。
- 設定為目前歌曲的偏好指型。
- 依難度、把位、是否橫按及用途篩選。
- 設定最高琴格。
- 重新自動最佳化全曲指型。

### 6.4 預設候選排序

1. 容易彈且包含必要和弦音；
2. 與前後和弦手位移動較小；
3. 符合 Capo、調弦與最高琴格設定；
4. 適合目前節奏用途；
5. 符合使用者在本歌曲中的偏好。

### 6.5 套用範圍

資料模型不可只存「C 和弦偏好」，因為同一首歌的不同位置可能需要不同按法。

支援：

```text
occurrence：只套用這一次
section：套用目前段落內同名和弦
song：套用整首歌內同名和弦
```

套用較大範圍前，UI 應顯示會影響的和弦事件數量。

---

## 7. 和弦指型資料與演算法

### 7.1 混合來源策略

- 常用和弦：使用經人工驗證的靜態資料庫。
- 少見和弦：用 fretboard search 動態生成候選。
- 動態候選：通過可演奏性驗證後才顯示。
- 每筆資料記錄來源與版本。

### 7.2 ChordEvent 與 ChordVoicing 分離

`ChordEvent` 表示某段時間的和聲，例如 `Cmaj7/G`。

`ChordVoicing` 表示吉他上實際彈哪些弦、哪些格與哪些音。

同一個 ChordEvent 可有多個候選，但只有一個目前選用的 voicing。

### 7.3 必要音與可省略音

指型搜尋器必須理解：

- 根音；
- 三音；
- 五音；
- 七音；
- 延伸音；
- slash chord 指定最低音；
- 可省略的非關鍵音；
- 不可省略或改變的關鍵音。

不可只比較 pitch-class set，就把音樂功能不同的指型當成完全等價。

### 7.4 可演奏性檢查

候選至少滿足：

- 不超過最高琴格；
- 手位跨度不超過設定上限；
- 使用手指數合理；
- 橫按範圍合理；
- 非橫按情況下，不要求一根手指按不連續琴弦；
- slash chord 的最低發聲音正確；
- 包含和弦必要音；
- mute string 不會切斷無法實現的刷奏路徑；
- 不產生與標示和弦矛盾的額外關鍵音。

### 7.5 Voicing 排名

```text
voicing_cost =
  intrinsic_difficulty
  + barre_penalty
  + fret_span_penalty
  + high_position_penalty
  + muted_inner_string_penalty
  + transition_cost_from_previous
  + transition_cost_to_next
  + style_mismatch_penalty
  - open_string_bonus
  - user_preference_bonus
```

整首歌的最佳按法不應逐個和弦貪婪選擇。應對和弦序列使用動態規劃或最短路徑，將前後手位轉換成本納入。

---

## 8. 資料模型追加

主文件的 canonical `SongScore` 增加以下欄位。

### 8.1 Arrangement

```json
{
  "arrangement": {
    "source_key": "G",
    "target_key": "A",
    "transpose_semitones": 2,
    "prefer_accidentals": "sharp",
    "playback_pitch_shift": false
  }
}
```

### 8.2 GuitarSettings

```json
{
  "guitar": {
    "tuning": [40, 45, 50, 55, 59, 64],
    "tuning_name": "EADGBE",
    "capo": 2,
    "max_capo": 7,
    "max_fret": 15,
    "handedness": "right",
    "difficulty": "beginner"
  }
}
```

調弦陣列依低音 E 弦到高音 E 弦排列。

### 8.3 ChordEvent 追加欄位

```json
{
  "id": "chord-event-1",
  "start": 0.52,
  "end": 4.68,
  "source_symbol": "G",
  "target_symbol": "A",
  "shape_symbol": "G",
  "confidence": 0.84,
  "selected_voicing_id": "voicing-g-open",
  "voicing_scope": "occurrence",
  "origin": "model",
  "edited": false
}
```

### 8.4 ChordVoicing

```json
{
  "id": "voicing-g-open",
  "chord": "G",
  "base_fret": 1,
  "frets": [3, 2, 0, 0, 0, 3],
  "fingers": [2, 1, 0, 0, 0, 3],
  "barres": [],
  "bass_note": "G2",
  "notes": ["G2", "B2", "D3", "G3", "B3", "G4"],
  "difficulty": 1,
  "tags": ["open", "beginner", "strumming"],
  "source": "verified-dictionary",
  "source_version": "1.0"
}
```

欄位規則：

- `frets`：低音 E 到高音 E；`-1` 為 mute、`0` 為 open、正整數為琴格。
- `fingers`：相同弦順序；`0` 為不按，`1`～`4` 為手指。
- `barres`：記錄琴格、起始弦、終止弦與手指。
- `base_fret`：和弦圖的起始顯示琴格，不等於 Capo。
- `notes`：必須由 tuning、capo 與 frets 實際計算並驗證。
- ChordEvent 只引用 voicing ID，不重複嵌入整份指型。

### 8.5 Revision 原則

- Source Key 屬於模型分析 revision。
- Target Key、Capo、accidental preference 屬於 arrangement revision。
- 人工指定 voicing 屬於 user-edit revision。
- 重新執行模型不可覆蓋 arrangement 與 user-edit revision。
- 重新轉調時應保存可逆的基準，不在已轉調資料上反覆累加。

---

## 9. 服務界面追加

```python
class TranspositionService(Protocol):
    def transpose(
        self,
        score: SongScore,
        target_key: Key,
        accidental_preference: AccidentalPreference,
    ) -> TransposedArrangement:
        ...

class CapoAdvisor(Protocol):
    def recommend(
        self,
        score: SongScore,
        guitar: GuitarSettings,
    ) -> list[CapoRecommendation]:
        ...

class ChordVoicingProvider(Protocol):
    def find_voicings(
        self,
        chord: ChordSymbol,
        guitar: GuitarSettings,
        context: VoicingContext,
    ) -> list[ChordVoicing]:
        ...

class SongVoicingOptimizer(Protocol):
    def optimize(
        self,
        chord_events: list[ChordEvent],
        candidates: dict[str, list[ChordVoicing]],
        guitar: GuitarSettings,
    ) -> VoicingPlan:
        ...
```

這些服務不得依賴 React、FastAPI request 或特定資料庫 ORM object。

---

## 10. API 追加

```text
POST   /api/v1/scores/{score_id}/transpose
POST   /api/v1/scores/{score_id}/capo
GET    /api/v1/scores/{score_id}/capo-recommendations

GET    /api/v1/chord-voicings
PUT    /api/v1/scores/{score_id}/chords/{chord_id}/voicing
POST   /api/v1/scores/{score_id}/optimize-voicings
```

### 10.1 Transpose Request

```json
{
  "target_key": "A",
  "prefer_accidentals": "auto"
}
```

### 10.2 Capo Request

```json
{
  "capo": 2,
  "keep_sounding_key": true,
  "recalculate_voicings": true
}
```

### 10.3 查詢替代按法

```text
GET /api/v1/chord-voicings?symbol=G&shape_key=G&tuning=EADGBE&capo=2&max_fret=15&difficulty=beginner
```

### 10.4 選擇按法

```json
{
  "voicing_id": "voicing-g-open",
  "scope": "section"
}
```

### 10.5 最佳化全曲

```json
{
  "difficulty": "beginner",
  "prefer_open": true,
  "avoid_barre": true,
  "max_fret": 12,
  "scope": "song"
}
```

所有 mutation API 必須回傳新的 arrangement／edit revision，並允許 optimistic concurrency control。

---

## 11. 前端狀態管理

至少區分：

```text
analysisState     原始模型結果
arrangementState  Target Key、Capo、音名偏好
editState         使用者修改的和弦、節拍、voicing
playerState       播放位置、播放速度、原曲音高狀態
exportState       匯出格式與產生進度
```

重要規則：

- 升降 Key 不直接改寫 analysisState。
- 切換 Capo 不改變 Target/Sounding Key，除非使用者明確選擇。
- 使用者選 voicing 後，要標示尚未儲存或已儲存。
- 後端更新失敗時，不可讓 UI 看起來已永久保存。
- Undo/Redo 至少涵蓋 Key、Capo 與 voicing 變更。

---

## 12. 邊界案例

必須測試：

- C 上升一個半音時，在不同偏好下顯示 C# 或 Db。
- slash chord `D/F#` 的 root 與 bass 同時移調。
- minor、dominant 7、major 7、sus、dim、aug、add、extension。
- `N`／No Chord 不移調。
- Capo 造成 Shape Key 跨越 B/C 或 E/F。
- 轉調後原本人工選擇的開放和弦不再成立。
- 高把位 voicing 移調後超過 max fret。
- slash chord 找不到符合 bass 的可演奏指型。
- 同名和弦在不同段落選擇不同 voicing。
- 只套用單次與套用全曲的差異。
- 重新分析後保留 Target Key、Capo 與人工 voicing。
- 匯出後的 Key、和弦、旋律與和弦圖保持一致。
- YouTube 原曲未變調時顯示不一致警告。

---

## 13. 自動測試要求

### 13.1 Transposition 單元測試

- 十二個 pitch class 的正向與反向移調。
- Major/minor key spelling。
- slash chord。
- extension 保留。
- N chord。
- 移調往返應回到相同 canonical chord。
- 所有時間戳保持不變。
- 不修改 source analysis object。

### 13.2 Voicing 單元測試

- 實際發聲音與 frets 一致。
- 必要和弦音存在。
- slash bass 正確。
- 手指與橫按資料可實現。
- max fret、max span 與 difficulty filter 生效。
- 靜態資料庫不存在時可使用動態候選。
- 無可用候選時回傳可理解的 warning，而不是偽造指型。

### 13.3 整合測試

測試流程：

1. 載入固定 SongScore fixture。
2. 從 G major 移調到 A major。
3. 設定 Capo 2。
4. 確認 Shape Key 回到 G major。
5. 取得每個和弦候選。
6. 選擇並套用 voicing。
7. 匯出 JSON 與 ChordPro。
8. 驗證所有格式一致。

### 13.4 UI E2E

- `+`／`−` 每次只改一個半音。
- 「回到原調」恢復正確。
- 切換 flats/sharps 即時更新。
- Capo 推薦可套用。
- 和弦抽屜可開啟、預覽、篩選與套用。
- 套用範圍確認文字正確。
- 移調後播放器警告出現。
- 重新整理頁面後設定仍存在。
- Undo/Redo 正常。

---

## 14. 里程碑調整

### 對主文件 Milestone 0 的影響

Milestone 0 不需建立 UI，但 `SongScore` schema 現在必須預留：

- arrangement；
- guitar settings；
- selected voicing ID；
- voicing catalog；
- schema version migration。

### 對主文件 Milestone 2 的影響

Web UI MVP 加入基本 Key 工具：

- 顯示 Source Key；
- `−`／`+`；
- 回到原調；
- Target Key；
- 原曲音高不一致警告。

### 對主文件 Milestone 3 的影響

可編輯樂譜階段加入完整功能：

- 直接選 Key；
- accidental preference；
- Capo advisor；
- Shape Key；
- 和弦按法抽屜；
- 套用範圍；
- 全曲 voicing optimizer；
- Undo/Redo；
- revision persistence。

### 對主文件 Milestone 4 的影響

主旋律／Tab 在 Key 或 Capo 改變後必須重新映射，但不需重新執行音訊辨識。

---

## 15. 追加 Definition of Done

此追加功能完成必須符合：

- 使用者能以半音升降整首譜。
- 使用者能直接選擇 Target Key。
- Source Key 永遠可見且不被覆寫。
- 全部和弦與 slash bass 正確移調。
- 主旋律與所有匯出格式同步移調。
- flats/sharps 顯示符合目標調性或使用者偏好。
- YouTube 原曲未變調時有明確警告。
- 使用者可取得至少數個常用和弦的替代把位。
- 每個候選顯示正確六弦圖、琴格、手指與難度。
- 可選擇本次／段落／全曲套用範圍。
- 可依最高琴格及是否橫按篩選。
- Capo 建議能同時顯示 Sounding Key 與 Shape Key。
- 重新分析不覆蓋使用者選擇的 Target Key、Capo 或 voicing。
- JSON／ChordPro／MusicXML／PDF 不出現互相矛盾的調性或和弦。
- 核心移調與 voicing 驗證具有自動測試。

---

## 16. 給下一個 Coding Agent 的追加提示詞

```text
請先完整閱讀：
1. GuitarScribe_Web_UI_AI_Handoff.md
2. GuitarScribe_UI_Key_and_Chord_Voicings_Addendum.md

第二份文件是第一份的追加規格。若兩者在移調、Capo 或和弦指型上衝突，以追加文件為準。

請將以下能力納入架構與資料契約：
- Source Key 與 Target Key 分離；
- 全曲半音移調；
- flats/sharps 自動拼寫及使用者偏好；
- Capo、Sounding Key 與 Shape Key 分離；
- ChordEvent 與 ChordVoicing 分離；
- 一個和弦可有多個替代把位；
- 使用者可對單次、段落或整首歌套用指型；
- 重新分析不得覆蓋 arrangement 與 user-edit revision。

如果目前仍在 Milestone 0：
1. 先更新 SongScore JSON Schema。
2. 為 TranspositionService 建立純函式實作與測試。
3. 為 ChordVoicing 定義 schema、驗證器及少量合法 fixture。
4. 暫時不製作完整和弦圖 UI，但不可建立會阻礙後續功能的資料結構。

如果已進入 Web UI Milestone：
1. 實作常駐 Key 工具列。
2. 實作 Source/Target/Shape Key 顯示。
3. 實作原曲音高不一致警告。
4. 實作替代和弦按法抽屜。
5. 實作套用範圍與 revision 保存。
6. 加入相應 Vitest、pytest 與 Playwright 測試。

完成後請回報：
- 修改的 schema 與 migration；
- 音樂語意上的設計決策；
- 新增的 API；
- 自動測試結果；
- 尚不支援的和弦類型；
- YouTube 播放與譜面移調不一致時的 UI 行為。
```

---

## 17. 整合檢查表

下一個 AI Session 在宣告追加需求已整合前，逐項確認：

- [ ] 主文件與追加文件都已閱讀。
- [ ] Source Key 不會被 UI 移調覆蓋。
- [ ] Target Key 是 arrangement 狀態。
- [ ] Capo 與 base fret 沒有混用。
- [ ] Shape Key 與 Sounding Key 有獨立欄位或可明確推導。
- [ ] slash chord bass 會一起移調。
- [ ] melody notes 會一起移調。
- [ ] ChordEvent 與 ChordVoicing 已分離。
- [ ] 和弦事件引用 voicing ID。
- [ ] 常用指型資料經過驗證。
- [ ] 動態候選經過可演奏性檢查。
- [ ] 可選擇套用範圍。
- [ ] 全曲最佳化考慮前後手位。
- [ ] 轉調後會重新計算 voicing。
- [ ] YouTube 原曲未變調時有警告。
- [ ] JSON Schema 與 API 已有版本。
- [ ] 自動測試涵蓋十二個 pitch class。
- [ ] 匯出格式保持一致。

---

## 18. 本追加規格的產品原則

1. **Key 工具改的是編曲，不可竄改原始分析。**
2. **Capo 改變指型，但不必改變實際發聲調性。**
3. **和弦名稱與和弦按法是不同資料。**
4. **替代指型必須可演奏且音樂語意正確。**
5. **指型推薦要考慮整段轉換，不只考慮單一和弦。**
6. **YouTube 原曲未變調時，必須明示譜面與音訊的差異。**
7. **所有變更都應可逆、可儲存、可匯出、可測試。**

