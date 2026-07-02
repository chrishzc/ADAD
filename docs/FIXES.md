# 修改紀錄：分層架構 / include 機制修復

本次修改針對 `system_map.md` 主地圖透過 `<!-- include -->` 連結子地圖、以及
`Domain → Subsystem → Module` 三層架構解析的部分，修復以下問題。
所有修改集中在 `.agents/skills/adad-workflow/scripts/adad_core.py`。

## 1. include 路徑正則表達式的連字號 bug

**問題**：原本的正則 `[^\s-]+(?:\.md|\.yaml|\.txt)?` 排除了連字號 `-`，
導致任何含連字號的子地圖路徑（例如 `docs/user-service.md`、
`docs/adad-workflow/sub.md`）完全無法被比對到，該 include 會被靜默忽略，
子地圖內容完全不會被編譯進去，且不會有任何錯誤或警告。

**修法**：改為非貪婪比對到副檔名結尾：
```python
INCLUDE_PATTERN = re.compile(r'<!--\s*include:?\s*(\S+?\.(?:md|yaml|txt))\s*-->')
```

## 2. Domain / Subsystem 標題會汙染前一個模組的欄位

**問題**：`parse_markdown` 只認得 `##### Module:` 標題，遇到 `### Domain:`
`#### Subsystem:` 時完全略過、也不重置 `current_module`。若照文件建議寫法
在 Subsystem 標題後接一行 `- Description: ...`，這行會被誤判成「上一個已
解析完的模組」的欄位，靜默覆蓋掉它（已用單元測試重現並確認修復前後行為）。

**修法**：
- 新增 `domain_regex` / `subsystem_regex`，比對到時強制重置
  `current_module = None`、`current_section = None`
- Domain / Subsystem 名稱與描述寫入 `data["domains"]`
- 每個模組新增 `domain`、`subsystem` 兩個欄位，**分層架構第一次真正成為
  IR（`system_map.yaml`）裡可查詢的結構化資料**，而不只是 Markdown 排版

## 3. 模組名稱重複時靜默覆蓋 → 改為硬性報錯 + 來源反查

**問題**：模組名稱是全域扁平命名空間，兩個子地圖若不小心用了同名模組，
後解析的會直接覆蓋前一個，無任何警告。多檔案協作（原本拆子地圖的目的）
反而放大了這個風險。

**修法**：
- `resolve_includes` 展開時插入 `<!-- __ADAD_SOURCE_FILE__: 路徑 -->` 標記
- `parse_markdown` 追蹤目前內容來自哪個實體檔案，寫入模組的 `map_file` 欄位
  （解決「這個模組寫在哪個子地圖檔案」查無資料的問題）
- 偵測到同名模組時直接拋出 `ValueError` 中斷編譯，並列出兩個定義各自的
  來源檔案，而不是靜默覆蓋

此規則同時會擋下「鑽石型 include」（同一份子地圖被兩個不同父層各 include
一次，導致內容在合併文件中出現兩次）——這是純文字 include 機制無法避免的
結構性重複，過去會靜默造成資料損毀，現在會直接報錯逼你修正地圖結構
（例如改成只從單一父層 include 一次）。

## 4. include 循環偵測與快取分離

**問題**：原本 `visited.copy()` 每個分支各自複製一份，只能在單一路徑上
偵測真循環，且沒有任何快取，重複的 include 會被重複遞迴解析。

**修法**：拆成 `ancestors`（目前 DFS 路徑，偵測真循環用）與
`resolved_cache`（全域快取，避免重複遞迴解析同一檔案）兩個概念。

---

## 4. 孤兒子地圖偵測

**問題**：`system_map.md` 可以透過 `<!-- include -->` 拆成多個子地圖檔案，但如果
某個子目錄下新增了一個 `.md` 檔案卻忘記在父地圖裡加上 include，這份內容會
完全不會被編譯進架構，也不會有任何提示。

**修法**：`adad_core.py` 新增 `find_orphan_maps()`，只掃描「已經被 include
機制引用到的目錄」，找出同目錄下沒被引用到的 `.md` 檔案。`compile_map.py`
編譯完會自動呼叫並印出警告（不阻斷編譯），結果也會寫進 JSON 輸出的
`orphan_maps` 欄位。刻意不做全專案掃描，避免對 `docs/adr`、`docs/patterns`
這類非子地圖目錄產生假警報。

## 5. 跨 Domain 依賴邊界檢查

**問題**：即使 `domain`/`subsystem` 已經是 `system_map.yaml` 裡可查詢的結構化
資料（見第 2 項修復），過去完全沒有工具去檢查「模組依賴是否跨越了不該跨越
的 Domain 邊界」，分層架構停留在「看得到」但「沒人管」的狀態。

**修法**：
- `system_map.md` 的 Domain 底下新增可選欄位
  `Allowed Dependencies: [Domain_X, Domain_Y]`，宣告這個 Domain 允許依賴
  哪些其他 Domain；不宣告則預設只能依賴同 Domain 內的模組。
- `ADADCore.check_domain_boundary()`：掃描所有模組依賴，找出「依賴對象的
  Domain 跟自己不同，且沒有被宣告允許」的違規，回傳 `{passed, violations}`。
- 新增 CLI `check_domain_boundary.py`，比照 `check_normalization.py` 的用法。
- 接進 `adad_pre_commit.py`：只要本次 commit 觸碰到任一模組的原始碼，就會
  對整份架構圖跑一次邊界檢查，違規直接擋下 commit（比照 Invariants 的做法，
  而不是只停留在「文件建議」層級）。

沒有 `domain` 資訊的模組（例如尚未走三層架構、或舊專案還沒補標記）會被跳過，
不會被誤判為違規，向下相容既有專案。


## 驗證方式

以下測試皆已於本次修改後手動執行並通過：
- 含連字號路徑的 include 能被正確比對
- Domain/Subsystem 標題後的欄位不再誤植到前一個模組
- 重複模組名稱（含鑽石型 include 造成的重複）會被正確擋下並指出來源
- 專案自帶的 `python adad_core.py --test` 全數通過
- 對本專案實際的 `system_map.md` 執行 `compile_map.py` 編譯成功，
  且產出的 `system_map.yaml` 內含正確的 `domain` / `subsystem` / `map_file` 欄位
