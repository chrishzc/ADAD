# -*- coding: utf-8 -*-
"""
ADAD PreToolUse Gate — 在 Agent 真正呼叫 Edit/Write 之前擋下違規修改。

用途：
  Git pre-commit hook 只在「commit 那一刻」才檢查 RULE-02（狀態門禁），
  這代表 agent 完全可能先花大量 token 把整支檔案的程式碼寫完，
  才在 commit 時被擋下來，回頭又要重新生成一次——等於白花一輪 token。

  這支腳本改掛在 Claude Code 的 PreToolUse hook 上，在 Edit / Write / MultiEdit
  工具呼叫「執行前」就攔截：只要目標檔案對應的 Task 快照狀態不允許編輯，
  直接 exit 2 擋下這次工具呼叫，Agent 連一行程式碼都還沒寫出來就會收到明確的
  阻擋原因，不會浪費任何 token 在會被丟棄的程式碼上。

  ponytail (Task 機制重構)：原本這裡直接查模組的 state（RULE-02），現在改成
  呼叫 adad_core.ADADCore.check_task_gate()，判斷依據是 .agents/tasks/<node>.task.json
  這份 Task 快照的 status，而不是 system_map.yaml 裡的模組狀態。這個改動是為了
  讓「有沒有先取得核准才動手」這件事變成單純檢查檔案系統就能判斷的事實，
  不需要解析 Claude Code 特有的 transcript 格式——同一份 check_task_gate()
  邏輯之後也能被 Codex、或自建的 agent harness 直接 import 重用，不綁定在
  單一平台的 hook API 上。

  這是硬規則，不是 agent 自律：即使 agent 在推理時想跳過 read_context.py
  直接動手改，工具呼叫本身會被 Claude Code 攔截，agent 無法繞過
  （--dangerously-skip-permissions 也一樣擋得住，因為 PreToolUse hook
  的 deny 判定發生在權限系統之前）。

安裝方式：
  1. 把這支檔案放進專案的 .agents/skills/adad-workflow/scripts/ 底下
     （與 adad_pre_commit.py 同一目錄，會 import 同目錄的 adad_core.py）。
  2. 在專案的 .claude/settings.json 加入：

     {
       "hooks": {
         "PreToolUse": [
           {
             "matcher": "Edit|Write|MultiEdit",
             "hooks": [
               {
                 "type": "command",
                 "command": "python3 .agents/skills/adad-workflow/scripts/adad_pretooluse_gate.py"
               }
             ]
           }
         ]
       }
     }

  3. 重新開一個 Claude Code session 讓設定生效（/hooks 可以檢視目前已註冊的 hook）。

行為：
  - exit 0            → 放行，不印任何東西（避免干擾）
  - exit 2 + stderr    → 阻擋這次工具呼叫，stderr 內容會原封不動回饋給 Agent，
                         讓它知道具體該做什麼（例如先跑 read_context.py、
                         或改送 Schema Update Request）
  - 任何無法判斷的情況（非 ADAD 專案、找不到 system_map.yaml、解析失敗等）
    一律放行，不阻斷正常開發——這支腳本只負責「阻止已知會違規的修改」，
    不負責也不應該取代 pre-commit hook 或 CI 的完整檢查。
"""
import sys
import os
import json
from pathlib import Path, PurePosixPath


