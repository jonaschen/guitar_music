# 第三來源：固定旋律方法唯讀審計

日期：2026-10-25。僅讀完成 job/API、既有 artifacts 與程式，執行固定 `decode_bounded` 統計；沒有下載、重新分離、重跑 pYIN、調參、寫入 job/revision 或變更產品。

## 來源與實際處理時間

第三來源 job：`f303ec8a86834633b060920fa85430af`，請求網址 `https://www.youtube.com/watch?v=0rpbhqZI0hc`。

- 建立：`2026-10-25T08:10:06.243936+00:00`（臺北16:10:06）。
- completed 更新：`2026-10-25T08:14:02.101569+00:00`（臺北16:14:02）。
- 兩個 job timestamp 相減：**235.857633秒**；包含排隊與處理，不是純模型運算時間。輪詢曾看到 beat_analysis 35%及 vocal_separation 66%，未另觸發分析。
- 原 input：48kHz／雙聲道，273.1015秒；實際 analysis-source：48kHz／雙聲道，**60.000秒**；完成 vocal-stem：44.1kHz／雙聲道，**60.000秒**。
- skip=0，score 的 source_start_seconds=0；contour 來源區間0–60秒。因此分析秒數等於這次輸入原檔秒數；未額外加 skip。

曲名／影片標題不作為錄音條件證據，未確認 studio/live 類型。score.song.title 為 `analysis-source`、source_type 為 local；它描述本地分析中介檔，不能取代 job 的 YouTube URL 與來源 hash。

## 與前案的設定比較

前案：`db79e1145ea046088b8aa5ef421d0e3f`，請求網址 `https://www.youtube.com/watch?v=Q-B-fw-bO7M&list=RDQ-B-fw-bO7M&start_radio=1`。

| 項目 | 第三來源 | 前案 |
|---|---|---|
| status | completed | completed |
| melody_mode | vocal | vocal |
| separate_vocals requested | true | true |
| vocal_source_separated | true | true |
| skip_seconds | 0 | 0 |
| analysis_seconds | 60 | 45 |
| chord_complexity | **standard** | **full** |
| melody engine/version | pyin_vocal / 0.11.0 | pyin_vocal / 0.11.0 |
| 原分析 processing | source-timed-semitone-v2 | source-timed-semitone-v2 |
| 原分析音符數（非G） | 106 | 76 |
| beat engine/version | beat-this / 1.1.0 | beat-this / 1.1.0 |
| chord engine/version | chordino / 1.1-provenance | chordino / 1.1-provenance |

前案建立 `2026-10-24T23:54:29.563091+00:00`，completed 更新 `2026-10-24T23:57:12.713225+00:00`，相減 **163.150134秒**。長度與處理負載不同，不拿兩個總時間作等條件效能比較。

兩案均記錄 small0／CPU／dbn=false，權重SHA `6074be2c4d490c5f6101fcc374a1ec72ae93456e23bb6019783b849f5dc7d47b`；Chordino library SHA `fb7d75cf816d3eab3d97da8e6df51f5642b008a49ff4ec6bc2695c42dfded998`。

**可稱固定旋律方法，不能稱整個 job 設定完全相同。** pYIN `_analyze` 使用 vocal profile，沒有讀 beats 或 chord_complexity；G直接讀 contour，沒有和弦輸入。本輪不試聽和弦，也未為消除 standard/full 差異重跑分析。

## 旋律實作與 profile

目前檔案與已版本化 `docs/diagnostics/2026-10-25/synthetic-results.json` 中的 implementation SHA逐項相等：

- `app/analyzers/melody/pyin_adapter.py`：`a44d7c1564b0888726a269319023f96eb1f494696e9db51cfd951b0c83295e8c`。
- `app/evaluation/conservative_notes.py`：`cbfc58b99ee1d00e599cb9a4204a2fdac9f3c34b7d05c6cd66c051c01d508c4f`。

