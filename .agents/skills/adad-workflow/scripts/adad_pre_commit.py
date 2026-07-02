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
"""
import subprocess
import sys
import os
import json

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

    # 2-5. 各項檢查
    if src_map:
        errors.extend(check_state_gate(staged, modules, src_map))
        warnings.extend(check_atomic_scope(staged, src_map))
    if py_files and src_map:
        errors.extend(check_invariants_staged(py_files, modules, src_map))
        errors.extend(check_verification_staged(py_files, modules, src_map))

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
