# #85 改善方向與實作計畫：Source Lock 依風險分級豁免與平行處理 (防禦型硬化版)

## 1. 任務背景

**原始待辦（`docs/specifications/05_task_backlog.md` #85）：**

> 本次案例：純 README／一般文件變更與可證明不重疊的施工，被全域 Task／Source Lock 一律序列化而無法平行處理；需依風險分級豁免或縮小鎖定單位，同時保留 fail-closed 與審計證據。

---

## 2. 核心防禦與硬化機制 (Defensive Engineering Directives)

本計畫包含六大資安與工程硬化原則：

1. **Mutation 操作全集合 (Mutation Operation Set)**：
   - 不僅限於 `Edit` / `Write` / `MultiEdit`，同時將 `Delete`, `Rename`, `Move`, `Copy` 納入統一閘門監控。
2. **Realpath & Repo-Root Containment 防逃逸**：
   - 解析實體路徑 `Path(target).resolve()`，檢驗 `is_relative_to(real_root)`，防止 Symlink / Junction / Path Traversal 逃逸出專案根目錄。
3. **Token-based 路徑邊界比對 (Token-based Path Matching)**：
   - 使用 `PurePosixPath(rel_path).parts` 比對路徑 Token，嚴禁純字串 `startswith("docs")`，避免 `docs_old/` 或 `docx/` 前綴誤碰撞漏洞。
4. **治理與規格文件收斂 (Governance Documents Scope)**：
   - 除 `system_map.md`/`yaml` 外，`docs/specifications/*`、`docs/architecture/*`、`AGENTS.md`、`SKILL.md` 與 `.agents/tasks/*` 劃為 Level 2 治理文件，絕對禁止豁免。
5. **Canonical SSOT 單向傳播**：
   - `adad_source` 永遠為 Canonical 源頭。更新順序：`adad_source → (.agents & adad_cli) → Hash Verification`。
6. **結構化 Diagnostic 輸出**：
   - Exit 2 阻斷時輸出包含 Rule ID、生效等級、正規化路徑、阻斷原因與下一步建議指令的結構化診斷訊息。

---

## 3. 風險分級與豁免原則 (Risk-Based Exemption Principles)

### 3.1 檔案類型風險分級矩陣

| 風險等級 | 檔案類型與目錄範例 | 存取控制策略 | 理由 |
|---|---|---|---|
| **Level 0 (無害資產)** | `README.md` (root), `docs/*`（普通說明檔）, `.txt` (非設定檔) | **完全豁免 (Exempt)** | 不影響商業邏輯或治理規範，允許平行編輯 (exit 0) |
| **Level 1 (受管程式碼)** | `*.py`（於 `system_map.yaml` 中登記之 Source）及所有未登記 `.py` | **Task Scope 限制** | 影響商業邏輯與模組契約，必須有 Task 快照授權 (exit 2) |
| **Level 2 (架構與治理)** | `system_map.*`, `.agents/*`, `AGENTS.md`, `SKILL.md`, `docs/specifications/*` | **嚴格關卡保護** | 全域架構、憲法與規格 SSOT，絕對禁止豁免 (exit 2) |

---

### 3.2 豁免判定純函式演算法

```python
from pathlib import Path, PurePosixPath
import os

EXEMPT_EXTENSIONS = {".txt", ".md"}
DOC_IMAGE_EXTENSIONS = {".png", ".jpg", ".svg", ".css"}
BLACK_LIST_FILENAMES = {"requirements.txt", "constraints.txt", "system_map.md", "agents.md", "skill.md"}
GOVERNANCE_FIRST_PARTS = {".agents", ".claude"}
GOVERNANCE_PATH_TUPLES = {("docs", "specifications"), ("docs", "architecture")}

def is_exempt_file(file_path: str, is_code_source: bool, project_root: str) -> bool:
    """
    純函式判定：指定檔案是否屬於 Level 0 無害放行資產。
    """
    if not file_path:
        return False

    real_root = Path(project_root).resolve()
    try:
        real_target = Path(file_path).resolve()
        if not real_target.is_relative_to(real_root):
            return False  # 實體路徑逃逸出 repo，絕對阻斷
        rel_path = real_target.relative_to(real_root).as_posix().lower()
    except Exception:
        return False

    parts = PurePosixPath(rel_path).parts
    filename = parts[-1] if parts else ""

    # 1. 檔名黑名單（如敏感設定或憲法檔）
    if filename in BLACK_LIST_FILENAMES or rel_path == "system_map.yaml":
        return False

    # 2. Token-based 治理目錄比對（防前綴誤碰撞）
    if parts and parts[0] in GOVERNANCE_FIRST_PARTS:
        return False
    if len(parts) >= 2 and parts[:2] in GOVERNANCE_PATH_TUPLES:
        return False

    # 3. 程式碼檔案（含未登記的 .py）一律不豁免
    if is_code_source or filename.endswith(".py"):
        return False

    # 4. 放行條款
    if filename == "readme.md" and len(parts) == 1:
        return True
    if parts and parts[0] == "docs":
        ext = os.path.splitext(filename)[1]
        if ext in EXEMPT_EXTENSIONS | DOC_IMAGE_EXTENSIONS:
            return True

    return False
```

