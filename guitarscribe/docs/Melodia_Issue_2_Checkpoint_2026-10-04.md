# Issue #2：MELODIA 隔離 benchmark

本輪隸屬 [器樂主旋律 #2](https://github.com/jonaschen/guitar_music/issues/2)，由 [總追蹤 #6](https://github.com/jonaschen/guitar_music/issues/6) 管控。I1／I2 已由使用者否決，不再調整該路徑；中段細 pYIN 只有些微改善，暫不升級正式預設。

## 選擇與界線

採 Essentia 的 PredominantPitchMelodia 作為既有 polyphonic predominant-melody 比較組，而非另一版最高音／最強峰值選取。依 [官方演算法說明](https://essentia.upf.edu/reference/std_PredominantPitchMelodia.html)，它以連續 pitch contours 估計多音音樂的主要旋律，並建議 EqualLoudness 前處理。官方用途說明不保證本曲的小提琴一定成功。

[官方授權頁](https://essentia.upf.edu/licensing_information.html) 與 [固定版本 PyPI metadata](https://pypi.org/project/essentia/2.1b6.dev1389/) 記錄授權條件。此處只做本機隔離研究；**不是已取得產品商用／再散布許可，也不是正式依賴採用決策**。正式整合前另審程式、依賴與部署方式。此次沒有使用或下載預訓練模型。

## 可重現設計

- 拋棄式 `docker compose run --rm --no-deps` 容器，套件只安裝在該容器 `/tmp/essentia-benchmark`，結束即隨容器消失。沒有改 `pyproject.toml`、正式 image 或後台程序。
- 固定 `essentia==2.1b6.dev1389`，為目前 Python 3.10 環境可取得的 wheel；不宣稱是所有 Python 版本的最新套件。
- 來源同一 job 的伴奏與裁切原曲。M1＝伴奏；M2＝原曲，兩者演算法／參數相同，只比較輸入來源。
- 上下文分析時間 218–235 秒，試聽 220–233 秒，各 13 秒；原檔起點 18.5 秒不再次加到分析輸入。
- mono／44.1kHz／EqualLoudness、hop 128、frame 2048、minFrequency 80、maxFrequency 1760、guessUnvoiced false；其餘使用該固定版本預設。
- 保存 Hz 與原始 confidence；非正音高／非正信心留白，不補音、不升八度、不按調性修正、不套 G、不改拍點。
- 兩檔使用同一連續相位合成器與音量。較多有聲影格不表示較準，也不代表演算法已辨認小提琴。

重現（project 目錄）：

```sh
docker compose run --rm --no-deps -v "$PWD/backend:/app" backend bash -c 'python -m pip install --no-deps --only-binary=:all: --target /tmp/essentia-benchmark essentia==2.1b6.dev1389 && PYTHONPATH=/tmp/essentia-benchmark:/app python -m app.evaluation.melodia_benchmark /app/output/work/jobs/12fac6df94ee48a282fe2c542df3ae22 /app/output/evaluation/NEW_DIRECTORY'
```

輸出目錄必須尚不存在。`report.json` 記錄套件／引擎／numpy／librosa 版本、來源 hash、參數、上下文與耗時。WAV 與 JSON 為本機產物、不納入 Git。正式採用仍需獨立授權與依賴驗收。

## 驗收與停止條件

已成功完成真實片段 benchmark：套件 2.1b6.dev1389、numpy 1.26.4、librosa 0.11.0，M1／M2 各推論約 1.12 秒（不含安裝／前處理），各輸出 5859 個上下文影格；13 秒試聽內 M1 有聲約 7.91 秒、M2 約 8.70 秒。其餘保留演算法留白，不因覆蓋不足而自動猜音。這是工程結果，不是主旋律已抓對。

輸出在 `output/evaluation/melodia-benchmark-2026-10-04/`；發布的 M1／M2 都經瀏覽器解碼確認為 13 秒、有非零音訊。試聽基底 `http://localhost:5173/listening/melodia-benchmark-2026-10-04/`，檔名 `M1-accompaniment.wav`／`M2-original.wav`。目前狀態為待聽感，#2 保持開啟。

22 項 optional adapter／來源診斷／G／候選相關測試通過；adapter 驗證的是資料形狀、非有限值與留白，不能當作 MELODIA 準確率。實際歌曲推論與可聽輸出另列為 benchmark 子項。

人工只需回答 M1 或 M2 是否跟上伴奏中的主要旋律。若兩者都不對，本 issue 保持開啟並記錄失敗，下一步轉向細分離或不同既有方法；不盲目增加本方法參數特例。若有改善，先另一個器樂片段再談接入候選／編輯。Bar 30–31 與 G 仍是獨立工作，不受此實驗修改。
