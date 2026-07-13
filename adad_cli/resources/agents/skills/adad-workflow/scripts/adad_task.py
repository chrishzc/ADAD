# -*- coding: utf-8 -*-
"""
adad_task.py — Task 快照的生命週期操作：submit / approve / reject。

submit（coding 端可自行呼叫）:
  python adad_task.py submit <node_name> [file_path]
  代表「我做完了，本地檢查都過了，準備給人審查」。會就地重新跑一次
  check_invariants + verify_implementation，兩項都過才允許轉成 submitted，
  不是 Agent 自己說了算。

approve / reject（只能由人類在真正的互動終端機執行）:
  python adad_task.py approve <node_name> <task_id 後6碼> --reviewer "姓名"
  python adad_task.py reject  <node_name> "<駁回原因>" --reviewer "姓名"

  這兩個指令一開始就會檢查 sys.stdin.isatty()——如果不是真正的互動終端機
  （例如 Agent 透過工具呼叫、或用管線餵資料進來），直接拒絕執行並印出
  明確訊息，不會嘗試用 input() 去等一個可能永遠不會出現的輸入而卡住。
  這是刻意設計成「Agent 沒辦法透過工具呼叫自我核准」的關卡，需要人類
  自己在自己的終端機視窗、或 IDE 內建的終端機（不是聊天視窗）親自執行。

isolate:
  python adad_task.py isolate <node_name> [artifact_type]
  建立或清理一個獨立隔離的工作目錄（預設在 .agents/workspaces/<node>），
  只掛載該階段需要的白名單檔案，防止 Agent 跨邊界修改或讀取未授權的原始碼。
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

    if res.get("success"):
        # Task #53: 偵測 Schema 缺口並給出警告
        import subprocess
        import os
        script_dir = os.path.dirname(os.path.abspath(__file__))
        gap_script = os.path.join(script_dir, "detect_schema_gaps.py")
        gap_res = subprocess.run([sys.executable, gap_script, node_name], capture_output=True, text=True)
        if gap_res.returncode == 2:
            try:
                gap_data = json.loads(gap_res.stdout)
                res["warnings"] = gap_data.get("gaps", [])
            except:
                pass

    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def cmd_approve(args):
    if len(args) != 4 or args[2] != "--reviewer":
        print(json.dumps({"success": False, "error": "用法: python adad_task.py approve <node_name> <task_id後6碼> --reviewer <姓名>"}, ensure_ascii=False))
        sys.exit(1)
    _require_human_tty("核准任務（approve）")
    node_name, confirm_suffix, reviewer = args[0], args[1], args[3]
    core = ADADCore()
    res = core.task_approve(node_name, confirm_suffix, reviewer)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def cmd_reject(args):
    if len(args) != 4 or args[2] != "--reviewer":
        print(json.dumps({"success": False, "error": "用法: python adad_task.py reject <node_name> \"<駁回原因>\" --reviewer <姓名>"}, ensure_ascii=False))
        sys.exit(1)
    _require_human_tty("駁回任務（reject）")
    node_name, reason, reviewer = args[0], args[1], args[3]
    core = ADADCore()
    res = core.task_reject(node_name, reason, reviewer)
    print(json.dumps(res, ensure_ascii=False, indent=2))
    sys.exit(0 if res.get("success") else 1)


def cmd_isolate(args):
    if len(args) < 1:
        print(json.dumps({"success": False, "error": "用法: python adad_task.py isolate <node_name> [artifact_type]"}, ensure_ascii=False))
        sys.exit(1)
    import subprocess
    import os
    node_name = args[0]
    artifact_type = args[1] if len(args) > 1 else "coding"
    script_dir = os.path.dirname(os.path.abspath(__file__))
    iso_script = os.path.join(script_dir, "prepare_isolation.py")
    res = subprocess.run([sys.executable, iso_script, node_name, artifact_type])
    sys.exit(res.returncode)


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in ("submit", "approve", "reject", "isolate"):
        print(json.dumps({
            "success": False,
            "error": "用法: python adad_task.py <submit|approve|reject|isolate> <node_name> [...]"
        }, ensure_ascii=False))
        sys.exit(1)

    sub, rest = sys.argv[1], sys.argv[2:]
    if sub == "submit":
        cmd_submit(rest)
    elif sub == "approve":
        cmd_approve(rest)
    elif sub == "reject":
        cmd_reject(rest)
    elif sub == "isolate":
        cmd_isolate(rest)


if __name__ == "__main__":
    main()
