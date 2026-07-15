## 5. 代辦事項總表（合併版，執行清單）

以下代辦目前編號至 #60，是根據第 1 節的能力缺口、加上工程稽核（README/測試/CI）盤點出來的具體
待辦事項。**這節才是「現在要動手做哪一項」的答案**，第 1~4 節是「做完之後系統該
長什麼樣子」的規格。

### A. 工程衛生（文件與實作落差 / Dogfooding / 測試 CI）

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|1|~~README 的「CLI 工具說明」表格漏了 3 支已存在的腳本（`generate_task.py`、`adad_task.py`、`check_domain_boundary.py`）~~ **✅ 已完成**|文件|已完成|
|2|~~README 的 Phase 1~4 + Checkpoint Payload 章節完全沒提到「Task 快照機制」，跟實際程式碼的職責分離設計對不上~~ **✅ 已完成**|文件|已完成|
|3|~~**環境宣告缺失（`environment` 欄位）**：schema 沒定義、`compile_map.py` 沒解析，100% 靠 SKILL.md 文字指示 Agent 自己記得~~ **✅ 已完成**（`environment` 已成為頂層必填 schema 欄位，`parse_markdown`／`compile_map.py` 會編譯並保存；支援 `planned`／`validated`／`deployed`／`not_required`，根目錄與新專案模板均已同步。）|ADAD schema|已完成|
|4|~~`system_map.md` 只登記 4 個舊模組，實際 codebase 已有 12+ 支腳本完全沒登記進架構地圖~~ **✅ 已完成**（canonical workflow 的 18 支 Python 腳本均已登記，另含 `sync_adad_assets`；根地圖 18 個 Module、roadmap 19 個 Module 均可編譯，Source binding 驗證通過。）|Dogfooding|已完成|
|5|~~沒有正式測試套件（無 `/tests`、無 pytest），CLI 腳本缺少自動化覆蓋~~ **✅ 已完成**（已建立 pytest 套件，涵蓋 workflow CLI、Task lifecycle、schema、跨平台 I/O、hook 與 Verification fixture；`pyproject.toml` 提供 `dev` extra 與 pytest 設定。2026-07-13 使用全域 `C:\Python314\python.exe -m pytest -q` 實際執行，135 項全數通過。）|測試|已完成|
|6|~~沒有 CI/CD（無 `.github/workflows`），README 建議的「CI 跑 `adad_pre_commit.py`」自己沒做到~~ **✅ 已完成**（GitHub Actions 會在 push／pull request 執行資產同步檢查、ADAD guardrail、架構編譯與完整 pytest。）|CI|已完成|
|7|~~沒有 `CHANGELOG.md`，Improvements 都寫在 README 尾巴長條文字，無版本對照~~ **✅ 已完成**（已建立 `CHANGELOG.md`，維護版本化與 Unreleased 改善紀錄。）|文件|已完成|

### B. Schema / 架構層級缺口（Architecture Proposal / 模組定義）

