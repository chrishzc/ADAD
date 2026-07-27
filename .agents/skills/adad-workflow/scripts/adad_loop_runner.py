# -*- coding: utf-8 -*-
"""
adad_loop_runner.py — #86 無狀態微型調度器 (Stateless Loop Runner)。

行為模式比照 CI Runner：
- 輪詢檔案系統中 Task JSON 的 status 欄位 (assigned -> submitted -> approved / CP-2 pending)。
- 依狀態變化自動分派 (dispatch) subprocess 到對應角色腳本 (Coding Agent、verify_against_spec.py 機械審查)。
- 零 LLM Token 排程開銷，不讀取、不解讀 spec 自然語言內容。
- 無 task_return_to_planning 的呼叫憑證，確保角色職責徹底分離。
"""
import sys
import os
import json
import subprocess
from pathlib import Path


def get_task_status(project_root, node_name):
    task_file = os.path.join(project_root, ".agents", "tasks", f"{node_name}.task.json")
    if not os.path.exists(task_file):
        return None, {}
    try:
        with open(task_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("status", "unknown"), data
    except Exception:
        return "corrupted", {}


def dispatch_step(node_name, project_root=None):
    root = project_root or os.getcwd()
    status, task_data = get_task_status(root, node_name)

    if not status:
        return {"status": "error", "message": f"Task for node '{node_name}' does not exist"}

    if status == "approved":
        return {"status": "completed", "message": f"Task '{node_name}' is already approved"}

    if status == "assigned":
        # 需要 Coding Agent 生成程式碼
        return {
            "status": "in_progress",
            "action": "coding_required",
            "node_name": node_name,
            "message": f"Task '{node_name}' is assigned. Waiting for Coding Agent to submit code.",
        }

    if status == "submitted":
        # 呼叫 verify_against_spec.py 機械審查
        script_path = os.path.join(root, "adad_source", "agents", "skills", "adad-workflow", "scripts", "verify_against_spec.py")
        if not os.path.exists(script_path):
            script_path = os.path.join(root, ".agents", "skills", "adad-workflow", "scripts", "verify_against_spec.py")

        try:
            res = subprocess.run(
                [sys.executable, script_path, node_name],
                cwd=root,
                capture_output=True,
                text=True,
                timeout=60,
            )
            try:
                review_out = json.loads(res.stdout) if res.stdout.strip() else {}
            except Exception:
                review_out = {"pass": False, "error": res.stderr}

            return {
                "status": "in_progress",
                "action": "mechanical_review_completed",
                "review_result": review_out,
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Mechanical review failed to execute: {str(e)}",
            }

    return {"status": status, "message": f"Task '{node_name}' is in status '{status}'"}


def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "Usage: python adad_loop_runner.py <node_name>"}))
        sys.exit(1)

    node_name = sys.argv[1]
    res = dispatch_step(node_name)
    print(json.dumps(res, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
