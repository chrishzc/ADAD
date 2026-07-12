# -*- coding: utf-8 -*-
"""
generate_task.py — 從 system_map.yaml 匯出一份 Task 快照給 coding 端讀取。

Task ≠ Module：Module 是架構長期存在的事實，Task 是針對某次施工正式核發的
一份凍結指令（含 source_hash，可偵測架構是否在執行期間被更動過）。

用法:
  python generate_task.py <node_name> [--force]

--force 用於作廢並重新核發一份已存在但尚未結案（assigned/in_progress/submitted）
的任務，正常情況不應該需要用到，用到通常代表上一輪任務被放棄了。
"""
import sys
import json
from adad_core import ADADCore


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    force = "--force" in sys.argv[1:]

    if len(args) < 1:
        print(json.dumps({
            "success": False,
            "error": "請提供節點名稱。用法: python generate_task.py <node_name> [--force]"
        }, ensure_ascii=False))
        sys.exit(1)

    node_name = args[0]
    core = ADADCore()
    res = core.generate_task(node_name, force=force)

    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


if __name__ == "__main__":
    main()
