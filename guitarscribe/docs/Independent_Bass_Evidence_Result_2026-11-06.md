# A18：獨立低音證據不足，停止本輪固定試驗

日期：2026-11-06。[事前方案與授權](Independent_Bass_Evidence_Plan_2026-11-06.md)、[最終凍結計畫v3](evaluation/independent-bass-plan-v3-2026-11-06.json)、[完整數值及歷程](evaluation/independent-bass-results-2026-11-06.json)。

作者真bass／piano確實通過同錄音對齊檢查，但固定估音規則僅覆蓋8.869%的已知和弦時間，未達30%；因此結果是 **此估音規則的證據不足**，不是「低音機制已被否決」，更不是產品改善。停止這組固定試驗，不放寬range／信心／穩定／品質門檻，不進A16分離bass恢復性、和弦重排或試聽。

## 全曲結果與未知

| 指標 | 結果 | 事前門檻 |
| --- | ---: | ---: |
| 全曲／已知和弦時間 | 357.000／356.280秒 | 全曲共同域，offset0 |
| 穩定可用bass | 31.600秒 | 未估出或不穩定不補值 |
| 已知和弦穩定涵蓋 | 8.869% | ≥30% |
| 原root正確／錯誤時間的穩定涵蓋 | 7.452%／10.911% | 各≥20% |
| Observable flag | 3.091秒 | 不使用reference作觸發條件 |
| 有效TP／FP | 1.419／1.672秒 | TP≥10秒 |
| 有效TP precision | 45.905% | ≥80% |
| 所有已知root錯誤時間的TP recall | 0.972% | ≥20% |
| 原root正確時間的誤觸 | 0.795% | ≤5% |
| 穩定bass不在reference／該類flag | 0／0秒 | 保留且計FP，不手工排除 |

約325.4秒沒有通過穩定估音規則，完整保留為abstention，仍在涵蓋／recall／誤觸的分母。precision只描述3.091秒flag，不外推全曲；因涵蓋不充分，不能用這個低precision證明所有低音反證都無用。原root錯誤分母145.978秒包含diagnostic wrong_root145.745秒及missed_chord0.232秒；root正確分母210.302秒。沒有未知reference／estimate label。

Observable只看穩定bass是否被原estimate完整音集合漏掉；reference僅評估。有效TP需原category為wrong_root且reference包含該bass，其他已知reference flag均為FP。這輪1.672秒FP全部來自原root正確區間；不把品質錯誤、合法非和弦bass或reference N隱去。沒有將bass強制當root，也沒有手改任何音高。

## 同錄音及時間證據

兩個作者ZIP bytes及API base32 SHA1完全符合，只安全讀出 `Fretless Bass.flac`／`Piano.flac`；其他樂器不解壓。作者CC BY-NC4.0授權、Martijn de Boer (NiGiD)署名與原頁來源保留，僅本機非商業研究。

示範MP3與作者API原MP3 byte hash不同，沒有只憑同名宣稱同版。按事前規則，兩軌全曲及前／中／後三等分的八個互相關峰均為 **0秒lag**；bass相關分別0.6701／0.6803／0.6369／0.6904，piano0.6770／0.7072／0.6753／0.6461，全部高於原門檻。實長與357秒共同域符合要求，沒有shift、增益調整或為標註重新對齊。這支持本次同錄音對齊，不是完整stem重建混音的證明。

## 兩個工程缺口及明示修訂

1. 原GET因urllib預設header收到403，1.04秒停止，無音訊。公開同URL以瀏覽器UA及原頁Referer HEAD200，大小符合API；顧問允許只改取得header。原run與原plan保留，[v2](evaluation/independent-bass-plan-v2-2026-11-06.json)同URL／SHA1／音樂門檻／原絕對截止不變。
2. v2成功下載、轉檔、對齊，但pYIN在回傳f0前因431點transition窗大於361states而失敗（21.02秒）。顧問允許固定原431點三角prior，截合法目的state並逐row正規化；不改35.92／range／hop或依歌曲調參。[v3](evaluation/independent-bass-plan-v3-2026-11-06.json)只在隔離程序特例patch，`finally`還原，不改套件檔；合成55Hz可行性通過。v3按hash重用所有音訊及對齊，不重下載／轉檔／對齊重算。

最終v3運算19.23秒；以上是各次程式耗時，另有工程修訂時間，不當總投入。原最初1小時截止2026-11-06T10:02:24.156179+00:00未延長；每次均外層GNU timeout按剩餘秒數、啟動前OMP／OPENBLAS／MKL／NUMEXPR thread=2，manifest保存實際argv及parent launcher。總共1次403 GET、1次HEAD、2次ZIP payload GET；真實pYIN兩次attempt、只有一次成功f0，另一次合成可行性。零新分離／Chordino／模型下載／付費／上傳／產品修改。

7測試通過：穩定門檻／無邊緣補值、觸發不偷用reference、合法slash不強迫bass=root、abstention分母、對齊無效長度、合法三角prior與原API等同／超寬截域、同規格合成pYIN。最終plan SHA256 `0739a03a33ccdb5f35883e664b51c0324aef455bafc2cac2741b514d90cc9058`；runner `126a743dd3321cdf6766f3a82d952f3d16c5c839a1007e2f65111c96e9ba71d4`。

原始f0／voiced flag／voiced probability／RMS／穩定mask在 `output/evaluation/independent-bass-evidence-2026-11-06/run-v3/bass-pitch.npz`；逐cell/reference/estimate重疊及完整分類在 `stable-bass-evidence.json`。原下載／對齊在run-v2，錯誤與原runner快照保留；以原A17 diagnostic和這份NPZ呼叫 `assess` 可零音高重算指標。prob是pYIN數值，不是音高準確率。

本輪沒有可交付的和弦修正，不以更多分類／模型或放寬門檻代替產品改善。顧問已獨立通過7測試，另以357秒同波形與40ms位移核對齊pass／reject；從NPZ逐frame重算穩定性、另用mir_eval編碼音集合按cell交集累計，所有totals一致，計畫／輸入／實作／重用hash核符，零pYIN重跑。驗收產物為 `output/evaluation/independent-bass-evidence-2026-11-06/consultant-review.json`。維持原稿、線上預設及A15同入口待使用者方便時驗收；本輪不啟動新模型／分類／A16復測。
