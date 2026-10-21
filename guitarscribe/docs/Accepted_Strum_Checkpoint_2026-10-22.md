# B 版固定與尾段核對 · 2026-10-22

使用者：「B 比較對，但是B 的最後一次換刷好像也有一點早（我的體感，沒有確切比較過原曲）。」固定相對偏好，不記為整段通過，不將未確定體感轉成第三個150ms修正。

## 尾段查證

partner-session 核對最後換和弦 Am→Em 在裁切版5.855秒（分析60.813061秒）。後面還有5次Em刷奏，最後一刷在7.463秒，距7.5秒裁切僅37ms；六弦起音展開60ms，最後弦音會被截斷。「最後換刷」可能指兩種不同事件。

Am→Em 的伴奏模板偏好 crossing 約在保存邊界後14–38ms；原曲混音較雜，先在3–26ms短暫轉正，之後回負，再於189–212ms轉正。這些非毫秒真值，不能據此再加150ms。保留B及第三處時間原樣。

## 可重現候選及 MIDI

`docs/accepted-strum-recipe-2026-10-22.json` 固定來源revision、編譯版本hash、兩個source_id與原首刷時間。`backend/app/evaluation/strum_timing.py` 建立不修改輸入的performance候選，版本／錨點不符、重複指定、非首刷或延後跨越下一刷（含弦間offset）會拒絕。只修改兩個首刷及前和弦end/sustain_end，其餘音高、強弱、起音、旋律、拍點保持相同。新manifest有獨立hash。

MIDI由相同candidate manifest輸出，單元測試解碼MIDI tick驗證首刷延後而旋律及下一刷不動。MIDI音色／包絡依播放器而定，不宣稱與WebAudio尾音相同。既有`export_midi(score)`委派共用匯出函式，不改其編譯語意。

重現（repo根目錄）：

```sh
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/build_strum_checkpoint.py \
  --recipe guitarscribe/docs/accepted-strum-recipe-2026-10-22.json \
  --output guitarscribe/output/evaluation/accepted-strum-2026-10-22
```

產物含manifest.json、performance.mid、recipe.json、report.json。生成前後GET保存譜一致；沒有POST保存、沒有另存score revision，沒有啟用產品預設。這是可重現performance checkpoint，**正式編輯器保存／重載修正仍待整合**。直接保存和弦邊界會產生另一種+476/+441ms效果，不得冒充此候選。helper-session初步把最新B誤認為邊界版，主線已依刷奏產生器及實測更正，未採用其直接改score建議。

Checkpoint輸出目錄必須不存在；重跑請指定新目錄，不覆寫已驗收產物。partner-session唯讀審核未見此兩處recipe的時間邏輯阻擋問題，提出覆寫風險後已補拒絕保護並驗證既有manifest不變。

## 同版補足尾段

```sh
cd guitarscribe/frontend
node scripts/prepare-alignment-isolation.mjs db8c657e-62a5-4fad-a33e-cde25a9e1c0d --tail-context
```

此模式讀上述backend產出的manifest，與已獲偏好的JS控制逐event完整比對後才渲染。保留前輪開始位置，延伸到原片段末尾，再保留350ms合成尾音；原曲最後40ms淡出。多保留原有F和弦上下文，沒有新增第三處修正。前輪7.5秒音訊在1 PCM16 LSB內相同，完整音檔9.816秒，最後500 samples不超過1 LSB，沒有硬切刷弦。

唯一人工項：http://localhost:5173/listening/strum-tail-2026-10-22/index.html 。播放B約10秒；若仍早，回報5.9秒附近／7.5秒附近／不確定，或補足片尾後較自然。不要求再比較A/B，不將此項當整首驗收。

## 驗證

- `pytest -q tests/test_strum_timing.py tests/test_midi.py`：29 passed。
- 真實G候選完整event與已通過JS修正逐筆一致，MIDI成功產生；保存譜不變。
- 288個弦音排程逐項核對、峰值0.551無削波；保留片段波形在1 LSB內一致。
- Chrome核對播放至結尾、重播、停止、無pageerror。

下一步仍優先完成局部時間語意與編輯器／修訂／MIDI一致的正式整合，保留過期候選保護；不硬編歌曲時間進產品、不重新調G解碼器、不把試聽頁當產品已完成。