|#|代辦事項|歸屬|優先度|對應第 1 節能力|
|---|---|---|---|---|
|8|~~沒有 `Source`（實作檔案路徑綁定），pre-commit/PreToolUse gate 拿 staged 檔案反查模組的唯一依據~~ **✅ 已完成**（`Source` 欄位與反查機制 `build_source_to_module_map` / `build_file_to_registered_functions` 原已存在，但「一個 Source 只對應一個模組」過去只在 SKILL.md 裡用文字要求，從未被機械驗證。本次新增 `ADADCore.check_source_binding()` 與獨立 CLI `check_source_binding.py`，檢查三種歧義：①兩模組填完全相同的 Source；②同一檔案被整檔登記與逐函式登記混用；③同一函式被多個模組登記。已接進 `compile_map.py`（歧義時阻斷編譯，比照 Schema 違規處理）與 `adad_pre_commit.py`（commit 前用 staged 版本的 system_map.yaml 再檢查一次，避免繞過編譯流程手動改壞）。`source` 留空仍視為「尚未填寫」的軟提示（`unbound` 清單），不阻斷。SKILL.md 對應段落與 README CLI 工具表已同步更新；新增 `tests/test_check_source_binding.py`（6 個案例）並與既有 74 項測試一起於本機以 `pytest` 實際執行全數通過。）|ADAD|**最高**——沒填這欄，後面所有機械強制全部失效|1-2 讀取邊界的前提|
|9|~~沒有 `Preferred Pattern`（首選設計模式），跟 `tradeoffs` 混在一起沒拆開~~ **✅ 已完成**（schema 已有獨立 `preferred_pattern`，context 組裝會輸出對應模式摘要。）|ADAD|已完成|—|
|10|~~沒有 `Complexity` + `Algorithm` 步驟大綱，複雜邏輯只靠 I/O 契約~~ **✅ 已完成**（`complexity`／`algorithm` 已是 schema 契約；high 且缺 Algorithm 會阻斷編譯。）|ADAD|已完成|1-7 Architecture Proposal 生成|
|11|~~`nfr` 太模糊，沒有機械可檢查的 `Invariants`~~ **✅ 已完成（第一階段）**（支援 `deny_imports` 與 AST `deny_calls`；違規會阻擋 Task submit／pre-commit。）|ADAD 定義 + Kernel 執行 AST 掃描|已完成（第一階段）|1-3 驗證掛勾|
|12|~~完全沒有 `Verification`（可執行測試案例）~~ **✅ 已完成（第一階段）**（支援 input/expect 與 `expect_exception`；失敗會阻擋 Task submit。）|ADAD 定義 + Kernel 執行|已完成（第一階段）|1-3 驗證掛勾|
|13|~~模組是扁平清單，沒有 `Domain/Subsystem` 分層 + `Allowed Dependencies`~~ **✅ 已完成**（schema 與 domain boundary gate 已支援巢狀分層及跨 Domain 白名單。）|ADAD|已完成|—|
|14|~~沒有 per-module 生命週期狀態~~ **✅ 已完成**（每個模組有獨立 `state`，approve/reject 依 `node_name` 局部推進。）|ADAD 定義狀態語意 + Kernel 執行狀態轉移|已完成|1-6 Permission Check|
|15|~~沒有區分「架構文件」跟「Task 快照」~~ **✅ 已完成**（架構地圖保持長期事實；`.agents/tasks/<node>.task.json` 是單次凍結快照。Task Schema v2 驗證 schema version、source hash、狀態、目標契約與相依介面。）|ADAD 定義快照內容 + Kernel 提供凍結/hash 過期/門禁機制|已完成|1-1 Task 規格供給|
|16|~~沒有 `Observability Contract`~~ **✅ 已完成（宣告與上下文層）**（每個 Module 具 `not_required` 或 required + metric/log/trace/alert signals；schema、編譯與 Task Readiness 會機械驗證。）|ADAD 宣告 + Kernel 執行埋點|已完成（埋點執行層依產品實作）|—|
|17|~~沒有失敗清理 / Rollback 契約~~ **✅ 已完成（安全保留策略）**（Task 固定採 `preserve_diff`，不自動 reset／刪檔，並記錄施工前與駁回時 hash。）|ADAD 定義策略 + Kernel 執行|已完成|—|
|18|~~沒有併發修改衝突機制~~ **✅ 已完成**（Task Schema v2 新增 `source_lock`；原子檔案鎖阻擋同一 Source 的平行 Task，跨 assigned/in_progress/submitted 保留，CP-2 核准後釋放，駁回則留給原 Task 修正。）|ADAD 宣告邊界 + Kernel 執行鎖定|已完成|1-5 Checkpoint 核准的下游|

### C. Task 規格層級缺口（單一 Task 該長什麼樣）

#### Specification

