# -*- coding: utf-8 -*-
import sys
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "請提供提議節點的 JSON 字串。用法: python check_normalization.py '<json_string>'"}, ensure_ascii=False))
        sys.exit(1)
        
    try:
        data = json.loads(sys.argv[1])
    except Exception as e:
        print(json.dumps({"error": f"JSON 解析失敗: {e}"}, ensure_ascii=False))
        sys.exit(1)
        
    name = data.get("name")
    proposed_input = data.get("input", {})
    proposed_output = data.get("output", {})
    
    if not name:
        print(json.dumps({"error": "JSON 必須包含 'name' 欄位。"}, ensure_ascii=False))
        sys.exit(1)
        
    core = ADADCore()
    result = core.evaluate_normalization(name, proposed_input, proposed_output)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
