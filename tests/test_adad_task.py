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
    assert data["implementation_hash"] == ADADCore._file_hash(src)
    saved = ADADCore(project_dir / "system_map.yaml", check_validity=False).load_task("sample_tool")
    assert saved["implementation_hash"] == data["implementation_hash"]


def test_submit_uses_physical_file_for_function_level_source(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["source"] = "sample_tool.py::sample_tool"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_calls: [eval]"]
    write_yaml(project_dir, base_modules)

    _generate(project_dir)
    code, data, out, err = run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)

    assert code == 0, err
    assert data["success"] is True
    assert data["implementation_hash"] == ADADCore._file_hash(src)


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
    approved_task = core.load_task("sample_tool")
    assert approved_task["approved_implementation_hash"] == approved_task["implementation_hash"]
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "validated"


def test_commit_gate_allows_only_approved_matching_hash(project_dir, base_modules):
    source = project_dir / "sample_tool.py"
    source.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    submitted = core.task_submit("sample_tool")
    assert submitted["success"] is True
    assert core.check_task_gate(
        "sample_tool.py", operation="commit", candidate_hash=submitted["implementation_hash"]
    )["allow"] is False

    assert core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")["success"] is True
    assert core.check_task_gate(
        "sample_tool.py", operation="commit", candidate_hash=submitted["implementation_hash"]
    )["allow"] is True
    assert core.check_task_gate(
        "sample_tool.py", operation="commit", candidate_hash="0" * 64
    )["allow"] is False


def test_commit_gate_fails_closed_for_legacy_approved_task(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    task["status"] = "approved"
    core._save_task("sample_tool", task)

    gate = core.check_task_gate("sample_tool.py", operation="commit", candidate_hash="0" * 64)
    assert gate["allow"] is False
    assert "approved_implementation_hash" in gate["reason"]


def test_source_lock_blocks_parallel_tasks_and_releases_after_approval(project_dir, base_modules):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n\ndef other_tool(x):\n    return x\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "sample_tool.py::sample_tool"
    other = dict(base_modules["modules"]["sample_tool"])
    other["source"] = "sample_tool.py::other_tool"
    base_modules["modules"]["other_tool"] = other
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)

    first = core.generate_task("sample_tool")
    assert first["success"] is True
    conflict = core.generate_task("other_tool")
    assert conflict["success"] is False
    assert conflict["error"].startswith("[SOURCE LOCK]")
    assert conflict["conflict"]["node_name"] == "sample_tool"

    assert core.task_submit("sample_tool")["success"] is True
    assert core.task_approve("sample_tool", first["task_id"][-6:], "Chris")["success"] is True
    assert not list((project_dir / ".agents" / "tasks" / ".source_locks").glob("*.lock.json"))
    assert core.generate_task("other_tool")["success"] is True


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


def test_rejection_preserves_diff_and_records_hashes(project_dir, base_modules):
    source = project_dir / "sample_tool.py"
    source.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    write_yaml(project_dir, base_modules)
    core = ADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    source.write_text("def sample_tool(x):\n    return x + 1\n", encoding="utf-8")

    result = core.task_reject("sample_tool", "請修正回傳值", "Chris")
    assert result["success"] is True
    assert source.read_text(encoding="utf-8").endswith("return x + 1\n")
    rollback = core.load_task("sample_tool")["rollback"]
    assert rollback["strategy"] == "preserve_diff"
    assert rollback["source_changed_since_issue"] is True


def test_unknown_subcommand_errors(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("adad_task.py", ["frobnicate", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