| #   | 代辦事項                                                                                                           | 歸屬                              | 優先度             |
| --- | -------------------------------------------------------------------------------------------------------------- | ------------------------------- | --------------- |
| 19  | ~~`description` 升級成結構化 Semantic Contract，不是自然語言~~ **✅ 已完成**（已實作 `validate_semantic_contract`，支援將自然語言無痛升級為 summary 搭配 goals，亦支援對結構化 JSON 做 schema 驗證。） | ADAD                            | 已完成             |
| 20  | ~~新增 `Non-goal` 欄位~~ **✅ 已完成**（已實作 `validate_non_goals`，強制 non_goals 必須顯式提供，且空陣列 `[]` 代表已明確確認，不可為 None。） | ADAD                            | 已完成             |
| 21  | ~~Preconditions/Postconditions——**不建議獨立開欄位**，應擴充現有 `Verification: case` 語法來表達，否則跟 Verification 分類重疊打架~~ **✅ 已完成**（已實作 `validate_verification_conditions`，強制 case 必須有 `input` 表達 Pre-條件，並有 `expect` 或 `expect_exception` 表達 Post-條件，重用既有欄位不重複造輪子。） | ADAD 定義 + Kernel 驗證             | 已完成 |
| 22  | ~~新增 `Assumptions` 欄位~~ **✅ 已完成**（已實作 `validate_assumptions`，強制 assumptions 必須顯式提供以利快照與審核，且空陣列為合法，不可為 None。） | ADAD                            | 已完成             |
| 23  | ~~把 `validate_schema.py` 這套已存在的通用校驗引擎，延伸套用到 per-task 的 Input/Output JSON Schema（目前只套用在 `system_map.schema.json`）~~ **✅ 已完成**（已實作 `validate_task_input_schema`，沿用 `validate_schema` 支援的語法關鍵字子集，並對 properties 和 items 等進行遞迴嚴密驗證。） | ADAD 內容 + Kernel 引擎（已存在，屬小工程延伸） | 已完成         |

#### Behavior

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|24|~~`Invariants` 加強~~ **✅ 已完成**（支援 `require_calls`、`deny_env_read`、`deny_sys_exit` 與 `deny_bare_except`。）|ADAD 內容 + Kernel（AST 掃描）|已完成|
|25|`Side Effect Contract` 宣告|ADAD 宣告 + Kernel（很難，需 sandbox/mock 動態追蹤）|低——工程量大，先宣告不強求驗證|
|26|~~`Determinism` / `Idempotency` 宣告，實作成「執行兩次比對輸出」的 case type~~ **✅ 已完成**（已加入 schema，並於編譯時支援解析）|ADAD 宣告 + Kernel（相對便宜）|已完成|
|27|`State Change Contract` 宣告|ADAD 宣告 + Kernel（很難，同 Side Effect）|低|
|28|`Purity`——**不建議獨立開欄位**，改成幫 `Preferred Pattern: pure_function` 加一個機器可讀 `purity: true` flag|ADAD|低——避免同一件事兩處定義|
|29|`Resource / Timeout Contract`（執行期記憶體/時間上限，跟 Context Budget 是兩件事）|ADAD 宣告 + Kernel 執行 sandbox 限制|中|
|30|`Concurrency / Thread-safety Contract`|ADAD 宣告 + Kernel（盡力而為）|低——機械驗證困難，只能宣告優先|

#### Exception

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|31|~~`Exception Type/Condition` 欄位~~ **✅ 已完成**|ADAD|已完成|
|32|~~`Exception Verification`——併入現有 `case` 語法，加 `expect_exception: "ValueError"` 類型~~ **✅ 已完成**（驗證器會比對實際例外類別名稱。）|ADAD 定義 + Kernel 執行|已完成|

#### Dependency

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|33|Dependency 的 Exception/Side Effect/Preconditions/Postconditions 宣告|ADAD|中——⚠️ 要求越完整，Task 快照要遞迴帶入的內容越大，會撞到 Context Budget，兩者需同步規劃|
|34|Per-module `Dependency Version`|ADAD，但需三思|低——schema 結構性大改，先確認真的需要再排|
|35|~~Retry Budget（每個 Task 該重試幾次才升級 CP-2），目前寫死在 Kernel 的固定值該搬到 ADAD 可宣告欄位~~ **✅ 已完成**（已加入 schema，並於編譯時支援解析）|ADAD 逐 Task 宣告 + Kernel 執行計數器|已完成|

