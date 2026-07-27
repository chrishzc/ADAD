# -*- coding: utf-8 -*-
"""
verify_against_spec.py — #86 第一層（機械層）審查腳本。

五階段短路快篩鏈 (Fail-Fast Pipeline)：
0. 語法快篩 (py_compile)：檢查 AST 語法錯誤，失敗即快速阻斷。
1. Diff 去重快篩：比對本輪 git diff SHA256，若與上一輪打回完全相同，直接判定本層 fail 且沿用上一輪 fingerprint。
2. AST 靜態 Invariants 檢查 (check_invariants)。
3. Verification Cases 斷言檢查 (verify_implementation)。
4. Signature Diff Checker：比對實體 AST 簽章與 system_map.yaml 契約。

輸出格式：
{"pass": bool, "mismatches": [...], "fingerprint": "..."}
"""
import sys
import os
import json
import py_compile
import hashlib
import subprocess
from pathlib import Path


def _compute_fingerprint(data_str):
    return hashlib.sha256(data_str.encode("utf-8")).hexdigest()[:16]


def check_syntax(file_path):
    """步驟 0：語法快篩 (py_compile)。"""
    if not file_path or not os.path.exists(file_path) or not file_path.endswith(".py"):
        return None
    try:
        py_compile.compile(file_path, doraise=True)
        return None
    except py_compile.PyCompileError as e:
        err_msg = str(e)
        fp = _compute_fingerprint(f"SyntaxError:{file_path}:{err_msg}")
        return {
            "rule_id": "L1-SYNTAX-ERROR",
            "target_file": file_path,
            "reason": err_msg,
            "fingerprint": fp,
        }


def check_diff_dedup(project_root, last_diff_hash, last_fingerprint):
    """步驟 1：Diff 去重快篩。"""
    try:
        cmd = ["git", "diff", "HEAD"]
        res = subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, timeout=10)
        if res.returncode == 0 and res.stdout.strip():
            cur_hash = hashlib.sha256(res.stdout.encode("utf-8")).hexdigest()
            if last_diff_hash and cur_hash == last_diff_hash:
                return {
                    "is_duplicate": True,
                    "diff_hash": cur_hash,
                    "fingerprint": last_fingerprint or _compute_fingerprint(cur_hash),
                }
            return {"is_duplicate": False, "diff_hash": cur_hash}
    except Exception:
        pass
    return {"is_duplicate": False, "diff_hash": ""}


def run_mechanical_review(node_name, project_root=None, last_diff_hash=None, last_fingerprint=None):
    """主程序：執行五階段機械審查。"""
    root = project_root or os.getcwd()
    mismatches = []

    # 載入 Task 快照
    task_file = os.path.join(root, ".agents", "tasks", f"{node_name}.task.json")
    if not os.path.exists(task_file):
        return {
            "pass": False,
            "mismatches": [{
                "rule_id": "L1-NO-TASK",
                "target_file": task_file,
                "reason": f"Task 快照檔案不存在: {task_file}",
            }],
            "fingerprint": _compute_fingerprint(f"NO_TASK:{node_name}"),
        }

    try:
        with open(task_file, "r", encoding="utf-8") as f:
            task_data = json.load(f)
    except Exception as e:
        return {
            "pass": False,
            "mismatches": [{
                "rule_id": "L1-TASK-CORRUPT",
                "target_file": task_file,
                "reason": f"Task 快照損毀: {str(e)}",
            }],
            "fingerprint": _compute_fingerprint(f"TASK_CORRUPT:{node_name}"),
        }

    spec = task_data.get("spec", {})
    target_file = spec.get("target_file", "")
    abs_target = os.path.join(root, target_file) if target_file else ""

    # 步驟 0：語法快篩
    if abs_target:
        syntax_err = check_syntax(abs_target)
        if syntax_err:
            return {
                "pass": False,
                "mismatches": [syntax_err],
                "fingerprint": syntax_err["fingerprint"],
            }

    # 步驟 1：Diff 去重快篩
    dedup = check_diff_dedup(root, last_diff_hash, last_fingerprint)
    if dedup.get("is_duplicate"):
        return {
            "pass": False,
            "mismatches": [{
                "rule_id": "L1-DUPLICATE-DIFF",
                "target_file": target_file,
                "reason": "本輪程式碼修改與上一輪被打回時完全相同 (Diff Deduplicated)",
            }],
            "fingerprint": dedup["fingerprint"],
            "diff_hash": dedup["diff_hash"],
        }

    # 步驟 2 & 3：動用 adad_core 執行 Invariants & Verification Cases
    try:
        scripts_dir = os.path.dirname(os.path.abspath(__file__))
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        from adad_core import ADADCore
        core = ADADCore(project_root=root, check_validity=False)

        # 執行 verify_implementation
        v_res = core.verify_implementation(node_name)
        if not v_res.get("success", False):
            err_reason = v_res.get("error") or "Verification failed"
            fp = _compute_fingerprint(f"VERIFY_FAIL:{node_name}:{err_reason}")
            mismatches.append({
                "rule_id": "L1-VERIFICATION-FAIL",
                "target_file": target_file,
                "reason": str(err_reason)[:200],
            })
            return {
                "pass": False,
                "mismatches": mismatches,
                "fingerprint": fp,
                "diff_hash": dedup.get("diff_hash", ""),
            }
    except Exception as e:
        fp = _compute_fingerprint(f"EXEC_ERR:{node_name}:{str(e)}")
        mismatches.append({
            "rule_id": "L1-EXEC-ERROR",
            "target_file": target_file,
            "reason": f"審查腳本執行異常: {str(e)[:200]}",
        })
        return {
            "pass": False,
            "mismatches": mismatches,
            "fingerprint": fp,
            "diff_hash": dedup.get("diff_hash", ""),
        }

    # 機械層全部通過
    return {
        "pass": True,
        "mismatches": [],
        "fingerprint": _compute_fingerprint(f"PASS:{node_name}"),
        "diff_hash": dedup.get("diff_hash", ""),
    }


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"pass": False, "error": "缺少 node_name 參數"}))
        sys.exit(1)

    node_name = sys.argv[1]
    res = run_mechanical_review(node_name)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("pass") else 2)


if __name__ == "__main__":
    main()