### 3.3 #85 MVP 版本（精簡版）

#### 3.3.1 風險邊界（最小化）
- **Level 0（可放行）**：`README.md`、`docs/*`、`.txt`（非治理/受控）
- **Level 1（需 Task 授權）**：所有 `.py`（含未登記新檔）
- **Level 2（不得豁免）**：`system_map.yaml`、`system_map.md`、`docs/specifications/*`、`docs/architecture/*`、`AGENTS.md`、`SKILL.md`、`.agents/tasks/*`

#### 3.3.2 is_exempt_file 核心規則（MVP）
- 以 `project_root` realpath 為基準做 containment，先 `resolve()` 再比對，不依賴 cwd。
- `Rename / Move / Copy` 需以「來源＋目標」同時判斷，任一路徑為 Level 1/2 一律封鎖。
- 任何 `.py` 不得豁免，即使是未登記新檔。
- 先檢查 `Level 2` 再判 `Level 0`，保證 deny-first（`Level 2 > Level 1 > Level 0`）。

#### 3.3.3 門禁與稽核（最小可行）
- PreToolUse 僅做短路放行/封鎖：
  - Level 0 → `exit 0`
  - Level 1/2 → `exit 2` + 輸出 `rule_id / level / path / next_action`
- `adad_pre_commit.py` 保留為第二道防線，不得移除。
- Audit 至少記錄 `tool_name`、`operation`、`mutated_path`。

## 4. 實作步驟（分階段）

1. **階段 A：`adad_pretooluse_gate.py` 防禦硬化**
   - 整合 `MUTATION_OPERATIONS` 檢測。
   - 實現 Containment Check 與 Token-based `is_exempt_file()` 判斷。
   - 實作結構化 Diagnostic 輸出（Rule ID, Level, Path, Next Action）。
2. **階段 B：`source_lock_audit_service.py` 結構化審計**
   - 新增 `exemption_rule_id`, `exemption_reason`, `mutated_path` 審計斷言欄位。
3. **階段 C：全矩陣單元測試與雙向資產同步**
   - 新增 `test_source_lock_exemption.py` 覆蓋 4 大矩陣場景（含 Symlink 防逃逸、Prefix Collision 測試）。
   - 執行 `sync_assets.py --write` 完成 canonical 同步與驗證。

---

## 5. 驗收標準（Checklist）

- [x] `docs/task_85_improvement_plan.md` 中更新 `3.1~3.3` 的風險分級與 MVP 門禁邏輯
- [x] `is_exempt_file()` 使用 realpath + repo-root containment，支援 cwd 漂移下正確判定
- [x] 未登記或已登記 `.py` 檔皆不得豁免，未持 task 授權需 `exit 2`
- [x] `system_map.yaml`、`system_map.md`、`docs/specifications/*`、`docs/architecture/*`、`AGENTS.md`、`SKILL.md`、`.agents/tasks/*` 一律 `exit 2`
- [x] `README.md` 與 `docs/*` Level 0 檔案在非受管情境可 `exit 0`
- [x] Mutation operation 以來源/目標雙向檢核（Rename/Move/Copy 皆納入）
- [x] Exit 2 的結構化提示至少包含 `rule_id / level / path / next_action`
- [x] Audit 事件至少包含 `tool_name`、`operation`、`mutated_path`
- [x] 保留 Pre-Commit 第二防線，不允許以 PreToolUse 覆寫
- [x] 3.3 驗收項目均新增對應 `test_source_lock_exemption.py` / `test_adad_pretooluse_gate.py` 回歸
