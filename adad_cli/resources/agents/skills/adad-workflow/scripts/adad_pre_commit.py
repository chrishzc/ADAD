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
  9. 模組落點校驗（RULE-05：模組必須寫在其 Domain/Subsystem 目前落腳的子地圖檔案）
"""
import subprocess
import sys
import os
import json
import ast
import tempfile

# ponytail: 動態加入 scripts 目錄以便 import adad_core
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)


def get_staged_files(diff_filter="ACM"):
    """
    取得 git staged 且符合指定 diff-filter 的檔案清單。

    ponytail (Bug 5 修正): 預設 "ACM"（新增/複製/修改）給需要讀檔案內容的檢查用
    （被刪除的檔案讀不到內容）。但狀態門禁、原子範圍這類只在意「這個模組的原始碼
    是否被動了」的檢查，應該用 "ACMD" 把刪除也算進去——不然砍掉一個 deployed
    模組的原始碼會完全繞過 RULE-02，因為刪除本身也是一種需要先轉成 dirty 才能做
    的變更。
    """
    # ponytail: CI 環境下 index 是空的，改跟 base branch 比對
    diff_target = [os.environ.get("GITHUB_BASE_REF", "HEAD~1"), "HEAD"] if os.environ.get("CI") else ["--cached"]
    if diff_target[0] != "--cached" and not diff_target[0].startswith("HEAD") and not diff_target[0].startswith("origin/"):
        diff_target[0] = f"origin/{diff_target[0]}"

    result = subprocess.run(
        ["git", "diff", *diff_target, "--name-only", f"--diff-filter={diff_filter}"],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        print(
            f"❌ [GIT] 無法取得 staged 檔案清單（git diff 執行失敗，returncode={result.returncode}）：\n"
            f"{result.stderr.strip()}",
            file=sys.stderr
        )
        print("🚫 Commit 被阻斷（無法確認變更內容，安全起見中止）。", file=sys.stderr)
        sys.exit(1)
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


def write_temp_file(content, suffix):
    """把內容寫進一個暫存檔，回傳路徑；呼叫端用完要負責刪除。"""
    fd, tmp_path = tempfile.mkstemp(suffix=suffix)
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(content)
    return tmp_path


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
    """
    RULE-02: 只有 planned/dirty/validated/draft 狀態的模組才允許修改對應程式碼。

    ponytail (Bug 6 修正): 原本這裡混進了 pending_review，跟本函式的文件說明矛盾。
    pending_review 語意是「已提交待人類審查」，這個狀態理應被凍結——如果允許在
    送審期間繼續靜默修改程式碼，等於讓 RULE-02 的審查閘門形同虛設。要修改已進入
    pending_review 的程式碼，應該先用 transit_state.py 轉回 dirty，讓狀態轉移
    留下明確紀錄，而不是繞過去直接改。
    """
    errors = []
    allowed_states = {"planned", "dirty", "validated", "draft"}
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


def check_task_gate_staged(staged_files, src_map, map_path=None):
    """
    Task 狀態門禁：commit 時再檢查一次 .agents/tasks/<node>.task.json 的 status。

    這是 RULE-02 的補強，不是取代——RULE-02 管的是模組長期生命週期（防止改動
    已 deployed 的模組），Task Gate 管的是這一輪施工指令有沒有還在「開放編輯」
    的狀態。兩者分開檢查，任一項不過都會擋下 commit。

    ponytail: 這裡刻意做成 pre-commit 層級的第二道防線，是因為 PreToolUse hook
    這種「動手前攔截」的機制不是每個 agent 平台都支援到位——例如 Codex CLI 目前
    的 PreToolUse hook 只對 Bash 工具呼叫觸發，對它自己原生的檔案編輯工具
    （apply_patch）完全不會觸發。不管是哪個平台、用什麼工具改的檔案，只要最後
    真的要 commit，這裡都逃不掉，把防線退到所有平台都繞不過去的關卡上。

    map_path 傳入 staged/index 版本的暫存檔路徑（呼叫端已經為其他檢查產生過），
    跟其餘檢查一致地以「即將被 commit 的內容」為準，而不是工作目錄上可能還沒
    git add 的版本。
    """
    errors = []
    warnings = []
    try:
        from adad_core import ADADCore, MAP_FILE
        core = ADADCore(map_path=map_path or MAP_FILE, check_validity=False)  # staleness 已由 check_staleness() 檢查過
    except Exception:
        return errors, warnings  # Task 機制本身故障不應該讓 commit 整個卡死

    checked_nodes = set()
    for f in staged_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None or mod_name in checked_nodes:
            continue
        checked_nodes.add(mod_name)
        try:
            gate = core.check_task_gate(f_norm)
        except Exception:
            continue
        if gate.get("soft_warning"):
            warnings.append(gate.get("reason"))
        elif not gate.get("allow", True):
            errors.append(f"[TASK GATE] {gate.get('reason')}")
    return errors, warnings


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


def check_invariants_staged(py_files, modules, src_map, map_path):
    """對 staged .py 檔執行 deny_imports 校驗（讀 git index 內容，不讀工作目錄）"""
    from adad_core import ADADCore
    errors = []
    # ponytail-fix: 原本 ADADCore(map_path) 寫在迴圈內，代表每一個 staged .py
    # 檔案都會重新讀取並解析一次整份 system_map.yaml。專案小的時候感覺不出來，
    # 但實測在 2000 模組規模、50 個 staged 檔案的情境下，這個寫法要跑 67 秒；
    # 搬到迴圈外只載入一次之後，同樣的工作只要 1.3 秒。這正是會讓
    # pre-commit 從「跟 Linter 一樣快」變成「卡到讓人想用 --no-verify」的元兇，
    # 必須修掉，而不是靠使用者忍耐。
    try:
        core = ADADCore(map_path, check_validity=False)
    except Exception:
        return errors  # 無法載入 core 時不阻斷其他檢查
    for f in py_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None:
            continue
        mod_info = modules.get(mod_name, {})
        if not mod_info.get("invariants"):
            continue
        staged_content = get_staged_content(f)
        if staged_content is None:
            continue  # 理論上不該發生（ACM filter 保證此檔存在於 index），保守略過
        tmp_py = None
        try:
            tmp_py = write_temp_file(staged_content, suffix=".py")
            result = core.check_invariants(mod_name, tmp_py)
            if not result.get("success", True):
                for v in result.get("violations", []):
                    errors.append(
                        f"[INVARIANT] {f}:{v['line']} — 違反 {v['rule']}，詳情：{v.get('detail', '')}"
                    )
        except Exception:
            pass  # ponytail: 單一檔案解析失敗不阻斷其他檢查
        finally:
            if tmp_py and os.path.exists(tmp_py):
                os.remove(tmp_py)
    return errors


def check_verification_staged(py_files, modules, src_map, map_path):
    """對 staged .py 檔執行 must_have_assertions 校驗（讀 git index 內容，不讀工作目錄）"""
    from adad_core import ADADCore
    errors = []
    # ponytail-fix: 同上，ADADCore 只在這裡載入一次，不要放進迴圈。
    try:
        core = ADADCore(map_path, check_validity=False)
    except Exception:
        return errors
    for f in py_files:
        f_norm = f.replace("\\", "/")
        mod_name = src_map.get(f_norm)
        if mod_name is None:
            continue
        mod_info = modules.get(mod_name, {})
        if not mod_info.get("verification"):
            continue
        staged_content = get_staged_content(f)
        if staged_content is None:
            continue
        tmp_py = None
        try:
            tmp_py = write_temp_file(staged_content, suffix=".py")
            result = core.verify_implementation(mod_name, tmp_py)
            if not result.get("success", True):
                errors.append(f"[VERIFICATION] {f} — {result.get('error', '校驗失敗')}")
        except Exception:
            pass
        finally:
            if tmp_py and os.path.exists(tmp_py):
                os.remove(tmp_py)
    return errors


def check_domain_boundary_staged(staged_files, modules, src_map, map_path):
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
        core = ADADCore(map_path, check_validity=False)
        result = core.check_domain_boundary()
        if not result.get("passed", True):
            for v in result.get("violations", []):
                errors.append(f"[DOMAIN BOUNDARY] {v['reason']}")
    except Exception:
        pass  # ponytail: 無法載入 core 時不阻斷其他檢查
    return errors


from adad_core import build_file_to_registered_functions, get_top_level_function_names


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


def check_module_placement(modules, domains):
    """
    RULE-05：模組必須寫在其所屬 Domain/Subsystem 目前落腳的子地圖檔案裡。

    依模組目前的生命週期狀態決定嚴重度，而不是一律阻斷：
    - `planned` / `draft`：尚未通過任何一次人工 Checkpoint 審查，規劃期本來就
      預期會邊規劃邊調整位置，先寫草稿、之後再挪到正確的子地圖是正常流程。
      這個階段只發出 WARNING，不阻斷 commit。
    - 其餘狀態（`pending_review` 以上，代表至少通過一次 Checkpoint、甚至已經
      有其他模組依賴它）：放錯位置已經是真正的結構性問題，直接阻斷 commit。
    """
    from adad_core import find_misplaced_modules
    LOOSE_STATES = {"planned", "draft"}
    errors = []
    warnings = []
    misplaced = find_misplaced_modules({"modules": modules, "domains": domains})
    for m in misplaced:
        state = modules.get(m["module"], {}).get("state", "planned")
        detail = (
            f"模組 `{m['module']}`（屬於 {m['scope']} `{m['scope_name']}`，狀態: `{state}`）"
            f"實際寫在 [{m['actual_file']}]，但應該寫在 [{m['expected_file']}]。"
            f"請搬移，或執行 resolve_target_file.py 確認正確落點"
        )
        if state in LOOSE_STATES:
            warnings.append(f"[RULE-05] {detail}（狀態為 `{state}`，規劃期暫不阻斷，但建議盡快搬移）")
        else:
            errors.append(f"[RULE-05] {detail}")
    return errors, warnings


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

    # 1. Staleness 檢查（比對本機檔案 mtime，跟 git 暫存無關，維持讀磁碟）
    stale = check_staleness()
    if stale:
        errors.append(f"[STALENESS] {stale}")

    # 取得 staged 檔案
    # ponytail (Bug 5 修正): staged 只含 ACM（讀內容用），staged_all 額外含刪除（D），
    # 給狀態門禁 / 原子範圍 / domain boundary 這些只在意「有沒有被動到」的檢查用。
    staged = get_staged_files("ACM")
    staged_all = get_staged_files("ACMD")
    if not staged_all:
        sys.exit(0)

    py_files = [f for f in staged if f.endswith(".py")]

    # 載入「即將被 commit」的 system_map.yaml（staged/index 版本，而非工作目錄）
    yaml_path = "system_map.yaml"
    modules = {}
    domains = {}
    src_map = {}
    tmp_map_path = None
    staged_yaml_content = get_staged_content(yaml_path)
    if staged_yaml_content is None and os.path.exists(yaml_path):
        # ponytail: yaml 尚未被 git 追蹤/staged（例如專案剛初始化）時，退回讀磁碟版本，
        # 盡力而為；一旦被 git add 過，之後一律以 staged 內容為準。
        try:
            with open(yaml_path, "r", encoding="utf-8") as f:
                staged_yaml_content = f.read()
        except Exception:
            staged_yaml_content = None
    if staged_yaml_content is not None:
        try:
            import yaml
            data = yaml.safe_load(staged_yaml_content) or {}
            modules = data.get("modules", {})
            domains = data.get("domains", {})
            src_map = build_source_to_module_map(modules)
            tmp_map_path = write_temp_file(staged_yaml_content, suffix=".yaml")
        except Exception:
            pass  # 載入失敗不阻斷，僅跳過需要 YAML 的檢查

    try:
        # 0. Source 綁定完整性檢查（代辦事項 #8）：src_map 是下面所有檢查反查
        # 模組的唯一依據，若映射本身有歧義（重複綁定、整檔/逐函式混用），
        # 之後的 RULE-02/03/04、Invariants、Verification、Domain Boundary
        # 全部會依附在錯的（或不完整的）映射上靜默失效，因此在使用 src_map
        # 之前就先擋下來，而不是等結果算錯了才發現。
        if tmp_map_path:
            from adad_core import ADADCore
            try:
                _core_for_binding = ADADCore(tmp_map_path, check_validity=False)
                binding_result = _core_for_binding.check_source_binding()
                if not binding_result["passed"]:
                    for v in binding_result["violations"]:
                        errors.append(f"[SOURCE BINDING] {v['reason']}")
            except Exception:
                pass  # 無法載入時不阻斷其他檢查，交由後續檢查各自 best-effort

        # 2-8. 各項檢查
        if src_map:
            errors.extend(check_state_gate(staged_all, modules, src_map))
            warnings.extend(check_atomic_scope(staged_all, src_map))
            task_errors, task_warnings = check_task_gate_staged(staged_all, src_map, map_path=tmp_map_path)
            errors.extend(task_errors)
            warnings.extend(task_warnings)
        if py_files and src_map and tmp_map_path:
            errors.extend(check_invariants_staged(py_files, modules, src_map, tmp_map_path))
            errors.extend(check_verification_staged(py_files, modules, src_map, tmp_map_path))
        if src_map and tmp_map_path:
            errors.extend(check_domain_boundary_staged(staged_all, modules, src_map, tmp_map_path))
        if modules:
            errors.extend(check_dangling_dependencies(modules))
        if modules and domains:
            e5, w5 = check_module_placement(modules, domains)
            errors.extend(e5)
            warnings.extend(w5)
        if py_files and modules:
            errors.extend(check_unregistered_functions(py_files, modules))
    finally:
        if tmp_map_path and os.path.exists(tmp_map_path):
            os.remove(tmp_map_path)

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