#### Verification

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|36|~~Boundary/Invalid Input/Exception Cases——不新增欄位，改由 Task Readiness 要求 case 類型~~ **✅ 已完成（併入 #40）**|Task Readiness|已完成|
|37|**🟡 第一階段完成**：已實作並核准 `resolve_verification_fixture_inputs`，支援專案內 UTF-8 JSON fixture 注入、跨平台絕對／drive／UNC／逃逸路徑阻擋、key 衝突與原物件不變性。尚待：① `system_map.schema.json` 接受 `case.fixtures`；② `verify_implementation` 呼叫 resolver，完成真正的 Kernel 執行注入。|ADAD 宣告 + Kernel 執行注入|中——進行中，不可標記全項完成|
|38|Coverage Gate（`verify_implementation.py` 升級成真的跑 coverage 工具）|Kernel|**P2，先不做**——複雜度躍升一個量級|
|39|Property-based / Golden Test|Kernel，可選|低優先|
|55|**Command／Integration Verification 強化測試**：補齊 unknown placeholder、POSIX absolute／Windows drive／UNC、fixture source/target 穿越、timeout、UTF-8 decode failure、stdout/stderr contains、目錄 fixture 複製與清理，以及 integration fail-fast。|Kernel pytest|中——核心流程已可用，這些是邊界與失敗路徑補強|
|56|**相對專案路徑的 cwd 診斷**：當 `command` 在預設 `workspace` 執行、argv 或 inline script 使用相對專案檔案路徑而未指定 `cwd: "project"` 時，輸出可行動的診斷／lint，明確提示隔離暫存目錄與 `cwd: "project"` 選項；補齊對應 pytest。|ADAD verification runner + Kernel pytest|中——避免既有 cwd 功能因設定遺漏造成難以辨識的檔案不存在錯誤|
|57|**Source Markdown 反引號正規化**：`parse_markdown()` 必須移除 `Source` 欄位成對的外層 Markdown 反引號，避免 `file.py::function` 的函式名稱殘留反引號並使 `verify_implementation` 找不到實作；補齊帶／不帶反引號、整檔／逐函式 Source 的編譯與驗證 pytest。|ADAD parser + Kernel pytest|中——合法 Markdown 表示法會使通過的業務邊界測試被 ADAD 誤擋|
|58|**Command 輸出容錯解碼**：verification runner 必須以 bytes 擷取 stdout/stderr，再以 UTF-8 優先、系統偏好編碼 fallback 與 `errors="replace"` 解碼；不得因外部工具輸出非 UTF-8 位元組而覆蓋 command 的 exit code 或中斷 Task submit。timeout 的 bytes stdout/stderr 亦須採同一邏輯，並補齊 UTF-8、非 UTF-8 stdout/stderr、輸出契約與 timeout pytest。|ADAD verification runner + Kernel pytest|高——Windows／pytest 非 UTF-8 輸出會使合法驗證誤判失敗並阻斷提交|
|59|**Release Gate project_root 分離**：pre-commit 解析 staged YAML 時可使用暫存檔，但 Verification 的 `project_root`、`cwd: project`、`project_python`、fixture 與 placeholder 必須固定指向正式 repository root；補齊 staged map 位於 Temp 時仍可執行專案 pytest 的整合測試及 bounded 診斷。|ADAD Core + Enforcement Gate pytest|P0——目前 Temp YAML 會把 Verification 導向錯誤目錄，造成 gate 假失敗|
|60|**Approved Commit Hash Gate**：Edit Gate 與 Commit Gate 分離；submit/approve 保存實作 SHA-256，pre-commit 僅允許 `approved` 且 staged hash 與核准 hash 相同的內容。`assigned` 不得 commit，`approved` 不得 edit；舊 Task 缺少核准 hash 時 fail-closed。|ADAD Task lifecycle + Enforcement Gate pytest|P0——目前 approved 反而不能 commit，SOP 被迫重新核發未核准 Task|

#### Task Readiness

