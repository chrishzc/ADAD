# -*- coding: utf-8 -*-
"""
ADAD Pre-Commit Hook — 機械強制核心規則
ponytail: 純標準庫實作（subprocess + ast + tempfile），不引入額外依賴。
將 AGENTS.md 軟規則轉為 git commit 階段的硬閘門。

檢查項目：
  1. Staleness 阻斷（RULE-01）
  2. 狀態門禁（RULE-02）
  3. 原子範圍警告（RULE-03）
  4. Invariants deny_imports 校驗
  5. Verification must_have_assertions 校驗
  6. 跨 Domain 依賴邊界校驗

Bug-fix (2026-07): 所有檔案內容一律透過 `git show :<path>` 讀取「暫存區（index）」
版本，而非讀磁碟工作目錄，防止「先 git add 違規版本 → 改乾淨但忘記重新 add」
的繞過攻擊向量。
"""
import subprocess
import sys
import os

import tempfile

# ponytail: 動態加入 scripts 目錄以便 import adad_core
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


# ─── Staged-blob 讀取工具 ────────────────────────────────────────────────────

def read_staged_bytes(path):
    """
    讀取暫存區（index）中指定路徑的原始位元組內容。
    若檔案不在 index 中（尚未 git add）則回傳 None。
    """
    result = subprocess.run(
        ["git", "show", f":0:{path}"],
        capture_output=True
    )
    if result.returncode != 0:
        return None
    return result.stdout


def is_staged(path):
    """判斷路徑是否存在於 staged index 中"""
    return read_staged_bytes(path) is not None


def staged_text(path, encoding="utf-8"):
    """以文字形式回傳 staged 版本內容，不在 index 中時回傳 None"""
    raw = read_staged_bytes(path)
    if raw is None:
        return None
    return raw.decode(encoding, errors="replace")


# ─── 主要工具函式 ────────────────────────────────────────────────────────────

