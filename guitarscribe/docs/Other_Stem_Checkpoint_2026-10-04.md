# 器樂來源細分比較（Issue #2）

## 依據與本輪範圍

使用者確認 R 與 M1 在試聽 0–2 秒及 7–11 秒都較接近，沒有證據支持 R 新增音符優於原 M1。停止放寬有聲門檻，保留 M1；2–7、11–13 秒仍待查，不能直接當作每音皆錯。

這輪只改來源層：用現有 Demucs htdemucs 四軌模型，對裁切原曲分析時間 218–235 秒做獨立局部分離。比較：

- N：同一輪的 drums + bass + other，排除 vocals 的伴奏控制。
- O：同一輪的 other，排除預估 drums／bass／vocals 的剩餘器樂群。

[Demucs 官方專案](https://github.com/facebookresearch/demucs) 的四軌分類不是專用小提琴模型。other 仍可能混合吉他、鍵盤等，分離也可能漏掉／損傷主旋律。N 用來控制「局部分離不同於原 M1 的整曲分離」這個變因，不單憑 O 與 M1 差異推斷移除鼓／貝斯有效。

## 固定條件

- 17 秒上下文、13 秒試聽，來源 hash 保留；不將原檔略過的 18.5 秒重複加入。
- CPU、2 threads、seed 0、shifts 0、overlap 0.25；不聲稱不同硬體皆逐位元相同。
- 保存四條 FLOAT 原始估計軌，無逐軌峰值正規化；N／O 的真實音訊試聽共用必要的防削波增益。
- 音高分析固定原 MELODIA 參數（80–1760Hz、guessUnvoiced false、EqualLoudness）；不使用 R 的門檻、移八度或 G 分音。
- 保存套件／torch 版本與模型權重 hash，估計軌必須維持來源取樣數和聲道數。實際安裝的是 Demucs 4.1.0，會從 Hugging Face 取得 safetensors；已改為明確固定 `adefossez/HTDemucs` snapshot `cbc8a9b1a87023b7fd74e7b3412e6321c0eab003`，不依賴會更新的 main。
- 拋棄式容器執行，模型僅快取於 output/evaluation；正式後台、分析與修訂不變。Essentia 正式整合的授權審核仍未完成。

## 重現

```sh
docker compose run --rm --no-deps -v "$PWD/backend:/app" -e HF_HOME=/app/output/evaluation/benchmark-hf-cache backend bash -c 'python -m pip install --cache-dir /app/output/evaluation/benchmark-pip-cache --no-deps --only-binary=:all: --target /tmp/essentia-benchmark essentia==2.1b6.dev1389 && PYTHONPATH=/tmp/essentia-benchmark:/app python -m app.evaluation.other_stem_benchmark /app/output/work/jobs/12fac6df94ee48a282fe2c542df3ae22/analysis-source.wav /app/output/evaluation/NEW_DIRECTORY'
```

輸出目錄必須尚不存在。原始音訊、模型快取與生成音檔都不納入 Git，也不上傳 GitHub。25 項來源組合／MELODIA／G／候選相關測試通過；測試來源加總與不可變性，不代表分離或旋律品質通過。

## 聽感決策

固定模型重跑已完成：分離本身約 68.4 秒，輸出模型 YAML／safetensors SHA-256 皆有記錄。N 試聽有聲 2315 影格、O 2611 影格，hop 128／44.1kHz；這不是準確率。O 合成 WAV 與首次試驗逐位元相同，正式使用可重現的固定 snapshot 版本。

完整產物在 `output/evaluation/other-stem-pinned-2026-10-04/`。發布三檔皆已瀏覽器驗證為 13 秒、有非零音訊：`O-other-source.wav`（真實剩餘器樂）、`O-other.wav`（由 O 追蹤的合成旋律）、`N-local-accompaniment.wav`（同輪全部伴奏的合成旋律）。連結基底 `http://localhost:5173/listening/other-stem-2026-10-04/`。

先確認 O-source 中是否保留使用者認為的主要器樂旋律，再判斷 O 的合成音是否跟上。必要時對照同輪 N，而不是只看有聲比例。特別關注 2–7、11–13 秒，同時留意原先較好的 0–2、7–11 秒是否變差。

若來源中主旋律被破壞，就不能透過繼續调 MELODIA 修好；若來源清楚而音高仍錯，回到多音旋律辨識。無論結果如何，不把本候選自動套用至正式譜，#2 保持開啟，#3 合奏與 #4 編輯整合未被算作完成。
