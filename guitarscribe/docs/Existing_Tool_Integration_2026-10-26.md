# Codex：現成工具整合與專家驗證方案

查核日期：2026-10-26。使用者同意嘗試現成工具整合；不解讀成同意購買、申請第三方帳號或將音訊上傳雲端。目標仍可保留「音訊→樂譜」，只是評估由外部工具負責辨識；並未擅自縮成只有手動輸入MIDI的產品。

## 現況盤點

本專案已有MIDI／MusicXML匯出、播放、編輯，以及離線外部MIDI時間解析；目前API／前端沒有通用MIDI／MusicXML匯入入口。離線診斷解析不等於完成產品匯入整合。原分析與G不得被不明外部聲部自動覆寫。

## 首選：先驗證Klangio人聲轉譜，通過後接API

[Sing2Notes官方頁](https://sing2notes.klang.io/)明列人聲輸入及MIDI／MusicXML匯出，含量化與未量化MIDI。[音樂API文件](https://api-docs.klang.io/)亦明列vocal及MIDI／MusicXML輸出。這些是功能資訊，不是本案品質證據；尚未實測此服務。

[官方API方案頁](https://klang.io/api/)當次列Basic每月US$0、50 requests、每次音訊最多15秒、每分鐘1 request，需填申請表。Startup列每月US$99，不建議在尚未驗證品質時購買。API價格與網頁版方案不同，也不是 klang.ai 語音轉文字服務。

[網頁免費Demo限制](https://klang.io/help/difference-demo-full/)／[條款](https://klang.io/terms/)列20秒、僅PDF匯出；不能以此承諾免費取得網頁版MIDI。API的實際存取核發、可用輸出及計費應以核發帳號／合約確認，不能把網站列有Basic當作已取得權限。

## 備選與其界線

- [Melodyne Audio-to-MIDI](https://helpcenter.celemony.com/M5/doc/melodyneStudio5/en/M5tour_ExportMIDI_standalone?env=standAlone)：可匯出音符MIDI，適合作為另一個工具或由音樂工作者製作參考。官方[技術／試用頁](https://www.celemony.com/en/melodyne/editions-and-technical-matters?checkLang=1)列Windows/macOS及30天完整試用。本工作區為Linux，未核實可用的伺服器API，不承諾本機直接自動整合，也不為此先折騰Wine或新平台。
- [Tony](https://www.sonicvisualiser.org/tony/)是可輔助人工校正單旋律／人聲標註的免費工具，能匯出CSV；[官方程式庫](https://github.com/sonic-visualiser/tony)說明使用pYIN。因此它適合建立參考標註，不當作已證明更好的新辨識引擎。
- AnthemScore與ROSVOT已在本案驗收失敗，不因「現成工具」名義重新整合。

## 已備妥的具體測試包

`output/evaluation/existing-tool-integration-2026-10-26/comparison-inputs.zip`，僅在本機：

| 檔案 | 長度 | 來源 |
|---|---:|---|
| third-20-35.wav | 15.000秒 | 第三來源原曲20–35秒，固定先前視窗的前15秒 |
| third-40-55.wav | 15.000秒 | 第三來源原曲40–55秒，固定先前視窗的前15秒 |
| saved-G.wav | 14.466秒 | 先前較自然的固定片段 |

皆為既有人聲stem，未加入全曲、私人資料庫或帳號資訊。manifest含hash、原曲位置與檔案大小。截短是配合Basic限制，不是挑表現好的段落；舊20秒驗收不能直接當作這些15秒視窗的結果。當次程式誤用系統Python缺soundfile，改用既有runtime後成功，沒有修改環境套件。

待取得API權限及明確雲端上傳授權後，才送這三個檔案；不代購、不中途擴大測試。金鑰應存本機環境變數或秘密儲存，不貼在聊天、程式碼或git。

## 最小整合順序與停止條件

1. 先取得單次固定輸出的原始MIDI，使用現有離線解析／同音色播放器比對G，保留未量化輸出與原始時間原點。若免費API不能提供所需結果，先報實際限制，不自動轉付費。
2. 實測音高、音長、重奏、休止及修正時間。三段都需是可用草稿、不能破壞較好片段；若仍需重建大量音符，停止此服務整合。不以頁面漂亮或品牌作採用依據。
3. 只有品質支持後，新增通用MIDI匯入：解析tempo map、按軌／channel列出旋律候選，使用者確認所選聲部，保留來源秒數、原始MIDI與撤回，核對匯入→播放→匯出事件一致。第一階段不把多軌MIDI擅自壓成一條旋律。
4. 再接外部API任務提交／輪詢／輸出下載、額度與失敗恢復；一次只接一個提供者。MusicXML可另做譜面互通，不能在未核對節奏／聲部時替代原始MIDI事件。

本輪已完成查核、輸入準備與可審閱申請草稿，尚未送出申請、上傳、取得服務結果或完成產品adapter。

## 免費API申請說明草稿（未送出）

Name／Company／Email須由使用者提供真實資訊；不得由AI假造。

> We are evaluating a local guitar transcription and score-editing prototype. Our current vocal note extraction fragments expressive singing and sometimes produces incorrect note sequences. We would like to evaluate the Basic testing tier using three authorized isolated-vocal WAV clips, each no longer than 15 seconds. We need vocal note transcription with original-time/unquantized MIDI export, plus documentation of tempo maps, model/version identifiers, data retention, and deletion options. Please confirm whether the Basic tier supports these outputs, which API endpoints and credentials are required, and whether submission, polling, and export retrieval count separately toward the request allowance. We do not authorize a paid subscription or automatic upgrade. If the evaluation succeeds, we will discuss a production integration separately.

## 官方API流程補充（助手唯讀查核）

[帳號與API key](https://api-docs.klang.io/docs/getting-started/account-management)；[轉譜提交](https://api-docs.klang.io/docs/jobs/transcription-requests)：`POST https://api.klang.io/transcription?model=vocal`，header `kl-api-key`，multipart `file`及`outputs=midi`。之後按[工作流程](https://api-docs.klang.io/docs/getting-started/basic-job-workflow)輪詢 `GET /job/{job_id}/status`；完成後 `GET /job/{job_id}/midi`。官方[MIDI說明](https://api-docs.klang.io/docs/file-formats/midi)區分原始時間MIDI與 `/midi_quant`。文件稱結果保留14天；多輸出可能增加配額成本，需核對實際帳號。以上尚未實際呼叫，不能標示adapter已驗證。

## 使用者補充：參考譜路線沿用既有經驗

使用者提供《情非得已》圖片，並指出《小手拉大手》也曾用使用者參考譜。已查證既有紀錄；接受網路譜僅供參考的限制。後續可搜尋參考譜，與外部MIDI和錄音做差異核對，不能強制依譜改音或用同一譜自我評分。見 [參考譜工作流程](Reference_Score_Workflow_2026-10-26.md)。這個補充不構成雲端上傳授權。
