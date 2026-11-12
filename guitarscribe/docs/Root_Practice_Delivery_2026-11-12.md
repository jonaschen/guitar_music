# 根音抓歌協作第一版交付

2026-11-12。方向依使用者要求改為「軟體提供線索，使用者聽辨、比較與採用」。完整[計畫與反思](Root_Practice_Plan_2026-11-12.md)先於實作保存；候選實驗失敗與產品範圍修正均保留。主旋律自動辨識仍凍結。

## 已實作的完整流程

從歌曲頁進入根音練習，或使用 `?practice=roots` 直接開啟。使用原分析來源與原調，根音工作稿獨立保存，不修改和弦Score、調性、歌詞簡譜筆記或舊修訂。

| 功能 | 行為 |
| --- | --- |
| 三個參考音 | 本機聲學候選最多三個不同音級；點擊只試聽，採用才保存。無線索／同分無法區分時不湊數。 |
| 自行聽辨 | 可隱藏提示，使用十二音比較；可保留「還聽不出來」。沒有假機率、對錯評分或自動作答。 |
| 聲音比較 | 原曲、原曲＋根音、根音三模式；一致音色與音域、獨立音量、當段循環及可選前後文。固定試音脈衝明示非原曲節奏。 |
| 選段與修正 | 秒數時間軸、不捏造小節；上一段／下一段、保留空隙、在游標分段、與下一段合併。結構改動清除相關確認，可復原。 |
| 工作進度 | 採用／待聽、復原／重做、整首已採用根音連聽、暫停及正確位置續播；重新開啟保留進度與本分頁所選區段。 |
| 資料保護 | 獨立SQLite、版本衝突保護、分頁草稿、離線恢復、原始草稿下載、明確重新載入、同來源完整備份還原及文字匯出。 |
| 不完整來源 | 原曲到期仍可讀保存進度及下載；音訊不可用可改單音試聽。候選未安裝／失敗／取消時可繼續手動操作。 |
| 手機與鍵盤 | 320／390／768／1440px檢查，候選與採用集中一區，工具折收，焦點可見；選段只水平移動行進列。 |

這是共用受邀空間，不是個人帳號。使用者採用是個人工作判斷，不是人工驗證真值，也沒有用來訓練模型。

## 候選品質與計畫反思

兩個固定方法都沒有通過事前設定的「三份HU33每首Top3至少80%、救回原錯誤至少40%」開發門檻。沒有調低門檻、挑曲、改時間或另換參考。

第一個方法每frame取同根音profile最大值。檢查實際字典後發現每個根音均有18個profile，因此只增加一次整組平均的比較。平均法固定用於實驗工作區，不按曲挑選方法；它仍是未通過品質門檻的參考線索，不替換正式辨識預設。

| 既有開發來源 | 原版根音 | 平均法前三參考音涵蓋 | 原錯誤區間救回 |
| --- | ---: | ---: | ---: |
| GuitarSet SS2 | 92.2% | 95.3% | 39.6% |
| GuitarSet Rock1 | 97.4% | 98.2% | 28.4% |
| GuitarSet Funk3 | 82.4% | 87.7% | 30.0% |
| GuitarSet SS3 | 94.2% | 95.4% | 20.4% |
| GuitarSet Rock2 | 84.2% | 95.6% | 72.0% |
| GuitarSet Funk2 | 22.1% | 52.4% | 38.9% |
| HU33 04 | 64.2% | 79.8% | 43.6% |
| HU33 18 | 58.3% | 69.8% | 35.2% |
| HU33 21 | 73.2% | 88.7% | 58.0% |

分母依原固定參考範圍、實際時間加權；候選空白／缺覆蓋仍計入未命中。這些是既有開發資料，不能當任選新歌成功率。實驗只重用九份trace，新增推論0；固定區段內含多個真實根音的失敗亦保留。六份舊GuitarSet score缺少duration，僅由雜湊相符的原音訊metadata補入評估副本，未修改原檔或參考區間。

另直接讀取、核對雜湊的原始標註重算，兩個方法全部主要分數與先前逐區間診斷版本精確相同。精確數值：[max結果](evaluation/root-candidates-max-2026-11-12.json)、[mean結果](evaluation/root-candidates-mean-2026-11-12.json)。

產品決策是完成明示實驗性的互補工具，讓使用者能改選十二音與保留不確定；不是將門檻失敗稱為通過。是否能減少整理成本、是否適合使用者聽辨，留待完整版本的單次試用。

## 工程驗證

- 56項相關後端測試通過：候選語義／同音異名／N與未知、真實frame時間與尾端、重複profile、資料驗證、八執行緒同版競寫、重開、來源過期、裁切音訊、取消／忙碌／重試、舊試聽與歌詞筆記回歸。
- 根音瀏覽器／純函式檢查涵蓋試聽零保存、採用、離線恢復、衝突保留、分段／合併、JSON還原、整段連聽與續播、過期候選請求、四尺寸與鍵盤焦點。最後另補「原分析已過期，保存的練習仍可開啟、單音試聽及下載」入口回歸；最終完整執行結果記於發布段。
- 真實WebAudio buffer做頻率相關檢查，所選E／G音高符合；源音訊與根音起點共用同一AudioContext clock，切換及暫停取消舊聲音。另限制單音釋放尾端，不跨入下一段。
- 原曲播放API核對練習來源指紋；原job內容變動時拒絕混播，仍可備份既有練習。最終14項根音後端測試再次通過，包含正確／錯誤指紋與裁切音訊。
- 22項相關原產品測試完成：移調、凍結旋律、原曲音量、歌詞與簡譜及標記流程。一次整批執行有1項歌詞保存輪詢逾時；隔離重查通過，未改該功能或放寬舊斷言。這項初次失敗保留記錄。
- TypeScript／production build通過。大型AlphaTab既有chunk提示仍存在。
- 觀測插件重新從固定本機source編譯，HU33 18的968個精簡frame與歷史trace完全一致。此為一次推論整合檢查，與零推論候選評估分開計數。
- 《膽小鬼》258秒與《沒那麼簡單》304秒，用獨立工作目錄、真音訊、真API與SQLite完成候選準備、原曲＋根音、採用、重開與連聽；兩首原Score前後相同，四尺寸0頁面例外。這是工程驗證，沒有新歌曲音樂準確率標註。

