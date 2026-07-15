# Changelog

本專案遵循 [Semantic Versioning](https://semver.org/)。

## Unreleased

## 1.6.0 — 2026-07-15

### Added

- 新增 `sub_maps` schema 與遞迴 loader，支援全域重名、循環、路徑逃逸及 physical owner 一致性門禁。
- 缺失 ADR／Pattern 改以固定格式 `context_warnings` 回報，不再污染 Task 目標內容。

### Changed

- 編譯器依 shard owner 分流寫回 root／child YAML，保留 shard metadata，避免 child 節點膨脹進 root。
- Verification absence contract 明確區分欄位不存在與 `null`；Reviewer 與發布 SOP 補強 UTF-8、CI 子程序環境及退回診斷規範。
- `sub_maps` 發布驗收須等待 GitHub Actions 成功後才安裝本機工具，並以外部專案乾淨副本驗證 upgrade、`FinanceImport`／root context、root／child counts 與重複 compile 不膨脹。

### Fixed

- owner-aware save 將模組寫回原 shard，未知 owner、ghost scope 或 owner mismatch 一律 fail-fast。

## 1.5.0 — 2026-07-14

### Added

- 新增 development 子代理角色規範：Orchestrator、Planner、Implementer、Verifier 與 Reviewer；Reviewer 追蹤 Task 核發、退回、修改及 Coding 嘗試次數。
- 新增 Task Schema v3 保真契約並保留 v2 相容；v3 強制保存架構決策、施工約束、執行契約與 context 契約。
- 新增 `normalize_markdown_source` 原子 helper，支援 Source 外層單反引號正規化；接入 parser 留待後續 Task。

### Changed

- Coding 自我修正上限調整為 2 次；Reviewer 退回上限為 3 次，退回後必須記錄原因並立即送回 Planner 修訂。
- Verification command 改以 bytes 擷取輸出並嚴格驗證 UTF-8；非法編碼會保留 exit code 與替代文字供診斷，但不得通過輸出契約。

## 1.4.2 — 2026-07-14

### Fixed

- Verification command 支援明確 `cwd` 與跨平台 `{project_python}`；需要專案檔案的 CLI 可選擇專案根目錄執行，migration 仍可使用隔離 workspace fixtures。
- 將 `adad_cli/core.py` 的完整 top-level 函式集合納入架構 Source 綁定，恢復 RULE-04 對 init、upgrade、hook 與發行流程的追蹤。

## 1.4.1 — 2026-07-14

### Fixed

- `adad upgrade` 現會備份並同步根目錄 `system_map.schema.json` 與 `task_schema.json`，避免 Parser 已支援新 Verification 類型、正式 Schema 卻仍停留舊版。

## 1.4.0 — 2026-07-14

### Added

- **多型 Verification runner**：新增 `command` 與 `integration_case`，以 argv 與 `shell=False` 在隔離暫存工作區執行 CLI／migration 驗證。
- 支援 `{python}`、`{source}`、`{project}`、`{workspace}` placeholder、fixture 複製、預期 exit code、timeout 與 stdout/stderr contains 契約。
- 新增 SQLite migration 整合測試，驗證 check 阻擋、apply、資料快照保持、來源 fixture 隔離與 idempotent；完整 pytest 140 項通過。

- **跨平台 I/O 與版本庫邊界**：
  - `run_utf8_subprocess` 統一以 argv、UTF-8 strict 與明確 cwd 執行子程序，避免 Windows CP950 與 shell quoting 差異。
  - `read_utf8_text_strict`／`write_utf8_text_atomic` 提供嚴格 UTF-8 讀取及同目錄暫存檔原子替換。
  - `.gitattributes` 明確規範跨平台文字格式使用 LF，Windows batch/cmd 使用 CRLF，二進位檔不做文字轉換。
- **Verification fixture 第一階段（#37）**：新增 `resolve_verification_fixture_inputs`，可將專案根目錄內的 UTF-8 JSON fixture 安全注入 case input；拒絕路徑逃逸、POSIX absolute、Windows drive/UNC、重複或衝突 key，且不修改原始 case。完整接入 `system_map.schema.json` 與 `verify_implementation` 仍列為後續工作。
- 新增跨平台與 fixture 測試；2026-07-13 以 `C:\Python314\python.exe -m pytest -q` 實跑完整套件，135 項全數通過。

### Changed

- `adad init`／`upgrade`／`remove` 統一管理專案根目錄的 `.venv`；舊 `venv/` 只提示人工遷移，不自動搬移或刪除。
- pre-commit hook 與 Claude PreToolUse hook 固定使用目標專案 `.venv` Python，不再綁定安裝 ADAD 時的外部 Python 或硬編碼 `python3`。
- Claude hook command 依 Windows／POSIX 規則安全引用含空白路徑；升級時會冪等更新舊命令、保留其他 hooks，無效 JSON 則保留原檔並回報略過。
- `check_normalization.py` 停用容易被 shell quoting 破壞的 positional JSON，只接受 UTF-8 `--file` 或 stdin。

### Fixed

- 修正 Windows、macOS、Linux 間的子程序解碼、文字換行、路徑引用與 hook Python 選擇差異。
- 修正 fixture 來源在非 Windows 主機可能漏判 `C:relative`、drive-qualified 或 UNC 路徑的風險。
- 將 Task 快照未攜帶架構 `Decisions` 的核發品質缺口登記為 backlog #54，避免必要測試要求只存在於規劃端。
- `Verification` 不再把 migration CLI 誤當成可 import 的同名 Python 函式。

## 1.3.0 — 2026-07-12

### Added

- **Task 規格驗證系列 (Task Contract Schema)**：
  - `validate_semantic_contract`：支援 description 自然語言無痛升級，或結構化 JSON 目標/條件 schema 驗證。
  - `validate_non_goals`：限制 Non-goal 必須顯式定義且不能為 None（空陣列代表已明確確認）。
  - `validate_verification_conditions`：以 `input` 表達 Pre-conditions，並以 `expect` 或 `expect_exception` 表達 Post-conditions，重用既有 case 欄位。
  - `validate_assumptions`：強制 Assumptions 必須顯式定義（支援空陣列相容），限 string list。
  - `validate_task_input_schema` 與 `validate_task_output_schema`：延伸 `validate_schema` 的通用校驗子集，實施遞迴 JSON Schema 格式驗證，並拒絕未支援的關鍵字。
- 專屬單元測試套件 `tests/test_task_contract_schema.py`，105 個測試全數 100% 通過。
- Atomic per-source Task locks，防止平行 Tasks 覆蓋同一檔案。
- Module-level Observability Contract，支援 metric、log、trace、alert 等 signals 的快照核發。
- `deny_calls` AST invariant 與 `expect_exception` Verification case 支援。
- 獨立 `task_schema.json` 與 `preserve_diff` rollback 策略。
- Task Complexity Policy 接入核發 Gate，限制高複雜度 Module 核發。

### Changed

- **說明文件對齊與重構 (README Alignment)**：
  - 補齊 `generate_task.py`、`adad_task.py` 與 `check_domain_boundary.py` 到 CLI 工具說明。
  - 重構 Phase 2 工作流與 CP-2 Payload 指引，使其與 Task 快照與核准生命週期完全一致。
  - 將 README 尾端冗長的優化改善歷史轉移至 CHANGELOG 維護。
- 合併 canonical asset 架構，保留 Windows-safe normalization，並解決 Windows CP950 編碼解碼警告與 hook 靜默放行問題。

## 1.2.0 — 2026-07-11

### Added

- `environment` 頂層架構宣告與 schema 驗證；純 CLI 專案可明確標示 `not_required`。
- Task Readiness gate、`check_source_binding.py` 與 CP-2 checkpoint audit trail。
- GitHub Actions CI：執行 ADAD guardrail、架構編譯與 pytest。
- `check_source_binding` 的架構地圖登記與對應測試。

### Changed

- `Complexity: high` 缺少 `Algorithm` 時，編譯由警告升級為失敗。
- approve/reject 必須由互動終端機的人類提供 `--reviewer`，並留下可追溯的 YAML 紀錄。
- Windows 主控台輸出改為 UTF-8 安全處理，避免警告訊息造成編譯器崩潰。
