# -*- coding: utf-8 -*-
"""
detect_schema_gaps.py — Schema Gap Reporting (Task #53)
ponytail: 掃描 Task 快照中自然語言欄位（description, algorithm）
是否偷偷夾帶應該放在結構化欄位的詞彙（例如 timeout, retry, env）。
如果有，就印出警告，在 CP-2 (approve) 時提醒人類 reviewer。
"""
import sys
import json
import os

GAP_KEYWORDS = {
    "retry_budget": ["retry", "重試"],
    "environment": ["env", "環境變數", "environment variable"],
    "permission": ["permission", "auth", "權限", "認證"],
    "idempotency": ["idempotent", "冪等", "side effect", "副作用"],
    "timeout": ["timeout", "超時"]
}

def detect_gaps(task_data):
    gaps = []
    node = task_data.get("spec", {}).get("target_node", {})

    text_to_scan = node.get("description", "") + "\n" + "\n".join(node.get("algorithm", []))
    text_lower = text_to_scan.lower()

    for category, keywords in GAP_KEYWORDS.items():
        # 如果該分類已經有對應結構化欄位且有值，就不算 gap
        if category in node and node[category]:
            continue

        for kw in keywords:
            if kw in text_lower:
                gaps.append({
                    "category": category,
                    "keyword": kw,
                    "suggestion": f"偵測到自然語言中包含 `{kw}`，建議將此約束移至結構化欄位 `{category}`"
                })
                break # 同一個 category 報一次就好

    return gaps

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "用法: python detect_schema_gaps.py <node_name>"}, ensure_ascii=False))
        sys.exit(1)

    node_name = sys.argv[1]
    task_path = f".agents/tasks/{node_name}.task.json"

    if not os.path.exists(task_path):
        print(json.dumps({"success": False, "error": f"Task 快照不存在: {task_path}"}, ensure_ascii=False))
        sys.exit(1)

    with open(task_path, "r", encoding="utf-8") as f:
        task_data = json.load(f)

    gaps = detect_gaps(task_data)

    result = {
        "success": True,
        "has_gaps": len(gaps) > 0,
        "gaps": gaps
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))
    sys.exit(0 if not gaps else 2) # 返回 2 表示有 warning

if __name__ == "__main__":
    main()
