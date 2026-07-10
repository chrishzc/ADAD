# -*- coding: utf-8 -*-
"""
adad_task.py — Task 快照的生命週期操作：submit / approve / reject。

submit（coding 端可自行呼叫）:
  python adad_task.py submit <node_name> [file_path]
  代表「我做完了，本地檢查都過了，準備給人審查」。會就地重新跑一次
  check_invariants + verify_implementation，兩項都過才允許轉成 submitted，
  不是 Agent 自己說了算。

approve / reject（只能由人類在真正的互動終端機執行）:
  python adad_task.py approve <node_name> <task_id 後6碼>
  python adad_task.py reject  <node_name> "<駁回原因>"

  這兩個指令一開始就會檢查 sys.stdin.isatty()——如果不是真正的互動終端機
  （例如 Agent 透過工具呼叫、或用管線餵資料進來），直接拒絕執行並印出
  明確訊息，不會嘗試用 input() 去等一個可能永遠不會出現的輸入而卡住。
  這是刻意設計成「Agent 沒辦法透過工具呼叫自我核准」的關卡，需要人類
  自己在自己的終端機視窗、或 IDE 內建的終端機（不是聊天視窗）親自執行。
"""
import sys
import json
from adad_core import ADADCore


def _require_human_tty(action_desc):
    """approve/reject 共用的守門：不是互動終端機一律拒絕，不嘗試等待輸入。"""
    if not sys.stdin.isatty():
        print(json.dumps({
            "success": False,
            "error": (
                f"[BLOCKED] {action_desc} 必須由人類在真正的互動終端機親自執行，"
                "不接受透過工具呼叫或非互動方式（stdin 不是 tty）觸發。"
                "請在你自己的終端機視窗（不是 Agent 的工具呼叫）手動執行這個指令。"
            )
        }, ensure_ascii=False, indent=2))
        sys.exit(1)


def cmd_submit(args):
    if len(args) < 1:
        print(json.dumps({"success": False, "error": "用法: python adad_task.py submit <node_name> [file_path]"}, ensure_ascii=False))
        sys.exit(1)
    node_name = args[0]
    file_path = args[1] if len(args) > 1 else None
    core = ADADCore()
    res = core.task_submit(node_name, file_path)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def cmd_approve(args):
    if len(args) < 2:
        print(json.dumps({"success": False, "error": "用法: python adad_task.py approve <node_name> <task_id後6碼>"}, ensure_ascii=False))
        sys.exit(1)
    _require_human_tty("核准任務（approve）")
    node_name, confirm_suffix = args[0], args[1]
    core = ADADCore()
    res = core.task_approve(node_name, confirm_suffix)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def cmd_reject(args):
    if len(args) < 2:
        print(json.dumps({"success": False, "error": "用法: python adad_task.py reject <node_name> \"<駁回原因>\""}, ensure_ascii=False))
        sys.exit(1)
    _require_human_tty("駁回任務（reject）")
    node_name, reason = args[0], args[1]
    core = ADADCore()
    res = core.task_reject(node_name, reason)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "approve", "reject"):
        print(json.dumps({
            "success": False,
            "error": "用法: python adad_task.py <submit|approve|reject> <node_name> [...]"
        }, ensure_ascii=False))
        sys.exit(1)

    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "submit":
        cmd_submit(rest)
    elif sub == "approve":
        cmd_approve(rest)
    elif sub == "reject":
        cmd_reject(rest)


if __name__ == "__main__":
    main()
