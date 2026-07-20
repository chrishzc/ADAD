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

## 6. 2026-07-19：Verification runner、被動資產漂移與 Windows 中斷事件

### 現象

- `adad_core` 的 Task submit 在 Windows 顯示 `KeyboardInterrupt`，或以摘要回傳
  `Verification 檢查未通過`。
- structured receipt 顯示 pytest 子行程其實已輸出 `70 passed`，但父 runner 在
  `process.communicate()` 收集輸出時收到中斷，因此依 fail-closed 規則拒絕將 Task
  轉為 `submitted`。
- `.agents/skills/.../adad_core.py` 與 canonical
  `adad_source/agents/.../adad_core.py` 的 hash 不同；`sync_assets --check` 也列出
  `adad_core.py`、`adad_task.py` 與 packaged resource 的差異。使用者從 `.agents`
  執行 CLI，因而可能取得和 canonical 不同的 runner 行為。

### 成因

1. 先前直接改動被動 `.agents` 副本，沒有先回寫 canonical source 再由
   `sync_assets` 生成，破壞「只有 `adad_source` 可主動修改」的單一真實來源規則。
2. Verification workspace 的舊規則把所有 `cwd=project` command 一律改為隔離
   workspace；這和 non-pytest command 應保留 project-root `{workspace}` 的相容性
   要求衝突，且 project-root pytest basetemp 又容易遭 Windows 鎖定。
3. 受控／內嵌 Windows console 會向父 Python 發出中斷；這個訊號可能在 pytest
   已輸出成功摘要後才到達。父 runner 沒有可確認的子行程成功 exit code 時，不能
   將該次驗證視為成功。

### 修正與驗證

- 採用 R3 折衷規則：只有 pytest command（即使 `cwd=project`）建立 project-root
  內、每次唯一的 `adad_verify_work_*` workspace；非 pytest 的 `cwd=project`
  command 仍以 project root 作 `{workspace}`。
- canonical `adad_core.py` 補上上述規則及受中斷時的 structured fail-closed receipt；
  `tests/test_adad_task.py` 增加 pytest workspace 隔離回歸。
- canonical 驗證結果為 `70 passed`；Task 以不附著 console 的 `pythonw.exe` runner
  成功提交並完成 CP-2 核准。不得以手動改寫 Task status 或略過 verification 取代此流程。

### 預防與後續

- 修改 workflow asset 時只改 `adad_source`，再以 `python -m adad_cli.sync_assets --check`
  驗證；不得直接修 `.agents` 或 `adad_cli/resources`。
- `adad_task.py` 的被動資產漂移屬另一個原子節點：先將其 index CLI 變更補回
  canonical source、完成其 Task 驗證後，才能執行全域資產同步；不可為了修正
  `adad_core` 單一 Task 而覆寫其他節點的未同步變更。
- 遇到外部中斷時，只有已確認子行程 exit code 為成功才可視為成功；否則保留
  structured evidence 並拒絕提交。受 console control event 影響的 Windows 環境，
  可使用 `pythonw.exe` 啟動已驗證的提交程序以避免附著 console。

### 6.1 操作 Runbook：pytest 顯示通過，但 Verification 被中斷

此案例的辨識條件是同一筆 `command_results` 同時符合：

- `stdout` 已含 `N passed in ...`；
- `interrupted` 為 `true`；
- `returncode` 為 `null`，並帶有 `command 執行被使用者中斷`。

這表示 pytest 摘要可作為診斷證據，**不能**取代預期 exit code；Verification 必須維持
fail-closed。它不是 assertion failure，也不能僅憑 submit 的泛化錯誤訊息歸因為
`.agents/tasks` ACL 或 snapshot 寫入問題。先在專案根目錄直接取得 structured receipt：

```powershell
.\.venv\Scripts\python.exe .\.agents\skills\adad-workflow\scripts\verify_implementation.py adad_core
```

若 receipt 符合上述中斷特徵，且 pytest 的測試摘要已符合 Task 的驗證要求，使用下列
不附著 console 的方式重新執行 submit。保留 stdout、stderr 與 exit code，作為提交證據：

```powershell
$script = Join-Path $PWD ".agents\skills\adad-workflow\scripts\adad_task.py"
$out = Join-Path $env:TEMP "adad-submit-adad_core.out"
$err = Join-Path $env:TEMP "adad-submit-adad_core.err"

$p = Start-Process `
  -FilePath ".\.venv\Scripts\pythonw.exe" `
  -ArgumentList @($script, "submit", "adad_core") `
  -RedirectStandardOutput $out `
  -RedirectStandardError $err `
  -Wait -PassThru -WindowStyle Hidden

"exit_code=$($p.ExitCode)"
Get-Content -Raw $out
Get-Content -Raw $err
```

只有 `exit_code=0` 且 stdout 的 JSON 為 `success: true`、`status: submitted` 時，才可
進入人工 CP-2。不要手動改寫 Task status、略過 verification，或以移除 ACL deny 作為此
症狀的預設修復；若 receipt 沒有中斷特徵，再另行檢查 `.agents/tasks` 及
`.agents/tasks/.task_index.lock` 的 create/write/rename/delete 可寫性。


## 驗證方式

以下測試皆已於本次修改後手動執行並通過：
- 含連字號路徑的 include 能被正確比對
- Domain/Subsystem 標題後的欄位不再誤植到前一個模組
- 重複模組名稱（含鑽石型 include 造成的重複）會被正確擋下並指出來源
- 專案自帶的 `python adad_core.py --test` 全數通過
- 對本專案實際的 `system_map.md` 執行 `compile_map.py` 編譯成功，
  且產出的 `system_map.yaml` 內含正確的 `domain` / `subsystem` / `map_file` 欄位