| #   | 代辦事項                                                                                                                                                                                                                                                                          | 歸屬                                   | 優先度                                  |
| --- | ----------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ------------------------------------ | ------------------------------------ |
| 40  | ~~Required Field Gate / Completeness Check / Ready Score~~ **✅ 已完成（最小可執行版）**（`check_task_readiness()` 在核發前檢查必要欄位、型別、Observability 與高複雜度 Algorithm，回傳結構化 blockers；量化 Ready Score 待後續。） | ADAD 定義 schema + Kernel 執行 | 已完成（Ready Score 為後續增強） |
| 41  | ~~`[MISSING ALGORITHM]` 從 warning 升級成強制 compile fail~~ **✅ 已完成**（high complexity 缺 Algorithm 時輸出結構化錯誤並 exit 1。） | Kernel | 已完成 |
| 42  | ~~審批留痕 / Audit Trail~~ **✅ 已完成**（approve/reject 要求 `--reviewer`；原子寫入 CP-2 checkpoint，Task history 回鏈 audit，失敗時回復狀態。） | ADAD 定義必要欄位 + Kernel 執行寫入 | 已完成 |
| 49  | ~~**Task Complexity Budget / Decomposition Gate~~ **✅ 已完成（保守核發版）**：`generate_task` 現實際呼叫 complexity policy：`low` 可直接核發；`medium` 必須同時具備 Algorithm、非空 Input/Output 邊界與 Verification；`high` 一律阻擋並要求拆為 low/medium 子任務。完整 pytest 91 項通過。人工 high-capability override 尚未開放，避免尚無結構化審批契約時繞過拆分門檻。 | ADAD Task Readiness + Kernel 核發 gate | 已完成（override 為後續增強） |

#### Context

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|43|~~`Required Context` 宣告~~ **✅ 已完成**（已加入 schema 並支援編譯解析）|ADAD 宣告 + Kernel 組裝|已完成|
|44|~~`Forbidden Context` 宣告，現有 Task 快照白名單機制通用化成可配置黑名單~~ **✅ 已完成**（已加入 schema 並支援編譯解析）|ADAD 宣告 + Kernel 執行隔離|已完成|
|45|`Context Budget`（token 預算/裁剪策略）|**純 Kernel**，跟 ADAD 領域無關|追蹤——需跟 Kernel 的 LLM Provider Router 連動，非 ADAD 代辦|
|46|~~`Context Priority`（超預算時先砍什麼）~~ **✅ 已完成**（已加入 schema 並支援編譯解析）|ADAD 定義優先序 + Kernel 執行裁剪|已完成|
|47|`Context Source` 宣告|ADAD 宣告 + Kernel 擷取/快取|低|

### D. 開發環境一致性缺口

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|48|~~**單一專案虛擬環境**：`adad init` 只能建立並使用專案根目錄的 `.venv`；不得再建立 `venv`，且 Git pre-commit hook 必須固定使用該專案的 `.venv`，不可綁定執行 CLI 當下的外部/開發環境。若偵測到舊版 `venv/`，應提供明確遷移提示，避免自動刪除使用者環境。~~ **✅ 已完成**（已實作 `_project_venv_python`、`_write_project_pre_commit_hook`、`_ensure_project_virtual_environment` 與 `_remove_project_virtual_environment` 等原子操作；`init`、`upgrade` 與 `clean` 等生命週期函式已完成 refactor 並委派更新，支援 `project_root` 及舊 venv 保護提示，核心 90 項 pytest 單元測試均已通過。）|ADAD CLI + 文件 + 測試|已完成|

### E. 生成資產完整性缺口

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|50|~~**同步資產必須排除 Python 快取**：`sync_assets` 不得將 `__pycache__/` 或 `*.pyc` 視為 canonical 資產、複製到 `.agents`／`resources`，或讓它們造成 `--check` 假失敗。~~ **✅ 已完成**（同步器會排除並清除快取；合併後 canonical／生成資產一致，完整 pytest 90 項通過。）|ADAD 資產同步器 + 測試|已完成|

### F. Kernel 掛勾實作缺口

