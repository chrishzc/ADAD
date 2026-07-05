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

    # ponytail-fix: system_map.md 宣告本模組的 Verification 為 must_have_assertions，
    # 但實作裡原本一個 assert 都沒有——導致全新專案第一次 commit 就會被自己的
    # pre-commit hook 卡住。這裡補一個真正有意義的自檢斷言：合法 JSON 不代表一定是
    # 物件（例如可能是陣列、字串、數字），若不是 dict，後面的 data.get(...) 會
    # 得到不明確的 AttributeError；用 assert 把這個前提條件明確表達出來。
    assert isinstance(data, dict), "提議節點的 JSON 必須解析為物件（dict），而非陣列或純值"

    name = data.get("name")
    proposed_input = data.get("input", {})
    proposed_output = data.get("output", {})
    # ponytail: Rule of Two 改版後改看 Description 加權相似度，
    # 沒有 description 欄位時只剩規則 1（介面完全一致）在運作，不會報錯。
    proposed_description = data.get("description", "")
    
    if not name:
        print(json.dumps({"error": "JSON 必須包含 'name' 欄位。"}, ensure_ascii=False))
        sys.exit(1)
        
    core = ADADCore()
    result = core.evaluate_normalization(name, proposed_input, proposed_output, proposed_description)
    
    print(json.dumps(result, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
