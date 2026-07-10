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
    """回傳 (modules_dict, yaml_path)；任何失敗都回傳 ({}, yaml_path)。"""
    yaml_path = os.path.join(root, "system_map.yaml")
    if not os.path.exists(yaml_path):
        return {}, yaml_path
    try:
        import yaml  # 專案本身已依賴 PyYAML（compile_map.py 也用它）
        with open(yaml_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return data.get("modules", {}) or {}, yaml_path
    except Exception:
        return {}, yaml_path


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



def main():
    try:
        raw = sys.stdin.read()
        data = json.loads(raw) if raw.strip() else {}
    except Exception:
        sys.exit(0)  # 讀不到輸入就不阻擋，避免此腳本本身變成單點故障

    tool_name = data.get("tool_name", "")
    if tool_name not in ("Edit", "Write", "MultiEdit"):
        sys.exit(0)

    tool_input = data.get("tool_input", {}) or {}
    file_path = tool_input.get("file_path", "")
    if not file_path:
        sys.exit(0)

    cwd = data.get("cwd") or os.getcwd()
    root = _find_project_root(cwd)

    modules, yaml_path = _load_modules(root)
    if not modules:
        sys.exit(0)  # 非 ADAD 專案、或尚未 compile 出任何模組，不介入

    abs_path = file_path if os.path.isabs(file_path) else os.path.join(cwd, file_path)
    try:
        rel_path = os.path.relpath(abs_path, root).replace("\\", "/")
    except Exception:
        sys.exit(0)

    # --- 護欄 1：system_map.yaml 是編譯產物，嚴禁人工/Agent 直接編輯 ---
    if rel_path == "system_map.yaml":
        print(
            "🚫 [ADAD] system_map.yaml 是由 compile_map.py 從 system_map.md 編譯出來的中間表示，\n"
            "嚴禁直接編輯。請改為修改 system_map.md，再執行：\n"
            "  python .agents/skills/adad-workflow/scripts/compile_map.py",
            file=sys.stderr,
        )
        sys.exit(2)

    # --- 護欄 2：system_map.md 已修改但尚未重新編譯，禁止任何模組程式碼變更 ---
    # （system_map.md 本身、以及非模組程式碼檔案不受此限，避免卡死正常架構規劃）
    src_map = _build_src_map(modules)
    mod_name = src_map.get(rel_path)

    if rel_path not in ("system_map.md",) and _is_stale(root):
        print(
            "🚫 [ADAD RULE-01] system_map.md 比 system_map.yaml 新，架構事實尚未同步。\n"
            "請先執行以下指令重新編譯，再繼續修改程式碼：\n"
            "  python .agents/skills/adad-workflow/scripts/compile_map.py",
            file=sys.stderr,
        )
        sys.exit(2)

    if mod_name is None:
        sys.exit(0)  # 這個檔案沒有對應到任何已登記模組，不在 ADAD 追蹤範圍內

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
        print(
            f"🚫 [ADAD TASK GATE] {gate.get('reason')}\n\n"
            f"若還不確定目前上下文，可先執行：\n"
            f"  python .agents/skills/adad-workflow/scripts/read_context.py {mod_name}",
            file=sys.stderr,
        )
        sys.exit(2)

    sys.exit(0)


if __name__ == "__main__":
    main()
