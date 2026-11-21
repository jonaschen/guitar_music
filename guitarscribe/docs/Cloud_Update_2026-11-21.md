# 2026-11-21 個人雲端改版紀錄

目前狀態：已部署並完成驗證、備份與停機結算；正式 app f269caa 的完整遠端 CI 44845440050 三工作全通過。正式版本以 deployment.json 為準。

## 本輪功能

- 保存與完整雲端備份分開顯示；最近失敗不抹掉之前成功的時間。
- 完整和弦可先對照再沿用到等長核心片段，保留已確認目標與不同尾段，重開後仍能撤銷該次沿用。
- YouTube 下載失敗後選音檔，會正確改走上傳；雲端來源的機器人驗證仍可能拒絕新下載。
- 全曲／局部主音與調式假設、時間依據及筆記；獨立版本與跨頁保護。
- 和弦組成音／差異音比較與明確開啟的參考聲；看低頻仍只播原曲。
- 所選錄音音級能量與根音／交界改動後的和弦重聽提醒；不把能量或個人採用當正確答案。

操作見 [學習工具](Learning_Practice_2026-11-21.md)、[段落和弦與沿用](Section_Chord_Practice_2026-11-17.md)、[保存與備份](Cloud_Maintenance_2026-11-21.md)。

## 發布範圍與資料保護

程式提交 `f269caa1d7926901530308d1e5f3640f5bc57a44`，私人包 `releases/2026-11-21-v5/app.tar.gz`，SHA256 `8fb26454f2f11838fc4541913f507b6dd20602d2cbb0a624b4600d7d0274a16a`，1,998,477 bytes。功能基底為 9053368；其後只有測試工具與手機勾選框樣式修正。使用 `prepare_release.py --app-only` 從 Git HEAD 清潔建置，沒有讀取或打包本機 work/runtime/public 私人音訊。

入口與 VM 資源不變；這次只替換 app/site。Cloud Run digest 與原始 runtime 不變，KEEP_SONGS 保留。上一版保留在 `/srv/guitarscribe/releases/2026-11-21-v5/previous`（v4；更早 v3 另保留在 v4/previous）；現用程式另記 `app-release-manifest.json`，原 `release-manifest.json` 是初始安裝與遷移紀錄，不能據此判定最新 app 或拿初始資料覆蓋 work。

使用正常入口的時數帳本喚醒，約 48 秒就緒。08:24:40 台北的更新前快照已完成，manifest `backups/manifests/20261121T002440Z-d85224e4815d468d974a0ec832965f52.json`，generation `1795220825989807`，manifest SHA256 `9843a6d18764d27ddbe3e5d9ceb5978c9cd0062b0e0068998610e3dfc8d33410`。150 檔，僅新增一個 37 bytes blob；這是去重結果，不是歌曲遺失。

## 驗證

- 上一工程提交 0e21d0f：遠端 CI 44841127946 三工作成功，前端349通過／7既有條件skip、WebKit20＋學習2通過。
- 最新程式本機：89項相關後端、4項WebKit真API及build通過；10分鐘反覆操作通過，詳見 [持續操作證據](evaluation/practice-soak-2026-11-21.json)。
- 功能版遠端 CI 44842766057：三工作全通過；1461後端／3既有skip、351前端／7既有條件skip、WebKit20＋學習4。最終提交 f269caa 的 [CI 44845440050](https://github.com/jonaschen/guitar_music/actions/runs/44845440050) 三工作亦全通過：1462後端／3既有skip、351前端／7既有條件skip、WebKit20＋4、雲端98；本機build／WebKit4及正式站390／1440已通過。
- 雲端兩次純程式更新前後、專用fixture清理後及最後正式查核，6個既有DB邏輯內容一致；277個已安裝檔案SHA吻合發布包。25首原有歌曲保留。
- 三首正式歌曲結構／根音／和弦唯讀及原音訊Range 206；專用測試歌和弦／學習筆記保存、重開、409衝突、能量計算、沿用／撤銷通過。測試歌已清理，只刪有所有權標記的資料，原有DB及原稿不變。
- 新版完整備份狀態API確認complete，150檔；08:43:03快照、08:44:37完成，manifest `backups/manifests/20261121T004303Z-1b5037f47b834f6f868d30aefb5e40cd.json`，SHA256 `8a5971d4a600a42bbbabe8f0e6d3c07eddc4664e16c08fb3bdc1659861977d9a`。timer已啟用、startup-script已更新，重開仍用新版狀態紀錄。08:50台北已確認VM休息、可喚醒；使用帳本結算7725秒，剩136275秒／31天，本次維護增加1666秒（約27分46秒）。這是運行時數而非帳單。

獨立歌曲結構準確率、實體 iPhone 和數小時穩定性、實際月帳單仍未知。這些不以工程測試通過替代。

詳細數據見 [驗證摘要](evaluation/cloud-update-2026-11-21.json)。正式畫面截圖含私人歌曲進度，僅保留本機 output/cloud-control，不加入公開Git。
