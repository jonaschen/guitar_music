# Codex：ROSVOT 固定候選結果

使用者於第三來源驗收失敗後明確要求繼續。依 [本輪計畫](ROSVOT_Checkpoint_Plan_2026-10-25.md)，只測一個官方預訓練歌聲音符模型，未訓練、未逐曲調參，尚未接入產品。兩個助手分別做獨立方法／事件解析審查及既有contour現象盤點／比較頁測試。

## 已完成與未證實的事

官方ROSVOT以音訊特徵、RMVPE音高及自動RWBD邊界預測音符。相較G直接將F0轉整數音高，這是不同的音符事件預測路線，不是再調G靈敏度。[官方專案](https://github.com/RickyL-2000/ROSVOT)、[論文](https://aclanthology.org/2024.acl-long.526/)。

官方程式commit `3c8332bf43adae35f6e4d64971862f2f6139b310`；只修改推論裝置為CPU、略過CUDA搬移兩行。checkpoint、辨識閾值、word條件及後處理未依結果改動。CLI預設note threshold=.85（覆蓋config的.8）、word threshold=.5，RWBD自動開啟，無人工歌詞或時間。note boundary min gap官方config為90ms；不能宣稱短音皆可保留。

權重從README的官方Google Drive連結取得，zip SHA256 `b6055e81315b93415c9bd7fc48e10a28a3da1bea960cab7385483bd7443ba852`。下載、相容依賴均放獨立cache，production環境依賴未改，沒有音訊雲端上傳或付費。三個模型weights與config、依賴版本及CPU patch都記錄於 `docs/diagnostics/2026-10-25/rosvot-provenance.json`／`rosvot-cpu-compatibility.patch`。

CPU batch=1、workers=0；6個固定輸入推論loop約24.6秒，不含模型載入／下載／環境準備，未量測峰值記憶體。不能將loop時間稱為使用者端到端等待時間。僅此一組參數執行一次，沒有參數掃描。

## 控制結果：尚未通過完整品質關卡

| 控制 | 結果 |
|---|---|
| 長顫音A4 | 保留為1音；起音誤差−31ms、音尾+24ms，通過既定50ms判準。既有G在此控制也為1音，不能稱為相對G的改善證據。 |
| 九音諧波控制 | 只輸出7音，嚴格音高／起音匹配3/9；同音C4重奏合併、D4未正確保留、數處休止被音符覆蓋。合法75ms F4有出現，但延長至約117ms。**失敗。** |

合成音在歌聲模型訓練分布之外，但這不能抹除失敗，也不能稱模型已保證保留短音、休止與重奏。本次只能做探索性聽感比較，不升級預設、不宣稱通過前一輪嚴格控制或產品可用性門檻。

## 固定真實片段

| 片段 | G音符數 | ROSVOT音符數 | G短於100ms | ROSVOT短於100ms |
|---|---:|---:|---:|---:|
| 第三來源20–40秒 | 112 | 49 | 59 | 0 |
| 第三來源40–60秒 | 109 | 55 | 57 | 0 |
| 先前較自然片段 | 67 | 43 | 26 | 0 |
| 先前現場失敗片段 | 88 | 43 | 45 | 0 |

**音符變少不是準確率。** 新模型在部分G休止處輸出音符，也可能漏掉事件；目前沒有真實片段逐音真值。先前較自然片段亦保留作回歸，未挑掉現場片段的工程結果。M4Singer及輔助模型訓練歌曲重疊未排除，不能稱作獨立未見曲目的泛化證明。

G和contour盤點也找到30.163–30.511秒的六個短交替事件及數個大音程跳轉，但沒有真值，不能直接標示顫音或八度錯誤。見 [現象盤點](Third_Source_Contour_Patterns_2026-10-25.md)。

## 時間與播放保真

原始NPY中pitch=0表示休止，解析時仍累加它的時值；保留相鄰同音事件、所有正時值音符，不補音、不刪音、不量化。六段事件與原始MIDI全部在1 tick內一致，末尾與來源相差不超過模型一個hop（128/24000秒）。獨立解析fixture 6 passed，涵蓋休止、同音重奏、5ms事件及無效輸入拒絕；助手亦獨立覆核。

探索性試聽只給預定三組：第三來源兩段，加先前較自然片段。每組「原人聲／A現有G／B模型」，相同triangle音色、0.12增益及固定velocity；保留休止與事件時間、不人工移調或校時。現場片段的模型輸出仍完整留存，不另增加使用者試聽負擔。

入口：`http://localhost:5173/listening/rosvot-checkpoint-2026-10-25/index.html`。使用者判斷哪版音高／拍長較接近、是否更自然，以及是否漏音或拖過休止。偏好B也只代表值得下一步驗證，不直接推論可交付。

## 重現資料

- 方法審查：[ROSVOT_Method_Review_2026-10-25.md](ROSVOT_Method_Review_2026-10-25.md)。
- 全部來源hash、原始NPY／MIDI、模型記錄及六段結果：`output/evaluation/rosvot-checkpoint-2026-10-25/`。
- 版本化證據：`docs/diagnostics/2026-10-25/rosvot-results.json`、`rosvot-render.json`、`rosvot-provenance.json`、`rosvot-cpu-compatibility.patch`。
- 解析：`backend/scripts/evaluate_rosvot_checkpoint.py`；渲染：`frontend/scripts/render-rosvot-checkpoint.mjs`。不改工作譜／保存G／既有伴奏。


比較頁Playwright 1 passed（4.0s），驗證三組音軌、快速切換、互斥播放、停止與模擬404；桌面畫面檢視完成，未把頁面測試當作品質證據。

重現推論命令（在獨立cache的官方checkout，以 `git apply --unidiff-zero` 套用記錄的CPU patch後）：

```bash
PYTHONPATH=/home/jonas/.cache/guitarscribe-rosvot-evaluation/deps:. \
OMP_NUM_THREADS=2 MKL_NUM_THREADS=2 OPENBLAS_NUM_THREADS=2 \
MPLBACKEND=Agg CUDA_VISIBLE_DEVICES='' \
/home/jonas/.cache/guitarscribe-runtime/bin/python inference/rosvot.py \
  --metadata /home/jonas/gemini-home/music_analysis/guitarscribe/output/evaluation/rosvot-checkpoint-2026-10-25/inputs.json \
  --bsz 1 --ds_workers 0 --sync_saving \
  -o /home/jonas/gemini-home/music_analysis/guitarscribe/output/evaluation/rosvot-checkpoint-2026-10-25/raw
```

原始weights不提交或重新散布。此流程為本機研究檢查點，未提供產品安裝／正式部署保證。
