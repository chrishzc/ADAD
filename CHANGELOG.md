# Changelog

本專案遵循 [Semantic Versioning](https://semver.org/)。

## Unreleased

### Added

- Atomic per-source Task locks prevent parallel Tasks from modifying the same file; locks are released only after CP-2 approval.
- Module-level Observability Contract，支援 `metric`、`log`、`trace`、`alert` signals，並隨 Task 快照提供給 coding 端。
- `deny_calls` AST invariant 與 `expect_exception` Verification case，擴充危險呼叫與例外路徑的機械驗收。
- 獨立 `task_schema.json` 與 Task Snapshot 完整性驗證，明確切開長期架構文件與單次施工快照。
- `preserve_diff` rollback contract：拒絕或驗證失敗時保留工作區差異，並記錄施工前後的實作檔 hash。
- Task Complexity Policy 已接入核發 Gate：medium 需完整施工規格，high 一律要求拆分。

### Changed

- 以 development 的 `adad_source/` canonical asset 架構為合併基準，main 的 Task Schema v2、Observability、rollback、Source Lock 與驗證強化皆先移植至 canonical source，再同步生成 `.agents/` 與 `adad_cli/resources/`。
- 保留 development 的 Windows-safe normalization、Task Complexity Policy、資產快取排除與 roadmap；規格編號衝突中的 `report_blocked` 由 #48 改列 #51。

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