本機證據：`output/evaluation/root-practice-2026-11-12/`，含直接參考重評、觀測parity、隔離來源與候選、瀏覽器截圖及結果。正式資料未匯入測試採用紀錄。

## 重跑與環境

```bash
# 在 repo 根目錄：九份已凍結快取，不跑模型
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/evaluate_root_candidates.py guitarscribe mean
/home/jonas/.cache/guitarscribe-runtime/bin/python guitarscribe/backend/scripts/evaluate_root_candidates.py guitarscribe max

# 在 guitarscribe/backend：相關單元/API測試
/home/jonas/.cache/guitarscribe-runtime/bin/python -m pytest -q tests/test_root_practice.py tests/test_audition_playback.py tests/test_melody_notes.py tests/test_lyric_worksheets.py

# 在 guitarscribe/frontend：完整根音互動與build
npx playwright test --config playwright.root.config.ts
npm run build -- --base=/root-practice-2026-11-12/
```

候選工具使用隔離Vamp插件，不改全域VAMP_PATH或原引擎。預設安裝於 `~/.cache/guitarscribe-root-candidates/plugin`，可由 `GUITARSCRIBE_ROOT_PLUGIN_DIR` 指定；manifest核對library SHA256。每次觀測在子程序，180秒上限、跨程序檔案鎖、取消後回收程序，完整trace暫存用完刪除，只保存12音frame快取。來源音訊雜湊、原job／score身分與方法版本綁定。

重建命令：`python guitarscribe/backend/scripts/build_root_candidate_plugin.py guitarscribe`。目的目錄必須不存在；需要既有固定Chordino source、Vamp SDK、Boost與工具鏈。此工具不會自動下載或安裝套件。換機／Docker尚未包含這個觀測插件時，顯示工具未準備，手動練習仍可用；本次承諾的受邀主機已安裝並驗證。

新資料為 `work/root-practice.sqlite3`、每job的 `root-evidence-v1.json`；備份時要連同既有工作資料保存。練習JSON可單獨下載，但不含來源音訊。

## 發布與回退

新入口使用既有受邀服務的 `/root-practice-2026-11-12/?practice=roots`，有job時可附上 `&job=...`。保留原首頁與11-05閱讀入口，原帳密及資料位置沿用。後端增加獨立API，發布需在沒有分析工作時重啟原web服務；不更動ngrok方案。

發布備份：`output/backups/root-practice-2026-11-12/`。四份SQLite以backup API建立一致副本並通過integrity_check，另記錄全部118個既有網站檔案雜湊與服務設定。只發布index／assets／font／soundfont，不複製歷史聽音素材。已驗證的兩首精簡候選快取可依來源與音訊雜湊重用，人工測試進度不能複製到正式資料。

回退可撤下新入口並將API入口還原到備份的 `api-before.py` 後重啟原服務；保留新練習資料庫及使用者草稿，不回灌舊DB蓋掉使用者資料。新的插件只供新候選服務使用，舊和弦流程不受影響。

最終根音互動測試12項全部通過，包含原分析過期後的完整備份與單音路徑；TypeScript／production build再次通過。實際發布複查補上視窗縮放後保持選段可見、長歌名行距，以及原曲來源指紋核對。兩首真實歌曲在正式5273入口完成原曲＋根音、試聽零寫入、四尺寸選段可見及0頁面例外檢查；未匯入測試判斷。

首次正式檢查早於服務啟動完成而連線遭拒；待服務就緒後成功。第二首的自動化檢查曾因每個API請求先不帶帳密、反覆挑戰登入而碰到既有限流；已改為測試API請求主動帶邀請認證，並遇到失敗立即停止，沒有放寬登入保護。來源／候選快取本身相符。

正式發布核對記錄在備份目錄的 `after.json`，並保存[發布驗證摘要](evaluation/root-practice-release-2026-11-12.json)：118個既有網站檔案、4份舊資料庫logical hash與服務環境相同，新練習資料庫0筆人工測試紀錄；未登入仍拒絕存取，兩來源錯誤指紋皆拒播。新入口沿用邀請帳密，只能在運行服務的家中電腦以localhost開啟，沒有新外網網址。

試用入口：[膽小鬼根音練習](http://localhost:5273/root-practice-2026-11-12/?practice=roots&job=83a3643ab3814172a046cebf709f3413)、[沒那麼簡單根音練習](http://localhost:5273/root-practice-2026-11-12/?practice=roots&job=a3be29912a7045448765290d7cba2f6c)。下一步請使用者完成一小段，評估候選比較、採用與整理是否真的減少抓歌成本；這個主觀結果目前仍未知。
