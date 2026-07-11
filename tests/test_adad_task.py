# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml


def _generate(project_dir):
    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    return data


def test_submit_without_task_errors(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False


def test_submit_succeeds_when_checks_pass(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    assert isinstance(x, int)\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    _generate(project_dir)
    code, data, out, err = run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert data["status"] == "submitted"


def test_submit_blocked_when_invariants_fail(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("import os\ndef sample_tool(x):\n    return os.getpid()\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os]"]
    write_yaml(project_dir, base_modules)

    _generate(project_dir)
    code, data, out, err = run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert "Invariants" in data["error"]


def test_approve_rejected_without_human_tty(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    task = _generate(project_dir)
    run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)

    suffix = task["task_id"][-6:]
    # 測試環境用 subprocess 呼叫，stdin 一定不是互動終端機，這正是要驗證的行為：
    # Agent（或任何非互動呼叫）不能透過這個管道自我核准。
    code, data, out, err = run_script(
        "adad_task.py", ["approve", "sample_tool", suffix], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    assert "[BLOCKED]" in data["error"]
    assert "互動終端機" in data["error"]


def test_reject_rejected_without_human_tty(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    _generate(project_dir)
    run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)

    code, data, out, err = run_script(
        "adad_task.py", ["reject", "sample_tool", "理由"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    assert "[BLOCKED]" in data["error"]


def test_unknown_subcommand_errors(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("adad_task.py", ["frobnicate", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