|#|代辦事項|歸屬|優先度|對應第 1 節能力|
|---|---|---|---|---|
|51|~~`report_blocked` MCP server 尚未實作~~ **✅ 已完成**（實作 `report_blocked_mcp.py` 與 fallback 文字 parser，並擴充核心狀態支援 blocked，附結構化理由。）|ADAD 定義格式 + Kernel 提供掛勾點|已完成|1-4 卡住結構化回報|
|52|~~Agent Execution Environment Isolation Template~~ **✅ 已完成**（實作 `prepare_isolation.py` 與 `adad_task isolate`，採用白名單與 artifact 沙盒隔離工作區。）|ADAD CLI + Kernel 執行隔離|已完成|1-6 隔離執行環境|
|53|~~Schema gap reporting~~ **✅ 已完成**（實作 `detect_schema_gaps.py`，掃描自然語言中是否偷偷夾帶 `env`、`timeout`、`retry` 等應放入結構化欄位的約束，並於 `submit` 時輸出警告供 reviewer 檢視。）|ADAD Schema Gap Report|已完成|1-5 Schema 品質把關|

### G. Task 核發品質缺口

|#|代辦事項|歸屬|優先度|
|---|---|---|---|
|54|**Task 快照保真度**：`generate_task`／`read_context_by_node` 必須把 Module 的 inline `Decisions`（以及其他施工必要欄位）完整帶入 `.agents/tasks/<node>.task.json`，並新增 schema／pytest 防止欄位靜默遺失。2026-07-13 #37 首次核發因 pytest 要求只存在於 `Decisions`、Task 端未收到而遭駁回，已證明這是可重現的核發品質缺口。|ADAD Task snapshot + Kernel|**高——會讓 coding 模型在資訊不完整下仍通過提交 Gate**|

### 2026-07-13 更新紀錄

- 完成跨平台 UTF-8 subprocess、strict read、atomic write 與 `.gitattributes` 換行政策。
- `check_normalization` 改用 UTF-8 `--file`／stdin，移除易受 Windows shell quoting 破壞的 positional JSON。
- 專案 `.venv` 已成為 pre-commit 與 Claude PreToolUse hook 的唯一 Python；hook command 支援 Windows／POSIX 安全引用與舊 `python3` 冪等升級。
- #37 第一階段 resolver 已核准，修正後 pytest 覆蓋 null、drive-relative、UNC、invalid JSON 與輸入不變性；全套 135 項 pytest 通過。
- 登記 #54 Task 快照遺漏 `Decisions`，避免把本次駁回誤歸因於 coding 模型能力。

### 2026-07-14 更新紀錄

- Verification 新增 `command` 與 `integration_case`，支援 argv、隔離 fixture、預期 exit code、timeout、stdout/stderr 契約與多步 fail-fast。
- migration 驗證可依序執行 `--check`、`--apply`、資料快照 checker 與第二次 apply，確認阻擋條件、資料保持及 idempotent。
- 四個 runner helper 已納入 `adad_core.known_symbols`；重新編譯確認 `untracked_symbols: []`。
- 登記 #55，追蹤 command／integration runner 尚待補齊的邊界與失敗路徑 pytest。
- 登記 #56，追蹤相對專案路徑的 command 在預設隔離 workspace 執行時，缺少 `cwd: "project"` 的可行動診斷。
- 登記 #57，追蹤 `Source` 外層 Markdown 反引號未正規化而污染函式綁定的問題。
- 登記 #58，追蹤 command runner 對非 UTF-8 stdout/stderr 的容錯解碼，避免誤擋 Task submit。

#### Development Dogfood Reviewer 紀錄

