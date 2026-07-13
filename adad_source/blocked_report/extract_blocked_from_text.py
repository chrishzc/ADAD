# -*- coding: utf-8 -*-
"""
extract_blocked_from_text.py — 文字 fallback 解析器
ponytail: 從 Agent 的非結構化輸出文字中，擷取被 markdown code block 包住的 blocked report JSON。
"""
import sys
import re
import json
import os

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "用法: python extract_blocked_from_text.py <text_file>"}, ensure_ascii=False))
        sys.exit(1)
        
    text_file = sys.argv[1]
    if not os.path.exists(text_file):
        print(json.dumps({"success": False, "error": f"檔案不存在: {text_file}"}, ensure_ascii=False))
        sys.exit(1)
        
    with open(text_file, "r", encoding="utf-8") as f:
        content = f.read()
        
    # 尋找 JSON block
    match = re.search(r'```json\s*(.*?)\s*```', content, re.DOTALL)
    if not match:
        print(json.dumps({"success": False, "error": "找不到 JSON 區塊"}, ensure_ascii=False))
        sys.exit(1)
        
    try:
        report = json.loads(match.group(1))
    except json.JSONDecodeError:
        print(json.dumps({"success": False, "error": "JSON 格式錯誤"}, ensure_ascii=False))
        sys.exit(1)
        
    node_name = report.get("node_name")
    reason = report.get("reason")
    
    if not node_name or not reason:
        print(json.dumps({"success": False, "error": "缺少 node_name 或 reason 欄位"}, ensure_ascii=False))
        sys.exit(1)
        
    # 執行 block
    script_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "agents", "skills", "adad-workflow", "scripts"))
    sys.path.insert(0, script_dir)
    try:
        from adad_core import ADADCore
        core = ADADCore()
        res = core.task_block(node_name, reason)
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(0 if res.get("success") else 1)
    except Exception as e:
        print(json.dumps({"success": False, "error": str(e)}, ensure_ascii=False))
        sys.exit(1)

if __name__ == "__main__":
    main()
