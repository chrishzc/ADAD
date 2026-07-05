# -*- coding: utf-8 -*-
import sys
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "請提供節點名稱。用法: python read_context.py <node_name>"}, ensure_ascii=False))
        sys.exit(1)
        
    node_name = sys.argv[1]
    core = ADADCore()
    ctx = core.read_context(node_name)
    
    if "error" in ctx:
        print(json.dumps(ctx, ensure_ascii=False, indent=2))
        sys.exit(1)
        
    print(json.dumps(ctx, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
