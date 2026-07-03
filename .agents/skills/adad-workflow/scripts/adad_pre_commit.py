# -*- coding: utf-8 -*-
"""
ADAD Pre-Commit Hook — 機械強制核心規則
ponytail: 純標準庫實作（subprocess + ast），不引入額外依賴。
將 AGENTS.md 軟規則轉為 git commit 階段的硬閘門。

檢查項目：
  1. Staleness 阻斷（RULE-01）
  2. 狀態門禁（RULE-02）
  3. 原子範圍警告（RULE-03）
  4. Invariants deny_imports 校驗
  5. Verification must_have_assertions 校驗
  6. 跨 Domain 依賴邊界校驗
  7. 未登記函式掃描（RULE-04：實作前必須先登記於 system_map）
  8. 懸空依賴校驗（dependencies 指向不存在的節點）
"""
import subprocess
import sys
import os
import json
import ast

# ponytail: 動態加入 scripts 目錄以便 import adad_core
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def get_staged_files():
    """取得 git staged 的新增/修改檔案清單"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", "--diff-filter=ACM"],
        capture_output=True, text=True
    )
    return [f for f in result.stdout.strip().split("\n") if f.strip()]


def get_staged_content(path):
    """
    取得 path 在 git index（staged）中的實際內容，而不是工作目錄上的檔案。
    ponytail: 用 :0:path 明確指定 stage 0（一般情況下唯一版本）。
    這樣即使工作目錄後來又被改動、但忘記重新 git add，檢查的仍然是
    真正即將被 commit 的內容，而不是磁碟上可能已經不一致的版本。
    讀取失敗時回傳 None，交由呼叫端決定是否略過該檔案。
    """
    result = subprocess.run(
        ["git", "show", f":0:{path}"],
        capture_output=True
    )
    if result.returncode != 0:
        return None
    return result.stdout.decode("utf-8", errors="ignore")


def check_staleness():
    """RULE-01: 若 system_map.md (或其包含的子檔案) 比 system_map.yaml 新，阻斷 commit"""
    md_path = "system_map.md"
    yaml_path = "system_map.yaml"
    if not os.path.exists(md_path) or not os.path.exists(yaml_path):
        return None  # 非 ADAD 專案或尚未初始化，跳過
    from adad_core import get_max_mtime
    md_mtime = get_max_mtime(md_path)
    yaml_mtime = os.path.getmtime(yaml_path)
    if md_mtime > yaml_mtime + 1:
        return "system_map.md 或其包含的子檔案比 system_map.yaml 新，請先執行 compile_map.py"
    return None


def build_source_to_module_map(modules):
    """從 system_map.yaml 的 source 欄位建立 {filepath: module_name} 映射"""
    mapping = {}
    for name, info in modules.items():
        src = info.get("source", "")
        if src:
            # 正規化路徑分隔符
            mapping[src.replace("\\", "/")] = name
    return mapping


def check_state_gate(staged_files, modules, src_map):
    """RULE-02: 只有 planned/dirty/validated/draft 狀態的模組才允許修改對應程式碼"""
    errors = []
    allowed_states = {"planned", "dirty", "validated", "draft", "pending_review"}
    for f in staged_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None:
            continue  # 不在 source 映射中，跳過（非模組程式碼）
        state = modules.get(mod_name, {}).get("state", "unknown")
        if state not in allowed_states:
            errors.append(
                f"[RULE-02] 檔案 {f} 對應模組 `{mod_name}` 狀態為 `{state}`，"
                f"只有 {allowed_states} 狀態才允許修改程式碼"
            )
    return errors


def check_atomic_scope(staged_files, src_map):
    """RULE-03: 計算涉及的不同模組數量，>1 發出 WARNING"""
    touched_modules = set()
    for f in staged_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name:
            touched_modules.add(mod_name)
    warnings = []
    if len(touched_modules) > 1:
        warnings.append(
            f"[RULE-03] 本次 commit 涉及 {len(touched_modules)} 個模組的程式碼 "
            f"({', '.join(sorted(touched_modules))}), 建議拆分為原子 commit"
        )
    return warnings


def check_invariants_staged(py_files, modules, src_map):
    """對 staged .py 檔執行 deny_imports 校驗"""
    from adad_core import ADADCore
    errors = []
    for f in py_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None:
            continue
        mod_info = modules.get(mod_name, {})
        if not mod_info.get("invariants"):
            continue
        # 借用 ADADCore 的 check_invariants 方法
        try:
            core = ADADCore("system_map.yaml", check_validity=False)
            result = core.check_invariants(mod_name, f)
            if not result.get("success", True):
                for v in result.get("violations", []):
                    errors.append(
                        f"[INVARIANT] {f}:{v['line']} — 違反 {v['rule']}，匯入了 {v['imported']}"
                    )
        except Exception:
            pass  # ponytail: 無法載入 core 時不阻斷其他檢查
    return errors


def check_verification_staged(py_files, modules, src_map):
    """對 staged .py 檔執行 must_have_assertions 校驗"""
    from adad_core import ADADCore
    errors = []
    for f in py_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None:
            continue
        mod_info = modules.get(mod_name, {})
        if not mod_info.get("verification"):
            continue
        try:
            core = ADADCore("system_map.yaml", check_validity=False)
            result = core.verify_implementation(mod_name, f)
            if not result.get("success", True):
                errors.append(f"[VERIFICATION] {f} — {result.get('error', '校驗失敗')}")
        except Exception:
            pass
    return errors


def check_domain_boundary_staged(staged_files, modules, src_map):
    """
    只要本次 commit 有觸碰到任一模組的原始碼，就對「整份架構圖」做一次
    跨 Domain 依賴邊界檢查（而不只是被改動的模組），因為邊界違規往往是
    因為別的模組新增了一條跨界依賴，而不是被改動的檔案本身有問題。
    """
    from adad_core import ADADCore
    errors = []
    touched_any_module = any(
        src_map.get(f.replace("\\", "/")) for f in staged_files
    )
    if not touched_any_module:
        return errors
    try:
        core = ADADCore("system_map.yaml", check_validity=False)
        result = core.check_domain_boundary()
        if not result.get("passed", True):
            for v in result.get("violations", []):
                errors.append(f"[DOMAIN BOUNDARY] {v['reason']}")
    except Exception:
        pass  # ponytail: 無法載入 core 時不阻斷其他檢查
    return errors


def build_file_to_registered_functions(modules):
    """
    從 system_map.yaml 的 source 欄位建立 {file_path: {"whole_file": bool, "functions": set, "nodes": [...]}}。

    source 欄位的兩種寫法：
      - "path/to/file.py"                         → 整個檔案視為單一節點，不逐函式比對
      - "path/to/file.py::func_name"               → 該節點只對應檔案內的這一個函式
      - "path/to/file.py::f1,f2,f3"                → 該節點對應檔案內的多個函式（逗號分隔）
    """
    file_map = {}
    for name, info in modules.items():
        src = (info.get("source") or "").replace("\\", "/")
        if not src:
            continue
        if "::" in src:
            file_path, funcs_part = src.split("::", 1)
            funcs = [f.strip() for f in funcs_part.split(",") if f.strip()]
        else:
            file_path, funcs = src, []
        entry = file_map.setdefault(file_path, {"whole_file": False, "functions": set(), "nodes": []})
        entry["nodes"].append(name)
        if funcs:
            entry["functions"].update(funcs)
        else:
            entry["whole_file"] = True
    return file_map


def get_top_level_function_names(source_code):
    """
    解析原始碼，回傳所有 top-level 函式名稱（含 class 內的方法，以 Class.method 表示）。
    語法錯誤時回傳 None，交由呼叫端略過（避免跟其他檢查重複報同一個語法錯誤）。
    """
    try:
        tree = ast.parse(source_code)
    except SyntaxError:
        return None
    names = set()
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            names.add(node.name)
        elif isinstance(node, ast.ClassDef):
            for sub in node.body:
                if isinstance(sub, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    names.add(f"{node.name}.{sub.name}")
    return names


def check_unregistered_functions(py_files, modules):
    """
    RULE-04 硬閘門：掃描 staged .py 檔案中所有 top-level 函式，
    只要有函式不在 system_map.yaml 對應節點的 source 清單中，就阻斷 commit，
    要求先提出 Schema Update Request 經人類審查，而不是讓 agent 靠自覺記得。

    ponytail: 只對「已經有節點指到這個檔案、且是逐函式登記（source 帶 ::）」的檔案生效。
    完全沒被任何節點引用的檔案（非 ADAD 追蹤範圍）、或整檔對應單一節點的情況，不在此檢查範圍。
    """
    file_map = build_file_to_registered_functions(modules)
    errors = []
    for f in py_files:
        f_norm = f.replace("\\", "/")
        entry = file_map.get(f_norm)
        if entry is None or entry["whole_file"]:
            continue
        staged_content = get_staged_content(f)
        if staged_content is None:
            continue
        actual_funcs = get_top_level_function_names(staged_content)
        if actual_funcs is None:
            continue  # 語法錯誤，交給其他檢查處理
        unregistered = actual_funcs - entry["functions"]
        for fn in sorted(unregistered):
            errors.append(
                f"[RULE-04] {f} 中的函式 `{fn}` 未登記於 system_map.yaml"
                f"（此檔案已有節點 {sorted(entry['nodes'])}，但未涵蓋 `{fn}`）。"
                f"請先提出 Schema Update Request 經人類審查後再實作"
            )
    return errors


def check_dangling_dependencies(modules):
    """
    校驗每個模組的 dependencies 是否都指向 system_map.yaml 中實際存在的節點，
    避免出現「被依賴但從未定義」的懸空引用（例如引用了不存在的節點名稱）。
    """
    errors = []
    known = set(modules.keys())
    for name, info in modules.items():
        for dep in (info.get("dependencies") or []):
            if dep not in known:
                errors.append(
                    f"[SCHEMA] 模組 `{name}` 依賴了不存在的節點 `{dep}`，"
                    f"請確認命名是否有誤，或該節點尚未登記於 system_map.yaml"
                )
    return errors


def main():
    errors = []
    warnings = []

    # 1. Staleness 檢查
    stale = check_staleness()
    if stale:
        errors.append(f"[STALENESS] {stale}")

    # 取得 staged 檔案
    staged = get_staged_files()
    if not staged:
        sys.exit(0)

    py_files = [f for f in staged if f.endswith(".py")]

    # 嘗試載入 system_map.yaml
    yaml_path = "system_map.yaml"
    modules = {}
    src_map = {}
    if os.path.exists(yaml_path):
        try:
            # ponytail: 直接用 yaml.safe_load 避免循環 import
            import yaml
            with open(yaml_path, "r", encoding="utf-8") as f:
                data = yaml.safe_load(f) or {}
            modules = data.get("modules", {})
            src_map = build_source_to_module_map(modules)
        except Exception:
            pass  # 載入失敗不阻斷，僅跳過需要 YAML 的檢查

    # 2-8. 各項檢查
    if src_map:
        errors.extend(check_state_gate(staged, modules, src_map))
        warnings.extend(check_atomic_scope(staged, src_map))
    if py_files and src_map:
        errors.extend(check_invariants_staged(py_files, modules, src_map))
        errors.extend(check_verification_staged(py_files, modules, src_map))
    if src_map:
        errors.extend(check_domain_boundary_staged(staged, modules, src_map))
    if modules:
        errors.extend(check_dangling_dependencies(modules))
    if py_files and modules:
        errors.extend(check_unregistered_functions(py_files, modules))

    # 輸出結果
    for w in warnings:
        print(f"⚠️  {w}", file=sys.stderr)
    for e in errors:
        print(f"❌ {e}", file=sys.stderr)

    if errors:
        print(
            "\n🚫 Commit 被阻斷。請修正上述問題後重試。\n"
            "   （緊急情況可用 git commit --no-verify 繞過）",
            file=sys.stderr
        )
        sys.exit(1)

    sys.exit(0)


if __name__ == "__main__":
    main()