|Backlog|核發|退回／上限|修改|Coding 嘗試|目前處置|Fingerprint|
|---|---:|---:|---:|---:|---|---|
|#58|2|2／3|2|1|v8 Task 已提交；13 focused tests 通過，UTF-8 Gate 與診斷契約完成|`task58-adad_core-missing-task-gate-and-acceptance`|
|#54|1|1／3|1|2|v7 Task 已提交；Schema v3/v2 相容驗證完成|`task-54.snapshot-fidelity.unbound-schema-and-core-conflict`|
|#57|2|2／3|2|1|v8 Task 已提交；整檔 Source 修訂後 Invariants 與 4 cases 通過|`task-57.source-backtick-unbound-parser-contract`|
|#59/#60|1|1／3|1|0|合併規格被 Readiness Gate 退回；已拆為四個 sequential medium Task|`task-59-60.combined-high-readiness-atomicity`|
|#59 Hook|2|1／3|1|2|R1 明定解析 diagnostic JSON 後比較 Windows Path；舊 Task 停止，新 Task 重發|`task-59-hook.raw-json-windows-path-escaping`|

Reviewer 對主代理的核發改善建議：

- Task 必須明列唯一節點、canonical Source、必要同步產物、驗收案例、Non-goals、`task_id`、`source_hash` 與合法狀態。
- `adad_core` 內可獨立施工的函式應拆成可核發的原子節點，避免 wrapper 節點與真正修改來源不一致。
- 同一 Source 已有未整合 diff 時不得重複核發；先完成、退回或隔離既有工作。
- Coding Agent 每個 Task 最多兩次「修改＋驗證」；Task 格式或上下文缺陷應在第一次修改前退回。
- Reviewer 退回後由主代理立即路由 Planner 修訂；每個 Task 最多退回 3 次，第 3 次仍不合格才提交人工 Checkpoint。

R1 修訂摘要：

- **#58**：唯一施工範圍為 `ADADCore._decode_verification_output` 與 `_run_verification_command`；不得改 argv、cwd、fixture 或 placeholder。驗收涵蓋 UTF-8、非 UTF-8 stdout/stderr、replacement、exit code 與 timeout bytes。
- **#54-A**：新增 `task_snapshot_schema`，先讓 Task Schema v3 與 v2 並存；v3 強制保存原始 `decisions`、`preferred_pattern`、施工約束、執行契約與 Task 語意，summary 不得取代原值。本 Task 不修改 generator。
- **#57**：新增 `parse_markdown` 原子契約；僅移除完整包覆 Source 值的一對單反引號，未成對／多重反引號不處理；驗收為帶／不帶反引號 × 整檔／逐函式四組。
- 三項 R1 當時已達 Task 內容可審查程度，但涉及新增節點、非法現態或整檔／逐函式 Source 拆分，須人工 Checkpoint 後才能核發 Coding Task。
- 人工核准後三項均已核發並轉為 `submitted`；整合驗證共 32 tests 通過，`sync_assets --check` 無差異。
- #58 submit 的 schema-gap warning 指向自然語言 `timeout` 尚未結構化；已去重歸入既有 #29 Resource／Timeout Contract，不新增重複 backlog 項目。Fingerprint：`task58.timeout-natural-language-without-structured-contract`。

### 2026-07-12 分支差異與合併紀錄

- **development 保留為基準**：canonical `adad_source/`、`sync_assets` 生成流程、Windows-safe normalization 輸入、Task Complexity Policy 第一階段、完整 roadmap、#48 單一 `.venv` 與 #50 資產快取排除。
- **由 main 補入**：#3、#6、#11、#12、#15、#16、#17、#18、#32、#40、#41、#42，以及 Task Schema v2、Observability、`deny_calls`、`expect_exception`、`preserve_diff`、原子 Source Lock、CP-2 audit、README／CHANGELOG 與對應測試。
- **編號衝突處理**：development 的 #48／#49／#50 不變；main 的 `report_blocked` 缺口由 #48 改為 #51。
- **生成資產原則**：main 的核心改善已移植到 development 的 `adad_source/`，再由同步器生成 `.agents/` 與 `adad_cli/resources/`，未繞過 development 的唯一來源設計。


### 代辦事項優先順序
- #59、#60、#58、#54、#37（剩餘 case fixture schema + verifier 接線）、#55、#56、#57、#33、#29；低優先再評估 #28、#47。

`#25/#27/#30/#34/#38/#39` 這幾項工程量大或收益不確定，建議明確標記 P2，避免搶資源。