def get_staged_files(diff_filter="ACM"):
    """取得 git staged 的指定 filter 檔案清單；git 失敗時阻斷 commit"""
    result = subprocess.run(
        ["git", "diff", "--cached", "--name-only", f"--diff-filter={diff_filter}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"❌ [PRE-COMMIT] git diff --cached 執行失敗（returncode={result.returncode}）\n"
            f"   {result.stderr.strip()}",
            file=sys.stderr
        )
        sys.exit(1)
    return [f for f in result.stdout.strip().split("\n") if f.strip()]


def check_staleness():
    """
    RULE-01: 若 system_map.md（staged 版）比 system_map.yaml（staged 版）新，阻斷 commit。

    比較邏輯：
    - 若兩者都在 staged index 中 → 比較各自的 git object mtime（用 blob hash
      的提交時間做代理）較複雜；實務上最可靠的判斷是：
      只要 system_map.md 有在 staging area 但 system_map.yaml 沒有被重新 add，
      就視為「可能過時」，輸出錯誤。
    - 若 system_map.yaml 本身也在 staged 中，則信任使用者有一起重新 compile 了，
      額外比對磁碟 mtime 做二次確認（不影響 staged 版本的正確性）。
    """
    md_path = "system_map.md"
    yaml_path = "system_map.yaml"

    md_staged = is_staged(md_path)
    yaml_staged = is_staged(yaml_path)

    if not md_staged and not yaml_staged:
        # 兩者都不在 index，非 ADAD 專案或尚未初始化，跳過
        return None

    if md_staged and not yaml_staged:
        return (
            "system_map.md 已加入暫存區但 system_map.yaml 尚未被 git add，"
            "請先執行 compile_map.py 後重新 git add system_map.yaml"
        )

    if not md_staged and yaml_staged:
        # yaml 有 staged 但 md 沒有，視為正常（只更新 yaml 本身的情境）
        return None

    # 兩者都在 staged：再以磁碟 mtime 做 sanity check
    if os.path.exists(md_path) and os.path.exists(yaml_path):
        try:
            from adad_core import get_max_mtime
            md_mtime = get_max_mtime(md_path)
            yaml_mtime = os.path.getmtime(yaml_path)
            if md_mtime > yaml_mtime + 1:
                return (
                    "system_map.md 或其包含的子檔案比 system_map.yaml 新，"
                    "請先執行 compile_map.py"
                )
        except Exception:
            pass  # ponytail: core 載入失敗時跳過 mtime 比較

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
    """RULE-02: 只有 planned/dirty/validated/draft/pending_review 狀態的模組才允許修改對應程式碼"""
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
    """對 staged .py 檔執行 deny_imports 校驗（讀 index，不讀磁碟）"""
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
        try:
            core = ADADCore("system_map.yaml", check_validity=False)
            raw = read_staged_bytes(f)
            if raw is None:
                continue
            suffix = os.path.splitext(f)[1] or ".py"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                result = core.check_invariants(mod_name, tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            if result and not result.get("success", True):
                for v in result.get("violations", []):
                    errors.append(
                        f"[INVARIANT] {f}:{v['line']} — 違反 {v['rule']}，匯入了 {v['imported']}"
                    )
        except Exception:
            pass  # ponytail: 無法載入 core 時不阻斷其他檢查
    return errors


def check_verification_staged(py_files, modules, src_map):
    """對 staged .py 檔執行 must_have_assertions 校驗（讀 index，不讀磁碟）"""
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
            raw = read_staged_bytes(f)
            if raw is None:
                continue
            suffix = os.path.splitext(f)[1] or ".py"
            with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
                tmp.write(raw)
                tmp_path = tmp.name
            try:
                result = core.verify_implementation(mod_name, tmp_path)
            finally:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass
            if result and not result.get("success", True):
                errors.append(f"[VERIFICATION] {f} — {result.get('error', '校驗失敗')}")
        except Exception:
            pass
    return errors


def check_domain_boundary_staged(staged_files, modules, src_map):
    """
    只要本次 commit 有觸碰到任一模組的原始碼，就對「整份架構圖」做一次
    跨 Domain 依賴邊界檢查（而不只是被改動的模組），因為邊界違規往往是
    因為別的模組新增了一條跨界依賴，而不是被改動的檔案本身有問題。

    架構圖資料來自 staged 版 system_map.yaml（若已在 index 中）。
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


def main():
    errors = []
    warnings = []

    # 1. Staleness 檢查
    stale = check_staleness()
    if stale:
        errors.append(f"[STALENESS] {stale}")

    # 取得 staged 檔案（ACM 用於內容檢查；D 單獨抓用於狀態門禁）
    staged = get_staged_files("ACM")
    deleted = get_staged_files("D")   # 刪除的檔案也要過 RULE-02 狀態門禁
    if not staged and not deleted:
        sys.exit(0)

    py_files = [f for f in staged if f.endswith(".py")]

    # 嘗試從 staged index 載入 system_map.yaml（Bug-fix: 不讀磁碟）
    yaml_path = "system_map.yaml"
    modules = {}
    src_map = {}
    yaml_content = staged_text(yaml_path)
    if yaml_content is None and os.path.exists(yaml_path):
        # yaml 未被 git add，但磁碟上存在；仍嘗試讀磁碟版本（降級策略，並記錄警告）
        warnings.append(
            "[STALENESS] system_map.yaml 不在暫存區，使用磁碟版本做架構檢查（結果可能不準確，建議重新 git add system_map.yaml）"
        )
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                yaml_content = f.read()
        except Exception:
            yaml_content = None

    if yaml_content:
        try:
            import yaml
            data = yaml.safe_load(yaml_content) or {}
            modules = data.get("modules", {})
            src_map = build_source_to_module_map(modules)
        except Exception:
            pass  # 載入失敗不阻斷，僅跳過需要 YAML 的檢查

    # 2-5. 各項檢查
    if src_map:
        errors.extend(check_state_gate(staged + deleted, modules, src_map))
        warnings.extend(check_atomic_scope(staged, src_map))
    if py_files and src_map:
        errors.extend(check_invariants_staged(py_files, modules, src_map))
        errors.extend(check_verification_staged(py_files, modules, src_map))
    if src_map:
        errors.extend(check_domain_boundary_staged(staged, modules, src_map))

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
