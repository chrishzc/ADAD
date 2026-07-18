# -*- coding: utf-8 -*-
"""
prepare_isolation.py — Agent 執行環境隔離模板 (Task #52)
ponytail: 最小實作。讀取 isolation_policy.json 決定白名單，
將允許的檔案複製到 .agents/workspaces/<node>，供 Agent 在該隔離目錄下執行。
"""
import sys
import os
import json
import shutil
import subprocess

# ponytail: 簡單的內建 policy，不需額外檔案，符合 "簡單" 原則。
# 如果未來需要可以再抽出去。
ISOLATION_POLICY = {
    "coding": {
        "whitelist": [
            "{source_file}",
            ".agents/tasks/{node_name}.task.json"
        ],
        "context_dump": "context.json"
    }
}

def prepare_isolation(node_name, artifact_type="coding"):
    if artifact_type not in ISOLATION_POLICY:
        return {"success": False, "error": f"未知的 artifact 類型: {artifact_type}"}

    task_path = f".agents/tasks/{node_name}.task.json"
    if not os.path.exists(task_path):
        return {"success": False, "error": f"任務快照不存在: {task_path}，請先確認任務已核發"}

    policy = ISOLATION_POLICY[artifact_type]
    workspace_dir = f".agents/workspaces/{node_name}"

    # 建立/清理隔離目錄
    if os.path.exists(workspace_dir):
        shutil.rmtree(workspace_dir)
    os.makedirs(workspace_dir, exist_ok=True)

    # 取得 context
    # 這裡直接呼叫 read_context.py (已存在) 確保 DRY
    script_dir = os.path.dirname(os.path.abspath(__file__))
    read_context_script = os.path.join(script_dir, "read_context.py")
    result = subprocess.run(
        [sys.executable, read_context_script, node_name],
        capture_output=True, text=True
    )
    if result.returncode != 0:
        return {"success": False, "error": f"無法取得上下文: {result.stderr}"}

    try:
        context_data = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"success": False, "error": f"解析上下文失敗: {result.stdout}"}

    # 寫入 context dump
    if policy.get("context_dump"):
        dump_path = os.path.join(workspace_dir, policy["context_dump"])
        with open(dump_path, "w", encoding="utf-8") as f:
            json.dump(context_data, f, ensure_ascii=False, indent=2)

    # 解析動態變數
    source_file = context_data.get("target_node", {}).get("source", "")

    # 複製白名單檔案
    copied_files = []
    for pattern in policy.get("whitelist", []):
        actual_path = pattern.replace("{node_name}", node_name).replace("{source_file}", source_file)
        if not actual_path or not os.path.exists(actual_path):
            continue

        dest_path = os.path.join(workspace_dir, actual_path)
        os.makedirs(os.path.dirname(dest_path), exist_ok=True)
        shutil.copy2(actual_path, dest_path)
        copied_files.append(actual_path)

    return {
        "success": True,
        "workspace": workspace_dir,
        "copied_files": copied_files,
        "context_dump": policy.get("context_dump")
    }

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "用法: python prepare_isolation.py <node_name> [artifact_type]"}, ensure_ascii=False))
        sys.exit(1)

    node_name = sys.argv[1]
    artifact_type = sys.argv[2] if len(sys.argv) > 2 else "coding"

    res = prepare_isolation(node_name, artifact_type)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)

if __name__ == "__main__":
    main()
