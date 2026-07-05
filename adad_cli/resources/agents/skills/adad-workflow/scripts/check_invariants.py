# -*- coding: utf-8 -*-
import sys
import json
import os
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({
            "success": False,
            "error": "請提供節點名稱。用法: python check_invariants.py <node_name> [file_path]"
        }, ensure_ascii=False))
        sys.exit(1)
        
    node_name = sys.argv[1]
    file_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    core = ADADCore()
    res = core.check_invariants(node_name, file_path)
    
    # 輸出結果
    print(json.dumps(res, ensure_ascii=False, indent=2))
    
    if not res.get("success"):
        sys.exit(1)
    else:
        sys.exit(0)

if __name__ == "__main__":
    main()
