# 原曲與 G 合奏時間軸 · 2026-10-18

前置驗收已通過：使用者確認 G 獨聽「自然連貫」。本輪固定 revision `db8c657e-62a5-4fad-a33e-cde25a9e1c0d`，不改音符、和弦、拍點或 decoder，不重開旋律零落感的調參實驗。

## 工程發現與修正

1. 合奏原先由 RAF 到段尾後加 15ms 重開下一圈。改為單一 timer 管理各圈、固定音訊時鐘提前排程；畫面只顯示位置，不觸發下一圈。晚到時略過完整過期圈，停止或換工作世代後不補排舊音。
2. 真實保存 G 的首次核對抓到局部起音延後約 14ms。長譜畫面負載可能使 350ms 預排窗口不足；短選段（不超過 30 秒、旋律音符與其他聲音合計不超過 1024）改為一次排好整段。全曲與密集選段保留分批排程，避免全曲節點無上限建立。
3. 第二次核對確認段首延續吉他比旋律早 55ms：舊 pluck 路徑對過去 onset 直接夾到 currentTime + 5ms，沒有夾到共用起播時間。修正為至少從目前段落／續播時間起播，並從實際排程時間反推弦的衰減 age。保留跨圈共鳴，不藉縮短尾音掩蓋問題。

partner-session 唯讀覆核時鐘、世代、尾音與時間座標；helper-session 提供合奏三圈及停止／續播回歸，主線另補延續弦與旋律同時起播、保留 age 的案例。G 獨聽引擎未改。

## 真實資料核對

Bar 28–35 為分析時間 49.957732426303856–64.4237641723356 秒，長約 14.466 秒。原檔顯示時間另加 18 秒；來源 analysis-source.wav 已裁過起點，因此試聽與 manifest 不再加 18 秒。

`ensemble-alignment-live.spec.ts` 使用原生 AudioContext、實際 App、實際後端編譯。核對 67 個旋律音高／起音，以及每個吉他聲音的起音與刷弦偏移；以相同 origin 比較浮點排程時間，不放寬斷言。這驗證傳給音訊 API 的時間，不是量測喇叭硬體延遲，也不代表拍點或和弦本身符合原曲。

測試阻擋保存與分析，只允許讀取、MusicXML 與 manifest 編譯，結束重新讀取 G 並逐欄比對。並驗證簡化頁原曲接實際合奏、播完、再次播放與停止。

## 重現與單次人工驗收

在 frontend 目錄：

```sh
python3 scripts/prepare-ensemble-listening.py --revision db8c657e-62a5-4fad-a33e-cde25a9e1c0d
GUITARSCRIBE_ALIGNMENT_PACKET=1 GUITARSCRIBE_RECOVERY_REVISION=db8c657e-62a5-4fad-a33e-cde25a9e1c0d bash scripts/verify-workflow.sh
```

產物位於 ignored `public/listening/ensemble-2026-10-18/`，包括原曲取樣裁切、時間與 revision 設定、來源及雜湊紀錄，以及 `scripts/ensemble-listening.html` 副本。頁面內嵌實際 App，以原生控制事件選固定 G、Bar 28–35、100% 速度與合奏；沒有另寫合成器，也不改使用者的樂譜。此工具供本機驗收，依賴目前 App 控制標籤；自動測試會在標籤變動或載入失敗時揭露問題。

開啟 http://localhost:5173/listening/ensemble-2026-10-18/index.html ，按「依序播放原曲與合奏」，約 30 秒。只需回報「節拍與和弦跟得上／有明顯錯位」，有問題可補前半／後半或秒數。不再要求操作保存、找版本、測循環或重評獨聽連貫性。

## 保留界線

分段先後比較用來判斷音樂跟隨，不是逐取樣同步量測。長時間背景分頁節流仍可能中斷下一圈；不承諾任意負載無縫。單次段尾 Stop 會截斷殘留 release，而循環保留尾音共鳴；沿用既有語意。整首準確率與器樂旋律仍未驗收。

## 10/20 接續驗證與環境恢復

主機重啟後，先前 /tmp 測試紀錄與程序已不存在，不能把上次未完成的整套驗證記為通過。Docker 現有 image／overlay 儲存層缺檔，`compose up --no-build` 無法恢復容器。未刪除或重建 Docker 資料；另以使用者快取目錄的獨立 Python venv 與本機 Vite 恢復驗收所需 API/UI。

本機 Python 環境位於 `/home/jonas/.cache/guitarscribe-runtime`，依 backend/pyproject.toml 安裝基本與 dev 相依，沒有安裝選配 Demucs／Basic Pitch；因此此恢復只驗證保存譜與播放流程，不宣稱新的音訊分析環境已恢復等效。沿用原 output/work，設定長 TTL 避免啟動後清除舊驗收來源。原保存譜在 live tests 前後核對不變。

本機恢復指令（各自在長駐終端執行）：

```sh
# repository: guitarscribe/backend
GUITARSCRIBE_WORK_DIR=/home/jonas/gemini-home/music_analysis/guitarscribe/output/work GUITARSCRIBE_JOB_TTL_SECONDS=1000000000 /home/jonas/.cache/guitarscribe-runtime/bin/python -m uvicorn app.api:app --host 0.0.0.0 --port 8000
# repository: guitarscribe/frontend
npm run dev -- --host 0.0.0.0 --port 5173
```

10/20 整套初跑 76 項中 75 項通過，一項續播 age 邊界失敗：`baseAge + startAt - contextStart` 在相同起播時間下仍可能因相加相減得到略低於 baseAge 的浮點數。改為 `baseAge + (startAt - contextStart)`，保留同時起播的精確 age；測試未放寬。

10/20 最終結果：

- 修正 age 後，合奏／工作區相關 14 項全部通過；涵蓋首次失敗項及新增延續弦案例。其餘已通過測試未因單一算式調整重跑，不將前次 75/76 寫成一次全過。
- 真實保存 G 的 4 項 live 測試全部通過（1.7 分鐘），包含原生 AudioContext 下 67 音與吉他排程、簡化頁、完整／專注模式修譜及還原。紀錄 `/tmp/guitarscribe-live-20261020.log`。
- 最終 TypeScript、Vite build、git diff --check 通過。保存 revisions SQLite 檔案 SHA-256 前後一致；既有 G 獨聽 WAV 的 SHA-256 仍為 `0d6699e607bff97340f5d8d78646838e368c783718249ab5f359fb1489124650`。
- 目前只待本 checkpoint 的原曲／合奏音樂跟隨聽感驗收。
