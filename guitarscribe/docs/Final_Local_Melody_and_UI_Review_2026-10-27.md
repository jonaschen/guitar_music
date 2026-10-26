# Codex：最後本機旋律候選與集中 UI 驗收

2026-10-27。工程完成，等待使用者下班後集中驗收。沒有宣稱達到拍長 95%／旋律 85%；期限仍為 2026-10-28 星期三結束（Asia/Taipei）。

## 交付入口

http://localhost:5173/listening/after-work-2026-10-27/index.html

兩項合計約五分鐘：三組旋律（先原人聲與 B，A 視需要再比較），以及簡潔和弦頁。可直接聊天回覆，也可在入口寫草稿，草稿只存瀏覽器 localStorage 並可下載文字，沒有外送。循環、暫停、來源一致性與資料保護由工程驗證，不交使用者代測。

## 最後本機旋律假說與界線

既有 G 是從 F0 解碼的逐音版本。這次只試一次未曾執行的 SOME 預訓練模型，使用頻譜輸入與學習到的音高／邊界輸出；假說是它可能把歌聲的音高浮動與真正換音分開。這是不同於再調 G 門檻的候選，但不是品質證據，也不保證優於曾失敗的 ROSVOT。

在下載／推論前固定 protocol：三個原定片段、單一模型與官方參數、CPU、本機、準備執行上限兩小時、每片推論最多 300 秒，不訓練、不調參、不改音高或時間、不新增來源挑最好成績。未重開舊失敗候選，無雲端 API 或音訊上傳。

[官方 SOME](https://github.com/openvpi/SOME) 程式為 MIT；[官方 v0.0.1 模型](https://github.com/openvpi/SOME/releases/tag/v0.0.1) 為 CC BY-NC-SA 4.0。本次為本機非商業評估，模型不打包進產品或 git。這不是已完成產品整合；若品質通過仍須保留模型授權界線，不能宣稱可直接商業散布。

選用 0918_continuous256_clean_3spk_fixmel。程式 commit、模型/config SHA、輸入 SHA、版本與 CPU 設定均在報告。原電腦只有 AVX、沒有 AVX2；第一次執行 SIGILL，關閉最佳化快速路徑、改用 portable math kernels 後成功。隔離 cache 另將未使用的訓練 helper 改為 lazy import，避免為推論安裝整套訓練環境；只有這項 source patch，模型權重與參數未改。額外 parselmouth 放在 cache/deps，未改正式 runtime 套件。

| 固定片段 | 原 G 音符 | SOME 音符 | 推論與輸出約耗時 |
|---|---:|---:|---:|
| 第三來源 20–40 秒 | 112 | 49 | 18.5 秒 |
| 第三來源 40–60 秒 | 109 | 58 | 13.0 秒 |
| 小手既有約 14.466 秒片段 | 67 | 41 | 9.6 秒 |

音符變少不是改善指標，不以此排名。沒有逐音真值，沒有數值準確率；訓練資料是否包含歌曲亦未排除。官方輸出第二／三段末端分別超出片長約 6.25／12.09ms，保留在 raw／MIDI，沒有為了好看偷偷裁切；A/B 使用相同稍加尾音的總長。

三組 A/B 使用相同 connectedMelody 三角波、音量與速度；原人聲是完全相同的既有檔案。raw note 到 MIDI 時間誤差均低於 0.8ms；原 G／工作修訂未覆寫。九個音檔均可瀏覽器解碼，A/B 無削波，切換與全部停止通過。

## 和弦核對入口

新區塊提供起始小節、2／4／8 小節、循環、只聽原曲／只聽吉他／原曲＋系統吉他、吉他音量、重播、續播、暫停及附近的設定入口。來源 buffer 與吉他共用 AudioContext 與同一段時間原點；循環及續播按同一時鐘安排，不用兩個 HTML 播放器各跑各的。核對固定 100% 原速與 pluck 音色，不讓隱藏的速度／solo／旋律設定混入。

原曲必須屬於當前譜對應的完成 job；明確讀原曲 endpoint，不誤用先前選的人聲 stem。載入可取消、過期回應不播放、長度不足會拒絕；移調後禁止與原曲直接合奏，仍可分開聽。原曲音量固定 0.45，吉他沿用可調音量；此比例是操作預設，非音樂品質證據。

簡潔頁採明確 `view=accompaniment` 預覽入口，也可按「簡潔和弦頁」切換。將版本保存／還原與核對控制置於主頁，旋律編輯暫時收起但保持掛載與資料；可再開「旋律編輯（實驗）」或完整工具。不是把旋律宣告淘汰，也未改既有預設工作區偏好。和弦編輯／MIDI 等仍在完整工具，完整 UI 收尾待本次人類回饋。

## 工程驗證與已知限制

- 初輪 23 項瀏覽器回歸通過：核對播放、舊合奏、候選套用／Undo 與專注工作區。
- 新增簡潔頁切換案例後，最終受影響的 9 項核對／專注工作區測試通過；合計涵蓋 24 個不同案例。
- production build 通過，既有 alphaTab 大 bundle 提示仍在。
- 真實已保存小手工作譜可載入、播放原曲＋吉他、暫停，檢查前後譜完全相同；桌面與窄版面已檢視。source/guitar 單獨與混合、無系統旋律、同時鐘、連續循環與續播 offset 均有自動檢查。
- 第一輪新增續播按鈕與原編輯器同名導致既有測試歧義，改為「續播這段核對」後通過；不是忽略失敗。一次測試誤從 repo 根目錄啟動，改回 frontend 正確環境；未更改鎖檔。
- 新區塊對整首來源採單一解碼 buffer 快取；長音檔需額外記憶體。本次真實測試為既有片段，不宣稱所有長檔皆通過。

## 保留與重現

- `backend/scripts/run_final_some_evaluation.py`：讀固定 protocol，跑本機模型並保留 raw、MIDI、notes、來源與報告；有完成報告時拒絕覆寫。
- `frontend/scripts/render-final-some-checkpoint.mjs`：相同合成器產生 A/B，公開試聽目錄已存在時拒絕覆寫。
- `frontend/scripts/verify-final-packet.mjs`：驗收入口草稿保存／下載、三組音訊及真實 UI 唯讀驗證。
- 本機 cache：`~/.cache/guitarscribe-some-evaluation/`；產物：`output/evaluation/final-some-2026-10-27/`；音訊：`frontend/public/listening/final-some-2026-10-27/`。
- 入口 HTML 模板：`frontend/scripts/after-work-review.html`，已複製到 `frontend/public/listening/after-work-2026-10-27/index.html`。
- [固定規格](diagnostics/2026-10-27/final-some/protocol.json)、[推論](diagnostics/2026-10-27/final-some/inference-report.json)、[渲染](diagnostics/2026-10-27/final-some/render-report.json)、[時間核對](diagnostics/2026-10-27/final-some/transport-check.json)、[真實頁面](diagnostics/2026-10-27/final-some/browser-check.json)、[CPU import 相容修改](diagnostics/2026-10-27/final-some/cpu-compatibility.patch)。

唯一待辦：使用者下班後集中回報各組 B 的拍長／旋律門檻，以及 UI 是否能自行找到操作並判斷和弦。達標或期限到即依既定停利／停損收束，不再擴張候選。
