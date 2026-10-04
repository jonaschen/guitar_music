# MusicXML 局部拍點修正

## 問題與改動

舊版按偵測小節分段，卻用固定 BPM 把每段秒數換成 divisions。小節長短不同時，4/4 小節會不等於四拍；手動分界校正後尤其明顯。

新版依小節起訖與内部有效拍點建立分段線性座標。完整小節總拍長依拍號決定（4/4 為 1920、6/8 為 1440 divisions），音符與休止用「終點位置減起點位置」避免逐段取整累積誤差。跨小節延音保留 tie，前置弱起仍使用原有秒數長度並標 implicit。無內部拍點時以小節起訖線性插值；缺少後續小節的尾部仍使用既有 BPM 推估，不能當成已校準尾奏。

每個區間寫入局部 sound tempo 與 offset，使支援這些欄位的讀譜器能重建原時間。依據 [W3C sound 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/sound/) 與 [offset 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/offset/)。不修改 SongScore 秒數、來源分析或人工修訂。

## 驗證與限制

測試涵蓋不等拍距、4/4、6/8、局部 tempo 反算秒數、跨校正分界延音、密集音符取整、小節總長與原資料不變性。MusicXML／API／MIDI 回歸以來源掛載容器執行，52 項通過。

追加和弦位置修正：每個和弦事件依同一局部拍點座標輸出 offset，不再按名稱去重，因此 C → G → C 的返回事件保留。輸出根音升降、常見大小／七／減／增／掛留／六／九／power 品質及斜線低音；kind 的顯示文字只保留品質後綴，避免重複根音。不支援的品質、N／N.C. 等保留為原文字 direction，不捏造大三和弦；文字不代表完整和聲播放語意。依據 [W3C harmony 結構](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/harmony/) 與 [kind 定義](https://www.w3.org/2021/06/musicxml40/musicxml-reference/elements/kind/)。新增 12 項位置／語意案例後，MusicXML／API／MIDI 共 64 項通過。

尚未完成：第三方讀譜器實際渲染／播放验收、完整 schema 驗證、細緻的附點／連音記譜、完整延伸和弦與無和弦播放語意。和弦目前在原事件起點標記，不在每個延續小節重印。不要把這次修正解讀成整份 MusicXML 品質通過。

本次後端程式已提交但未重啟正式容器，避免中斷現有工作；需於適當部署窗口重建 backend 才會反映到網頁下載。小節分界 UI 的上一轮測試不受影響，也不需要再比較旋律候選。
