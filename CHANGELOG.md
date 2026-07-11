# Changelog

本專案遵循 [Semantic Versioning](https://semver.org/)。

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
