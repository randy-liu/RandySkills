# 回歸測試答案卷：12 支的官方商品圖與量測結果

`validate_grips.py` 用這份檔案考自己：逐支下載官方圖 → 重量一次 → 與下表比對，
**誤差須 < 1.0cm，12 支全過才算通過**。

> 🟡 「握把 cm」欄是本 skill 的量測值，不是原廠公佈規格。
> 這些數字同時也是 `rod-curve-generator/references/measured_grip_lengths.md` 的內容來源。

---

## 答案卷

| 型號 | 種類 | 全長cm | 仕舞cm | 先径mm | 元径mm | 圖型 | **握把cm** | 可利用竿長cm | 比例尺 |
|---|---|---|---|---|---|---|---|---|---|
| `702UL+FS-ST23` | S | 213 | 110 | 0.7 | 7.4 | 拆節平放 | **27.3** | 185.7 | 9.09 px/cm |
| `722LRS-21` | S | 218 | 113 | 1.4 | 11.9 | 拆節平放 | **30.1** | 187.9 | 8.85 px/cm |
| `6102MLFS-19` | S | 208 | 108 | 1.5 | 9.9 | 拆節平放 | **30.2** | 177.8 | 9.26 px/cm |
| `722LRSB-24` | B | 218 | 113 | 1.3 | 9.4 | 拆節平放 | **34.4** | 183.6 | 35.31 px/cm |
| `722MLRSS-24` | S | 218 | 113 | 1.6 | 9.4 | 拆節平放 | **34.5** | 183.5 | 35.31 px/cm |
| `772ML+FS-22` | S | 231 | 119 | 1.6 | 10.4 | 拆節平放 | **36.1** | 194.9 | 8.40 px/cm |
| `722ML+FB-ST20` | B | 218 | 113 | 1.2 | 10.9 | 整支組裝 | **37.1** | 180.9 | 4.59 px/cm |
| `722MRB-20` | B | 218 | 113 | 1.7 | 10.9 | 整支組裝 | **37.3** | 180.7 | 4.59 px/cm |
| `752HRB-21` | B | 226 | 117 | 2.0 | 12.9 | 拆節平放 | **39.7** | 186.3 | 8.55 px/cm |
| `722MHRB-19` | B | 218 | 113 | 1.8 | 11.8 | 拆節平放 | **40.8** | 177.2 | 8.85 px/cm |
| `802MHRB-21` | B | 244 | 126 | 1.8 | 12.9 | 拆節平放 | **41.3** | 202.7 | 7.94 px/cm |
| `7112MRB-25` | B | 241 | 124 | 1.8 | 10.9 | 拆節平放 | **43.2** | 197.8 | 32.18 px/cm |

⚠️ **兩支「整支組裝」圖的精度較差**（4.59 px/cm，約 ±0.5cm）：官方給的不是拆節平放圖，
比例尺只能用全長，而且竿尖與元節在同一條帶上，先径與接管重疊兩項交叉檢查無法進行。

---

## 官方商品圖網址

🔴 **這些網址會失效。** DAIWA 用 Azure CDN，網址帶 `?rev=` 版本碼，官方換圖就會 404。
失效時的正確處置是**回產品頁重新取得網址並更新本檔**，
**不是**放寬測試門檻、也不是把該支從答案卷裡刪掉。

產品頁：
- スピニング <https://www.daiwa.com/jp/product/3suacjj>
- ベイトキャスティング <https://www.daiwa.com/jp/product/8fqqixq>

| 型號 | 圖片網址 |
|---|---|
| `6102MLFS-19` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags/__icsFiles/afieldfile/2018/12/25/HL_6102MLFS-19.jpg?rev=c84cbd660a1e442b8e810cd8e6ba6b56> |
| `702UL+FS-ST23` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags/__icsFiles/afieldfile/2022/11/05/HL_702ULplusFS-ST23.jpg?rev=9ddd3a2b4a734688b673dafaab614bac> |
| `7112MRB-25` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/tsuika_8fqqixq/HEARTLAND_7112MRB-25_4550133434167.jpg?rev=33b2868aa09f42c6a21c840209473eb3> |
| `722LRS-21` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags/__icsFiles/afieldfile/2020/11/18/Heartland_722LRS-21.jpg?rev=8ac130c8e6904adba35acd8b8ffe41dd> |
| `722LRSB-24` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/tsuika/HEARTLAND_722LRSB-24_05806514.jpg?rev=95e8dc4f7b42437d9ee535589cb29da2> |
| `722MHRB-19` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/__icsFiles/afieldfile/2018/12/25/HL_722MHRB-19.jpg?rev=a5c992d0b98949509f0441605cb9d1da> |
| `722ML+FB-ST20` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/__icsFiles/afieldfile/2020/01/09/HL_722ML-FB-20_4.jpg?rev=ba7e2bbb2e8946679e4ec0579b0179c4> |
| `722MLRSS-24` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags/tsuika/HEARTLAND_722MLRSS-24_05806515.jpg?rev=c0c18fbcc8e044b68185d53a03b4fb8c> |
| `722MRB-20` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/__icsFiles/afieldfile/2020/01/09/HL-722MRB-20_4.jpg?rev=a586c3cfc7b7412d9c5fd2143abe1e91> |
| `752HRB-21` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/__icsFiles/afieldfile/2020/11/18/Heartland_752HRB-21.jpg?rev=429594b83c124ea8916d633566d45ebf> |
| `772ML+FS-22` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags/__icsFiles/afieldfile/2021/11/18/HL_772MLplusFS-22.jpg?rev=b7f2f456864446d896edd5cba4ba752f> |
| `802MHRB-21` | <https://390386bd-1bf0-4900-aa10-cac1793c9a23-afd-dqdkdpcqgcc6hahm.z01.azurefd.net/-/media/Project/globeride/daiwa_com_jp/resources/fishing/item/rod/bass_rd/heartland_ags_b/__icsFiles/afieldfile/2020/11/18/Heartland_802MHRB-21.jpg?rev=410e6f55329c437a80a819a02bd88c69> |

---

## 為什麼要有這份答案卷

這個演算法騙過我一次：第一版沒有「連續」條件，`722MLRSS-24` 被最大導環的單點厚度尖峰騙成
**96.5cm**（真值 34.5cm）。數字大到離譜，但當下沒有任何東西會擋它。

→ 所以偵測邏輯只要動到，就必須跑 `validate_grips.py`。**12 支全過才算沒壞。**
