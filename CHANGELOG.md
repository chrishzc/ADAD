# Changelog

本專案遵循 [Semantic Versioning](https://semver.org/)。

## Unreleased

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