pYIN固定參數為sr=22050、hop=512（23.2199546485ms）、frame_length=2048、resolution=0.5、n_thresholds=32；vocal頻率範圍98–1047Hz。MODE_PROFILES另有 onset_threshold=.35、frame_threshold=.20、minimum_note_length=100，但pYIN頻率追蹤只使用其中頻率範圍；不能誤稱這些Basic Pitch門檻都作用在G。

G的switch cost=.35、最大逐框來源誤差=.6半音，沒有最小音長或confidence刪音。本輪只呼叫此固定解碼器，沒有使用已拒絕的 onset-aware 候選。

界線：job未逐項保存上述全部pYIN參數與程式hash；這裡是目前固定程式、相同provenance版本及contour hop的查核，不冒稱每個歷史job都有完整執行環境快照。

## Artifact身分

第三來源SHA256：

| 檔案 | SHA256 |
|---|---|
| input.wav | `5371ca52ee79766dfcd63a51f8b34b4b2ee1adcfbdc6d9ab113939d4e57c092e` |
| analysis-source.wav | `892470bbc60e5401bd3c632aa169f2e7c948fc553a04996325ff28e1ffb9111d` |
| vocal-stem.wav | `b7fd25590abc742bbf93eadd9e38a6262c7b0ee635fddba780c099d3ee47994f` |
| melody-contour.json | `8a65c277a9a93db60dff808cf27e52f67cdebe3d0ec664504cdacbb87e37d2ba` |

contour.source_artifact_sha256 **精確等於完成 vocal-stem.wav SHA**。contour有2584 frames，其中1930有聲，hop與前案完全相同；source_start=0、source_end=60。

前案SHA256：

| 檔案 | SHA256 |
|---|---|
| input.wav | `f2c4b421bb7e994eea74a5a316f02c2dd346d09a049db03c162110ad0af0fe9e` |
| analysis-source.wav | `09ab077783f23ddcb226e13ad6c14bb41bf0b89f865d7a729d890ee3c2f2402d` |
| vocal-stem.wav | `1d57f3aefe1a2dc202f75f05990487609ca58fc32563d6f10ca67c6dbfb5d7f5` |
| melody-contour.json | `b5e102b960403d6a57d1d6ecde07eca2bd1381873c8bd9f4ad7e69f06dda4305` |

前案contour也精確對應其vocal stem（0–45秒、1938 frames、1647有聲）。兩案各自對應，沒有混用音檔。

## 固定G統計（非音樂準確率）

20–40、40–60秒由主線在完成contour前固定，沒有依結果挑窗。範圍採半開區間；音符只要與範圍相交就計數，voiced_seconds與片段音長統計在窗口截齊。本次短音數用原完整音長或窗口截齊音長計算恰好相同，不代表一般情況一定相同。

| 範圍 | G音符 | <100ms | <10ms | 有聲秒數 | 原音長中位數 | MIDI範圍 |
|---|---:|---:|---:|---:|---:|---|
| 第三來源0–60s | 260 | 134 | 0 | 44.814150 | 92.879819ms | 47–74 |
| 第三來源20–40s | 112 | 59 | 0 | 15.271111 | 92.879819ms | 47–60 |
| 第三來源40–60s | 109 | 57 | 0 | 16.416145 | 92.879819ms | 53–74 |
| 前案0–45s，僅背景對照 | 159 | 72 | 0 | 38.242993 | 116.099773ms | 47–71 |

第三來源第一音在2.809614512s，最後音尾60.000s；這只是來源contour覆蓋，不保證真實演唱從該時刻開始／結束。20秒窗口有一音從19.922721088s延入；40–60秒第一音在41.006439909s。兩案G均有序、無音符重疊，正音長且在各自來源範圍內。

短音比例較高不等於錯音較多，有聲覆蓋不等於正確休止。前案45秒與第三來源60秒的原始計數不作直接品質排名；沒有人工真值、不報音高／節奏準確率，也不因本次完成就宣稱跨曲泛化通過。實際compiler parity及播放片段由主線另行核對，本文件不替代該結果。