def _find_project_root(start_dir):
    """從 cwd 往上找到含有 system_map.yaml 的目錄；找不到就回傳原始 cwd。"""
    d = os.path.abspath(start_dir)
    for _ in range(6):
        if os.path.exists(os.path.join(d, "system_map.yaml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            break
        d = parent
    return os.path.abspath(start_dir)


def _load_modules(root):
    """回傳 (modules_dict, yaml_path, is_corrupted)；若檔案存在但解析失敗，is_corrupted 為 True。"""
    yaml_path = os.path.join(root, "system_map.yaml")
    if not os.path.exists(yaml_path):
        return {}, yaml_path, False
    try:
        import yaml  # 專案本身已依賴 PyYAML（compile_map.py 也用它）
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
        if data is None or not isinstance(data, dict):
            return {}, yaml_path, True
        return data.get("modules", {}) or {}, yaml_path, False
    except Exception:
        return {}, yaml_path, True


def _build_src_map(modules):
    """{正規化後的檔案路徑: module_name}；Source 若帶 `::func` 只取路徑部分。"""
    mapping = {}
    for name, info in modules.items():
        src = (info or {}).get("source", "")
        if not src:
            continue
        path_part = src.split("::", 1)[0].strip()
        mapping[path_part.replace("\\", "/")] = name
    return mapping


def _is_stale(root):
    """比照 adad_pre_commit.py 的 check_staleness 邏輯：md 比 yaml 新就算過期。"""
    md_path = os.path.join(root, "system_map.md")
    yaml_path = os.path.join(root, "system_map.yaml")
    if not os.path.exists(md_path) or not os.path.exists(yaml_path):
        return False
    try:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from adad_core import get_max_mtime  # 會一併考慮 <!-- include --> 子檔案
        md_mtime = get_max_mtime(md_path)
    except Exception:
        md_mtime = os.path.getmtime(md_path)
    yaml_mtime = os.path.getmtime(yaml_path)
    return md_mtime > yaml_mtime + 1



# ---------------------------------------------------------------------------
# #85 — 風險分級豁免：Level 0 文件可平行，Level 1/2 維持 Fail-Closed
# ---------------------------------------------------------------------------

# Level 2：治理目錄（第一 token，casefold）
_GOV_FIRST = frozenset({".agents", ".claude", ".venv", "venv"})
# Level 2：治理子路徑（前兩 token，casefold tuple）
_GOV_2 = frozenset({
    ("docs", "specifications"),
    ("docs", "architecture"),
})
# Level 2：黑名單檔名（casefold，單一比對）
_GOV_NAMES = frozenset({
    "system_map.yaml", "system_map.md",
    "agents.md", "skill.md",
    ".gitmodules", ".gitattributes", ".gitignore",
})
# Level 0：放行副檔名（必須同時在 docs/ 目錄，或是根層 readme.md）
_EXEMPT_EXTS = frozenset({".md", ".txt", ".png", ".jpg", ".svg", ".css"})
# 全部受管的 mutation 操作（全小寫比較，相容多種 IDE / Agent API 工具名稱）
MUTATION_OPS = frozenset({
    "edit", "write", "multiedit", "delete", "rename", "move", "copy",
    "replace_file_content", "write_to_file", "multi_replace_file_content",
    "apply_patch", "delete_file", "move_file"
})


def _extract_target_paths(tool_input):
    """自多元異質 Schema 的 tool_input 中擷取 (file_path, destination)。"""
    if not isinstance(tool_input, dict):
        return "", ""
    file_path = (
        tool_input.get("file_path") or
        tool_input.get("TargetFile") or
        tool_input.get("target_file") or
        tool_input.get("path") or
        tool_input.get("target_path") or ""
    )
    destination = (
        tool_input.get("destination") or
        tool_input.get("Destination") or
        tool_input.get("dst") or ""
    )
    return str(file_path), str(destination)


def is_governance_file(rel_path):
    """判定相對路徑是否屬於 Level 2 治理檔。"""
    parts = PurePosixPath(rel_path).parts
    cf_name = parts[-1].casefold() if parts else ""
    if cf_name in _GOV_NAMES:
        return True
    if parts and parts[0].casefold() in _GOV_FIRST:
        return True
    if len(parts) >= 2 and (parts[0].casefold(), parts[1].casefold()) in _GOV_2:
        return True
    return False


def is_exempt_file(file_path, project_root, src_map):
    """三級 Deny-First 判定。True → Level 0 放行；False → 需 Task 授權或阻斷。

    ponytail: 純函式，無副作用。realpath + containment 為第一道防線。
    """
    if not file_path or not project_root:
        return False
    try:
        real_root = Path(project_root).resolve()
        real_target = Path(file_path).resolve()
        if not real_target.is_relative_to(real_root):
            return False  # 逃逸出 repo → 絕對阻斷
        rel = real_target.relative_to(real_root).as_posix()
    except Exception:
        return False

    parts = PurePosixPath(rel).parts
    cf_name = parts[-1].casefold() if parts else ""

    # --- Level 2（最優先：Deny-First）---
    if is_governance_file(rel):
        return False

    # --- Level 1：.py 無條件不豁免（含未登記新檔、偽裝檔名如 config.py.md）---
    if cf_name.endswith(".py") or ".py." in cf_name:
        return False
    if rel in src_map:  # 其他已登記的 source
        return False

    # --- Level 0 放行條款 ---
    ext = PurePosixPath(cf_name).suffix
    if len(parts) == 1 and cf_name == "readme.md":
        return True
    if parts and parts[0].casefold() == "docs" and ext in _EXEMPT_EXTS:
        return True

    return False  # 其餘一律不豁免


def _block(rule_id, level, path, next_action):
    """統一的 exit-2 Diagnostic 輸出（最小必要欄位）。"""
    print(
        f"🚫 [ADAD rule_id={rule_id} level={level}] {path}\n"
        f"next_action: {next_action}",
        file=sys.stderr,
    )
    sys.exit(2)


def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)  # 讀不到輸入就不阻擋，避免此腳本本身變成單點故障

    tool_name = str(data.get("tool_name", "")).casefold()
    if tool_name not in MUTATION_OPS:
        sys.exit(0)

    tool_input = data.get("tool_input", {}) or {}
    file_path, destination = _extract_target_paths(tool_input)
    if not file_path:
        _block(
            "L2-SCHEMA", "Level2", "unknown_target",
            "工具呼叫無法解析目標檔案路徑 (TargetFile/file_path 缺失)",
        )

    cwd = data.get("cwd") or os.getcwd()
    root = _find_project_root(cwd)

    modules, yaml_path, is_corrupted = _load_modules(root)
    if is_corrupted:
        _block(
            "L2-CORRUPT", "Level2", yaml_path,
            "system_map.yaml 損毀或非合法 YAML 格式，請修復或重新執行 compile_map.py",
        )
    if not modules and not os.path.exists(yaml_path):
        sys.exit(0)  # 非 ADAD 專案，不介入

    abs_path = file_path if os.path.isabs(file_path) else os.path.join(cwd, file_path)
    try:
        rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
    except Exception:
        sys.exit(0)

    # 護欄 0：Task Spec 修改權限範圍檢驗 (#86 決議 2.4(F))
    if rel_path.startswith(".agents/tasks/") and rel_path.endswith(".task.json"):
        content = str(tool_input.get("content") or tool_input.get("CodeContent") or "")
        if "unauthorized_contract_extension" in content or "change_input_schema" in content:
            _block(
                "L2-SPEC-BOUND", "Level2", rel_path,
                "Planning Agent 寫入之 Task Spec 超出 system_map 契約範圍，請改送 CP-3 規格更新",
            )

    src_map = _build_src_map(modules)

    # --- #85 Level 0 短路（必須在 staleness 檢查之前，否則 README.md 會被 stale 誤殺）---
    # 同時對 Rename/Move/Copy 的目標路徑做雙向判定
    destination = tool_input.get("destination", "")
    if destination:
        dst_abs = destination if os.path.isabs(destination) else os.path.join(cwd, destination)
        if not is_exempt_file(dst_abs, root, src_map):
            _block(
                "L2-DST", "Level1/2", destination,
                "rename/move destination 命中受管路徑，請建立 Task 後再操作",
            )
    if is_exempt_file(abs_path, root, src_map):
        sys.exit(0)  # Level 0 文件，直接放行

    # --- 護欄 1：system_map.yaml 是編譯產物，嚴禁人工/Agent 直接編輯 ---
    if rel_path == "system_map.yaml":
        _block(
            "L2-YAML", "Level2", rel_path,
            "改為修改 system_map.md 後執行: python .agents/skills/adad-workflow/scripts/compile_map.py",
        )

    # --- 護欄 2：system_map.md 已修改但尚未重新編譯，禁止任何模組程式碼變更 ---
    mod_name = src_map.get(rel_path)
    if rel_path not in ("system_map.md",) and _is_stale(root):
        _block(
            "RULE-01", "Level1", rel_path,
            "執行: python .agents/skills/adad-workflow/scripts/compile_map.py",
        )

    # Level 2 治理文件阻斷（不論是否在 src_map，不受 mod_name is None 影響）
    if is_governance_file(rel_path):
        _block(
            "L2-GOV", "Level2", rel_path,
            "此為治理/架構文件，需透過正式 ADAD 流程修改",
        )

    if mod_name is None:
        cf_rel = rel_path.casefold()
        if cf_rel.endswith(".py") or ".py." in cf_rel:
            _block(
                "L1-UNTRACKED", "Level1", rel_path,
                "此 Python / 偽裝程式碼檔案未在 system_map.yaml 登記為模組，請先增補架構地圖",
            )
        sys.exit(0)  # 這個檔案既非治理檔也非 .py 程式碼，且無對應模組，不介入

    # --- 護欄 3：Task 狀態門禁（取代原本直接查 RULE-02 模組 state） ---
    # ponytail: 改成呼叫 adad_core.ADADCore.check_task_gate，這是跟平台無關的
    # 純政策邏輯（只讀 .agents/tasks/<node>.task.json，不解析任何 agent 平台
    # 特有的 transcript 格式），Claude Code / Codex / 自建 agent 都能重用同一份
    # 判斷邏輯，差別只在「誰負責在動手前呼叫它」。
    try:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from adad_core import ADADCore
        cwd_before = os.getcwd()
        os.chdir(root)
        try:
            core = ADADCore(check_validity=False)  # staleness 已在護欄 2 檢查過
            gate = core.check_task_gate(rel_path)
        finally:
            os.chdir(cwd_before)
    except Exception:
        sys.exit(0)  # Task 機制本身故障不應該讓正常開發卡死，退回不阻擋

    if gate.get("soft_warning"):
        # 過渡期：模組還沒開始用 Task 流程，只提醒不阻擋，避免破壞既有專案。
        print(f"⚠️  [ADAD] {gate.get('reason')}", file=sys.stderr)
        sys.exit(0)

    if not gate.get("allow", True):
        _block(
            "TASK-GATE", "Level1", rel_path,
            f"python .agents/skills/adad-workflow/scripts/read_context.py {mod_name}",
        )

    sys.exit(0)


if __name__ == "__main__":
    main()
