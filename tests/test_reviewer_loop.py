import sys
import json
import pytest
from pathlib import Path
from conftest import run_script, write_yaml


def _setup_submitted_task(project_dir, base_modules, node_name="sample_tool"):
    base_modules["modules"][node_name]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    # 1. 產生 Task
    run_script("generate_task.py", [node_name], cwd=project_dir)

    # 2. 建立實體檔案並 submit
    src_file = project_dir / f"{node_name}.py"
    src_file.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    run_script("adad_task.py", ["submit", node_name], cwd=project_dir)

    return project_dir / ".agents" / "tasks" / f"{node_name}.task.json"


# --- 測試 1: adad_loop_runner.py 無狀態調度 ---

def test_loop_runner_dispatches_mechanical_review(project_dir, base_modules):
    task_file = _setup_submitted_task(project_dir, base_modules)
    code, _, out, err = run_script("adad_loop_runner.py", ["sample_tool"], cwd=project_dir)
    assert code == 0
    assert "mechanical_review_completed" in out or "in_progress" in out


# --- 測試 2: task_return_to_planning 狀態退回與 History 壓縮 ---

def test_task_return_to_planning_resets_status(project_dir, base_modules):
    task_file = _setup_submitted_task(project_dir, base_modules)

    code, _, out, err = run_script(
        "adad_task.py",
        ["return-to-planning", "sample_tool", "Signature mismatch on line 10"],
        cwd=project_dir,
    )
    assert code == 0, f"got code {code}, out={out}, err={err}"
    assert '"status": "assigned"' in out

    with open(task_file, "r", encoding="utf-8") as f:
        data = json.load(f)
    assert data["status"] == "assigned"
    assert len(data.get("history", [])) > 0


# --- 測試 3: task_auto_certify 憑證審核與白名單重跑 ---

def test_task_auto_certify_rejects_code_reasoning_only(project_dir, base_modules):
    task_file = _setup_submitted_task(project_dir, base_modules)

    receipt = {
        "claim": "Test claim",
        "verification_type": "code_reasoning_only",
        "reproduction_steps": ["step 1"],
    }
    code, _, out, err = run_script(
        "adad_task.py",
        ["auto-certify", "sample_tool", json.dumps(receipt)],
        cwd=project_dir,
    )
    assert code == 1, f"got code {code}, out={out}, err={err}"
    assert "code_reasoning_only" in out or "code_reasoning_only" in err or "強制降級" in out or "強制降級" in err


def test_task_auto_certify_success_on_automated_test(project_dir, base_modules):
    task_file = _setup_submitted_task(project_dir, base_modules)

    with open(task_file, "r", encoding="utf-8") as f:
        task_data = json.load(f)
    verifications = task_data.get("spec", {}).get("verification", [])

    # 抓取第一項白名單 command
    valid_cmd = None
    for item in verifications:
        if isinstance(item, dict):
            if "command" in item and isinstance(item["command"], dict):
                valid_cmd = item["command"]
                break
            elif "argv" in item:
                valid_cmd = item
                break
    if not valid_cmd:
        valid_cmd = {"argv": [sys.executable, "--version"], "cwd": "."}
        task_data["spec"]["verification"] = [{"command": valid_cmd}]
        with open(task_file, "w", encoding="utf-8") as f:
            json.dump(task_data, f, ensure_ascii=False, indent=2)

    # 將 valid_cmd 同步寫回或取用 exact 存在於 spec.verification 的 command
    receipt = {
        "claim": "Test claim",
        "verification_type": "automated_test",
        "reproduction_steps": ["step 1"],
        "automated_evidence": {
            "test_file": "tests/test_sample.py",
            "run_command": valid_cmd,
            "result": "pass",
        },
    }
    code, _, out, err = run_script(
        "adad_task.py",
        ["auto-certify", "sample_tool", json.dumps(receipt)],
        cwd=project_dir,
    )
    assert code == 0, f"got code {code}, out={out}, err={err}"
    assert '"status": "approved"' in out
    assert '"reviewer": "auto-certified"' in out


# --- 測試 4: PreToolUse Gate L2-SPEC-BOUND 範圍防護 ---

def test_gate_blocks_unauthorized_spec_extension(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    task_file = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    task_file.parent.mkdir(parents=True, exist_ok=True)
    task_file.write_text("{}", encoding="utf-8")

    payload = json.dumps({
        "tool_name": "Write",
        "tool_input": {
            "file_path": str(task_file),
            "content": '{"spec": {"change_input_schema": true}}',
        },
        "cwd": str(project_dir),
    })

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=payload,
    )
    assert code == 2
    assert "L2-SPEC-BOUND" in err
