# -*- coding: utf-8 -*-
import sys
import json
from adad_core import ADADCore

def main():
    if len(sys.argv) < 2:
        print(json.dumps({"error": "請提供變更的節點名稱。用法: python analyze_cascade.py <changed_node_name>"}, ensure_ascii=False))
        sys.exit(1)
        
    target_node = sys.argv[1]
    core = ADADCore()
    
    node = core.get_node(target_node)
    if not node:
        print(json.dumps({"error": f"找不到節點: {target_node}"}, ensure_ascii=False))
        sys.exit(1)
        
    # 執行依賴級聯染色，並獲取所有變為 dirty 的節點
    dirty_nodes = core.analyze_dirty_cascade(target_node)
    
    # 保存對 system_map.yaml 的狀態變更
    core.save()
    
    result = {
        "success": True,
        "changed_node": target_node,
        "dirty_nodes_count": len(dirty_nodes),
        "dirty_nodes": dirty_nodes
    }
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
