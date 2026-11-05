# GuitarScribe 專案入口

以下路徑以包含 `guitarscribe/backend/app/cli.py` 的 workspace 為相對根；目前工作目錄也可能直接位於 `guitarscribe/`。先定位實際根目錄，不依賴固定家目錄。此對照核對於 2026-11-05，執行前以現行檔案及 `--help` 為準。

## 找到現有能力

| 工作 | 相對於 `guitarscribe/` 的入口 |
| --- | --- |
| CLI 與分析選項 | `backend/app/cli.py` |
| 引擎路由、fallback、後處理 | `backend/app/core/pipeline.py`、`backend/app/core/config.py` |
| 可用依賴與 Python 範圍 | `backend/pyproject.toml`、`backend/Dockerfile` |
| 分軌能力 | `backend/app/services/capabilities.py`，並追蹤 pipeline 的 separator |
| 音符與輪廓 | `backend/app/analyzers/melody/basic_pitch_adapter.py`、`pyin_adapter.py`、`backend/app/models/melody_contour.py` |
| 節奏與和弦 | `backend/app/analyzers/beats/`、`backend/app/analyzers/chords/` |
| 譜面與來源資料 | `backend/app/models/score.py`、`analysis.py` |
| 分層參考評分 | `backend/app/evaluation/quality_report.py`、`reference_timing.py` |
| 標註與來源查核 | `backend/app/evaluation/annotations.py`、`annotation_audit.py` |
| 跨曲比較 | `backend/app/evaluation/batch_report.py`、`backend/scripts/audit_song_batch.py` |

按任務閱讀 `docs/issues/quality-gates.md` 與最新相關工作文件。評分器研究另讀 `docs/evaluation/Validator_Protocol_2026-11-05.md` 及其後續結果；文件日期不代表所有舊結論仍適用。

## 執行環境與命令

核對時專案要求 Python `>=3.10,<3.13`。librosa 為基礎依賴；`melody`、`separation`、`quality` 等 extras 分別提供 Basic Pitch、Demucs、mir_eval。依賴被列出不表示目前環境已安裝。Essentia 與 music21 不在當時的依賴清單，不要假設可直接匯入。

在現有後端 Python 環境、工作目錄 `guitarscribe/backend/` 下查詢：

```bash
python -m app.cli analyze --help
python -m app.cli quality-report --help
python -m app.cli quality-audit --help
python -m app.cli quality-batch --help
```

容器方案的 Compose 檔位於 `guitarscribe/docker-compose.yml`，不是 workspace 根目錄。先確認現有服務、映像與掛載；容器中 app 在 `/app`，基本 Compose 只掛 fixtures、output 與 rhythm-patterns，不自動掛入後端原始碼。不要把主機音訊路徑直接當容器路徑，也不要只為讀取 help 重建昂貴映像。

下列為模板；將 `input.wav`、`analysis-run/`、`score.json` 等替換為已確認的實際路徑，先建立獨立輸出目錄。CLI 未提供裁切參數，片段須使用既有裁切流程準備並記錄來源偏移。

```bash
python -m app.cli analyze input.wav --melody-mode vocal --output analysis-run/score.json
python -m app.cli quality-audit annotations/ audio/ --output analysis-run/annotation-audit.json
python -m app.cli quality-report score.json annotation.json --output analysis-run/quality.json
```

`--melody-mode` 在核對時只接受 `vocal`、`guitar`、`mix`；內部 pipeline 支援的值不一定是 CLI 選項。

人聲分離須同時滿足：separator 已啟用、Demucs 可用，且要求中有 `--separate-vocals`。目前 pipeline 在成功分離人聲後走 pYIN，失敗時可能退回 Basic Pitch，分離失敗也可能使用完整混音。讀 score 的 provenance 與 warnings 確認**實際**發生的路徑。不要僅設定 `GUITARSCRIBE_MELODY_ENGINE` 就宣稱已切換引擎；核對時建立 pipeline 的程式並未用該欄位切換 melody analyzer。

## 評分的容易誤判處

- `evaluate` 使用簡化 golden-fixture 指標；部分空參考會得到 `1.0`。其旋律指標不是完整 note precision/recall。正式音樂比較優先使用 `quality-audit` 與 `quality-report`，仍須確認實際標註覆蓋。
- `quality-report` 需要 `QualityAnnotation` 格式，與簡化 golden JSON 不相同。先用現行 Pydantic schema 驗證，不混用欄位名稱或時間基準。
- `quality_gate` 標註有 30–60 秒、來源檔與雜湊等要求；這是現有 gate 的格式限制，不是所有分析都要 30–60 秒。draft 標註不能當已人工驗證的真值。
- 旋律分層報告在核對時把音符區間投影成 10 ms 的半音輪廓，再算 mir_eval。它評估的是轉錄後音符的輪廓，不是模型原始浮點 F0；要研究 F0 需另比較原始輪廓。
- `quality-report` 缺少整層標註時會回 `not_annotated`。僅有零散 melody notes 時，不能假設片段其他地方都已確認為休止；限制到確認完整的評分區段或明確提供 coverage mask。
- 檢查和弦 `*_scored_fraction`：被評分的少量大小和弦高分不能代替整段複雜和弦品質。`N`、未知與詞彙表外和弦必須保留差異。
- `analysis.confidence` 與部分 adapter 的固定 confidence／engine version 欄位不是獨立校準證據；另記實際套件版本、權重與程式 commit。

## 選擇相關驗證

修改後執行與變動層相關的既有測試，例如 `backend/tests/test_evaluation_metrics.py`、`test_evaluation.py`，並用 `rg` 找到對應的旋律／節奏測試。不要為單純分析或技能安裝重跑整個辨識管線。

評分器變動先核對 identity、八度偏移、已知漏音／多音、半倍拍速、小節錯一拍等適用控制案例。控制案例驗證評分器，不計入真實歌曲準確率。讀現有 benchmark 腳本的參數與副作用後再跑，不自動啟動名為 publish／integrate／import 的工作流程。
