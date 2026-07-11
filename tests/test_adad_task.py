# -*- coding: utf-8 -*-
import sys

from conftest import run_script, write_yaml, read_yaml, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))
from adad_core import ADADCore


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
        "adad_task.py", ["approve", "sample_tool", suffix, "--reviewer", "Chris"], cwd=project_dir
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
        "adad_task.py", ["reject", "sample_tool", "理由", "--reviewer", "Chris"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    assert "[BLOCKED]" in data["error"]


def test_approval_writes_auditable_checkpoint(project_dir, base_modules):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert generated["success"] is True
    assert core.task_submit("sample_tool")["success"] is True

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    assert result["success"] is True
    audit_path = project_dir / result["checkpoint"]["path"]
    assert audit_path.exists()

    import yaml
    audit = yaml.safe_load(audit_path.read_text(encoding="utf-8"))["checkpoint_payload"]
    assert audit["status"] == "approved"
    assert audit["decision"]["reviewer"] == "Chris"
    assert audit["target"]["task_id"] == generated["task_id"]
    assert core.load_task("sample_tool")["history"][-1]["checkpoint_id"] == audit["id"]
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "validated"


def test_audit_failure_rolls_back_approval(project_dir, base_modules, monkeypatch):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    monkeypatch.setattr(core, "_write_checkpoint_audit", lambda *args: (_ for _ in ()).throw(OSError("disk full")))

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    assert result["success"] is False
    assert core.load_task("sample_tool")["status"] == "submitted"
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "planned"


def test_unknown_subcommand_errors(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("adad_task.py", ["frobnicate", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
