# -*- coding: utf-8 -*-
import sys
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 3:
        print(json.dumps({"error": "請提供節點名稱與下一個狀態。用法: python transit_state.py <node_name> <next_state>"}, ensure_ascii=False))
        sys.exit(1)
        
    node_name = sys.argv[1]
    next_state = sys.argv[2]
    
    core = ADADCore()
    
    # 執行狀態轉移校驗與更新
    res = core.transit_state(node_name, next_state)
    
    if not res.get("success"):
        print(json.dumps(res, ensure_ascii=False, indent=2))
        sys.exit(1)
        
    # 保存狀態變更至 system_map.yaml
    core.save()
    
    print(json.dumps({
        "success": True,
        "node": node_name,
        "from_state": res.get("from"),
        "to_state": res.get("to")
    }, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
