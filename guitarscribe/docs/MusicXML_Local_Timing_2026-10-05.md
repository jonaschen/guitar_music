# MusicXML 局部拍點修正

## 問題與改動

舊版按偵測小節分段，卻用固定 BPM 把每段秒數換成 divisions。小節長短不同時，4/4 小節會不等於四拍；手動分界校正後尤其明顯。

新版依小節起訖與内部有效拍點建立分段線性座標。完整小節總拍長依拍號決定（4/4 為 1920、6/8 為 1440 divisions），音符與休止用「終點位置減起點位置」避免逐段取整累積誤差。跨小節延音保留 tie，前置弱起仍使用原有秒數長度並標 implicit。無內部拍點時以小節起訖線性插值；缺少後續小節的尾部仍使用既有 BPM 推估，不能當成已校準尾奏。

每個區間寫入局部 sound tempo 與 offset，使支援這些欄位的讀譜器能重建原時間。依據 [W3C sound 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/) 與 [offset 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/offset/)。不修改 SongScore 秒數、來源分析或人工修訂。

## 驗證與限制

測試涵蓋不等拍距、4/4、6/8、局部 tempo 反算秒數、跨校正分界延音、密集音符取整、小節總長與原資料不變性。MusicXML／API／MIDI 回歸以來源掛載容器執行，52 項通過。

追加和弦位置修正：每個和弦事件依同一局部拍點座標輸出 offset，不再按名稱去重，因此 C → G → C 的返回事件保留。輸出根音升降、常見大小／七／減／增／掛留／六／九／power 品質及斜線低音；kind 的顯示文字只保留品質後綴，避免重複根音。不支援的品質、N／N.C. 等保留為原文字 direction，不捏造大三和弦；文字不代表完整和聲播放語意。依據 [W3C harmony 結構](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/harmony/) 與 [kind 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/kind/)。新增 12 項位置／語意案例後，MusicXML／API／MIDI 共 64 項通過。

官方 schema 檢查發現既有 attributes 子節點順序錯誤：clef 必須在 staff-details 前；已修正並增加順序回歸檢查。新增 `backend/scripts/validate_musicxml_schema.py`，固定官方 MusicXML 3.1 三份 XSD 的 SHA-256、禁止網路解析與外部 entities，驗證空譜、TAB 跨小節 tie、弱起、和弦／文字 fallback、6/8 局部格線五組案例，並以非法文件確認驗證器會拒絕錯誤。

重跑方式：從 [W3C MusicXML v3.1 schema](https://github.com/w3c/musicxml/tree/v3.1/schema) 下載 `musicxml.xsd`、`xml.xsd`、`xlink.xsd` 到隔離資料夾（保留原始 bytes）。於拋棄式容器安裝 `lxml==6.0.2`，來源掛載 backend，唯讀掛載 schema 資料夾為 `/schema`，執行 `PYTHONPATH=. python scripts/validate_musicxml_schema.py /schema`。不將驗證依賴加入正式 backend、不讀寫使用者資料。

實際驗證結果：五組案例均通過，非法控制文件被拒絕；同容器 MusicXML／API／MIDI 64 項回歸通過。

## alphaTab 1.8.4 實際匯入檢查

直接使用專案安裝的 ScoreLoader 讀取後端當次匯出，而非手寫 XML fixture。發現 .75 秒（120 BPM）的音符雖保留 1440 alphaTab ticks，但 type=quarter、dots=0，顯示語意錯誤。已補常見單／雙附點的 type 與 dot，不更改 duration；不規則長度仍保留精確 divisions，不偷偷吸附到規整音長。

三組讀譜器檢查（附點四分、雙附點四分、附點八分）通過：type／dots、精確 ticks、TAB 弦格與全小節總長符合預期。後端 MusicXML／API／MIDI 現為 67 項通過。可在 guitarscribe 目錄重跑：

```bash
set -o pipefail
docker compose run --rm -T -v "$PWD/backend:/app" backend sh -c 'PYTHONPATH=. python scripts/musicxml_reader_fixtures.py' | node frontend/scripts/validate-musicxml-reader.mjs
```

另有未解決相容性證據：同小節 C（0 秒）→ G（1 秒）的 XML 有兩個 harmony／offset，但 alphaTab 匯入只有第一個和弦。需後續處理匯入相容的事件排列，不可將目前 MusicXML 預覽當作完整和弦位置真相；工作譜與 GuitarScribe 自有播放不受此讀譜器問題影響。本輪驗證是 reader model，不是瀏覽器視覺 screenshot 驗收。

### 和弦讀入後續修正

上述 C→G 問題已修正：將 harmony 排在它實際所屬的音樂位置，offset 相對當前 cursor 為零，不再一次堆在小節前面。換和弦落在休止內時分割休止；落在旋律持續音內時，僅在 MusicXML 中分割並加 sound／notation tie，工作譜不拆音符、不新增旋律攻擊。邊界取整到小節末的標記仍保留，不靜默丟失。

alphaTab 五組驗證現涵蓋三種附點、休止內換和弦、持續音下換和弦，確認 C@0／G@1920 ticks、完整小節時值與 tie origin/destination；後端相關 68 項通過。這解決了具體重現案例，不代表任意密集和弦、讀譜器畫面或全部播放語意皆已驗收。

尚未完成：第三方讀譜器實際渲染／播放验收、所有可能輸入的 schema 覆蓋、細緻的附點／連音記譜、完整延伸和弦與無和弦播放語意。和弦目前在原事件起點標記，不在每個延續小節重印。不要把這次修正解讀成整份 MusicXML 品質通過。

本次後端程式已提交但未重啟正式容器，避免中斷現有工作；需於適當部署窗口重建 backend 才會反映到網頁下載。小節分界 UI 的上一轮測試不受影響，也不需要再比較旋律候選。
