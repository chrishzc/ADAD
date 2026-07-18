# -*- coding: utf-8 -*-
import sys
import json
import argparse
from adad_core import ADADCore

def main():
    parser = argparse.ArgumentParser(description="執行 ADAD Rule of Two 邊界檢查")
    parser.add_argument("positional", nargs="*", help=argparse.SUPPRESS)
    parser.add_argument("--file", dest="proposal_file", help="包含提議節點的 UTF-8 JSON 檔案")
    args = parser.parse_args()

    if args.positional:
        print(json.dumps({"error": "Positional arguments are disabled. 請使用 --file 或 stdin 傳遞 JSON，避免 shell quoting 破壞內容。"}, ensure_ascii=False))
        sys.exit(1)

    if args.proposal_file:
        try:
            with open(args.proposal_file, "r", encoding="utf-8", errors="strict") as f:
                raw_proposal = f.read()
        except Exception as e:
            print(json.dumps({"error": f"JSON 檔案讀取失敗: {e}"}, ensure_ascii=False))
            sys.exit(1)
    else:
        if sys.stdin.isatty():
            print(json.dumps({"error": "請透過 --file 或 stdin 提供提議節點 JSON。"}, ensure_ascii=False))
            sys.exit(1)
        raw_proposal = sys.stdin.read()
        if not raw_proposal.strip():
            print(json.dumps({"error": "stdin 未提供 JSON 內容。"}, ensure_ascii=False))
            sys.exit(1)

    assert isinstance(raw_proposal, str), "提議節點輸入必須是文字"
    try:
        data = json.loads(raw_proposal)
    except Exception as e:
        print(json.dumps({"error": f"JSON 解析失敗: {e}"}, ensure_ascii=False))
        sys.exit(1)

    if not isinstance(data, dict):
        print(json.dumps({"error": "提議節點的 JSON 必須解析為物件（dict），而非陣列或純值。"}, ensure_ascii=False))
        sys.exit(1)

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
