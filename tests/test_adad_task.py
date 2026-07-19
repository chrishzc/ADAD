

# -*- coding: utf-8 -*-
import pytest

pytestmark = pytest.mark.regression_backlog

import sys
import builtins
import json
import importlib.util
import subprocess
from pathlib import Path


from conftest import run_script, write_yaml, read_yaml, SCRIPTS_DIR

sys.path.insert(0, str(SCRIPTS_DIR))
from adad_core import ADADCore

CANONICAL_CORE_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_core.py"
)
_canonical_spec = importlib.util.spec_from_file_location(
    "canonical_adad_core_task78", CANONICAL_CORE_PATH
)
_canonical_module = importlib.util.module_from_spec(_canonical_spec)
_canonical_spec.loader.exec_module(_canonical_module)
CanonicalADADCore = _canonical_module.ADADCore

CANONICAL_TASK_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_task.py"
)


def _generate(project_dir):
    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    return data


def _run_canonical_locks(monkeypatch, capsys, args, core_type):
    spec = importlib.util.spec_from_file_location(
        "canonical_adad_task_cli", CANONICAL_TASK_PATH
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    monkeypatch.setattr(module, "ADADCore", core_type)
    monkeypatch.setattr(module.sys, "argv", ["adad_task.py", "locks", *args])
    try:
        module.main()
    except SystemExit as exc:
        exit_code = exc.code
    else:
        raise AssertionError("locks command did not exit")
    return exit_code, json.loads(capsys.readouterr().out)


@pytest.mark.parametrize(
    ("pytest_args", "expected_disabled_tokens"),
    [
        ([], ["-p", "no:cacheprovider"]),
        (["-p", "no:cacheprovider"], ["-p", "no:cacheprovider"]),
        (["-p=no:cacheprovider"], ["-p=no:cacheprovider"]),
        (["-pno:cacheprovider"], ["-pno:cacheprovider"]),
    ],
)
def test_verification_runner_injects_pytest_cacheprovider_once(
    tmp_path, monkeypatch, pytest_args, expected_disabled_tokens
):
    core = CanonicalADADCore(tmp_path / "system_map.yaml", check_validity=False)
    captured = []

    class Completed:
        returncode = 0

        def communicate(self, timeout):
            return b"", b""

    def fake_popen(argv, **kwargs):
        captured.append(argv)
        return Completed()

    monkeypatch.setattr(_canonical_module.subprocess, "Popen", fake_popen)
    result = core._run_verification_command(
        {
            "argv": [sys.executable, "-m", "pytest", *pytest_args],
            "cwd": "project",
            "expect_exit": 0,
        },
        str(tmp_path / "workspace"),
        {"project": str(tmp_path)},
        0,
    )

    assert result["passed"] is True
    assert captured[0].count("no:cacheprovider") + captured[0].count(
        "-p=no:cacheprovider"
    ) + captured[0].count("-pno:cacheprovider") == 1
    assert [arg for arg in captured[0] if arg in expected_disabled_tokens] == expected_disabled_tokens


def test_project_verification_command_avoids_disposable_workspace(tmp_path, monkeypatch):
    source = tmp_path / "sample_tool.py"
    source.write_text("def sample_tool():\n    return True\n", encoding="utf-8")
    core = CanonicalADADCore(tmp_path / "system_map.yaml", check_validity=False)
    core.data = {
        "modules": {
            "sample_tool": {
                "source": str(source),
                "verification": [
                    {
                        "command": {
                            "argv": [sys.executable, "-c", "pass"],
                            "cwd": "project",
                            "expect_exit": 0,
                        }
                    }
                ],
            }
        }
    }
    captured = []

    def fake_command(command, workspace, placeholders, step_index):
        captured.append((workspace, placeholders["workspace"], step_index))
        return {"step_index": step_index, "passed": True}

    monkeypatch.setattr(core, "_run_verification_command", fake_command)
    monkeypatch.setattr(
        core,
        "_run_integration_verification",
        lambda *args, **kwargs: pytest.fail("project command must not create workspace"),
    )

    result = core.verify_implementation("sample_tool", str(source))

    assert result["success"] is True
    assert captured == [(str(tmp_path), str(tmp_path), 0)]


def test_verification_timeout_terminates_the_process_group(tmp_path, monkeypatch):
    core = CanonicalADADCore(tmp_path / "system_map.yaml", check_validity=False)
    captured = {}

    class TimedOutProcess:
        pid = 4321
        returncode = None

        def __init__(self):
            self.communicate_calls = 0

        def communicate(self, timeout):
            self.communicate_calls += 1
            if self.communicate_calls == 1:
                raise subprocess.TimeoutExpired(
                    ["verification-tool"], timeout, output=b"before", stderr=b"before-error"
                )
            return b"after", b"after-error"

    process = TimedOutProcess()

    def fake_popen(argv, **kwargs):
        captured["argv"] = argv
        captured["kwargs"] = kwargs
        return process

    def fake_run(argv, **kwargs):
        captured["termination_run"] = (argv, kwargs)

    def fake_killpg(pgid, sig):
        captured["killpg"] = (pgid, sig)

    monkeypatch.setattr(_canonical_module.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(_canonical_module.subprocess, "run", fake_run)

    import os
    if hasattr(os, "killpg"):
        monkeypatch.setattr(os, "killpg", fake_killpg)
    else:
        monkeypatch.setattr(_canonical_module.os, "killpg", fake_killpg, raising=False)

    result = core._run_verification_command(
        {"argv": ["verification-tool"], "cwd": "project", "expect_exit": 0, "timeout": 1},
        str(tmp_path / "workspace"),
        {"project": str(tmp_path)},
        0,
    )

    assert result["passed"] is False
    assert result["returncode"] is None
    assert result["stdout"] == "after"
    assert result["stderr"] == "after-error"

    if os.name == "nt":
        assert captured["kwargs"]["creationflags"] == _canonical_module.subprocess.CREATE_NEW_PROCESS_GROUP
        assert captured["termination_run"][0] == ["taskkill", "/PID", "4321", "/T", "/F"]
    else:
        assert captured["kwargs"]["preexec_fn"] == os.setsid
        assert captured["killpg"] == (4321, _canonical_module.signal.SIGKILL)

    assert process.communicate_calls == 2


def test_locks_cli_audit_is_read_only_thin_adapter(monkeypatch, capsys):
    calls = []
    expected = {
        "success": True,
        "mode": "audit",
        "categories": {"active": [{"node_name": "sample_tool"}]},
        "mutation_blocked": False,
    }

    class FakeCore:
        def audit_source_locks(self):
            calls.append(("audit", None))
            return expected

        def reconcile_source_locks(self, mode):
            calls.append(("reconcile", mode))
            raise AssertionError("audit must not call reconcile")

    code, data = _run_canonical_locks(monkeypatch, capsys, [], FakeCore)

    assert code == 0
    assert data == expected
    assert calls == [("audit", None)]


def test_locks_cli_prune_delegates_without_reimplementing_policy(monkeypatch, capsys):
    calls = []
    expected = {
        "success": False,
        "mode": "prune",
        "mutation_blocked": True,
        "preflight": [{"result": {"uncertain": True}}],
        "mutations": [],
        "partial_recovery": {"manual_action_required": True},
    }

    class FakeCore:
        def audit_source_locks(self):
            raise AssertionError("prune must delegate through reconcile")

        def reconcile_source_locks(self, mode):
            calls.append(mode)
            return expected

    code, data = _run_canonical_locks(monkeypatch, capsys, ["--prune"], FakeCore)

    assert code == 1
    assert data == expected
    assert calls == ["prune"]


def test_locks_cli_reconcile_delegates_and_preserves_nested_result(
    monkeypatch, capsys
):
    calls = []
    expected = {
        "success": True,
        "mode": "reconcile",
        "audit": {"categories": {"invalid": [{"reason": "missing_lock"}]}},
        "preflight": [{"candidate": {"node_name": "sample_tool"}}],
        "mutations": [{"action": "reconciled"}],
    }

    class FakeCore:
        def audit_source_locks(self):
            raise AssertionError("reconcile must delegate through reconcile")

        def reconcile_source_locks(self, mode):
            calls.append(mode)
            return expected

    code, data = _run_canonical_locks(
        monkeypatch, capsys, ["--reconcile"], FakeCore
    )

    assert code == 0
    assert data == expected
    assert calls == ["reconcile"]


def test_locks_cli_rejects_unknown_or_combined_arguments_before_core(
    monkeypatch, capsys
):
    constructed = []

    class FakeCore:
        def __init__(self):
            constructed.append(True)

    for args in (
        ["audit"],
        ["--prune", "--reconcile"],
        ["--force"],
        ["--prune", "extra"],
    ):
        code, data = _run_canonical_locks(monkeypatch, capsys, args, FakeCore)
        assert code == 1
        assert data["success"] is False
        assert "Usage:" in data["error"]

    assert constructed == []


def test_locks_cli_requires_literal_true_for_success_exit(monkeypatch, capsys):
    class FakeCore:
        def audit_source_locks(self):
            return {"success": 1, "mode": "audit"}

    code, data = _run_canonical_locks(monkeypatch, capsys, [], FakeCore)

    assert code == 1
    assert data == {"success": 1, "mode": "audit"}


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
    # Non-interactive environment (no human tty) should block approval.
    code, data, out, err = run_script(
        "adad_task.py", ["approve", "sample_tool", suffix, "--reviewer", "Chris"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    assert "[BLOCKED]" in data["error"]
    assert any(token in data["error"].lower() for token in ("human", "tty", "stdin", "non-interactive"))


def test_reject_rejected_without_human_tty(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    _generate(project_dir)
    run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)

    code, data, out, err = run_script(
        "adad_task.py", ["reject", "sample_tool", "?", "--reviewer", "Chris"], cwd=project_dir
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


def test_task_block_releases_physical_lock_and_preserves_metadata(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    lock_metadata = core.load_task("sample_tool")["source_lock"]

    result = core.task_block("sample_tool", "needs human input")

    assert result["success"] is True
    blocked = core.load_task("sample_tool")
    assert blocked["status"] == "blocked"
    assert blocked["source_lock"] == lock_metadata
    assert blocked["history"][-1]["action"] == "task_blocked"
    assert not (project_dir / core._source_lock_path(lock_metadata["source_path"])).exists()
    assert generated["task_id"] == blocked["task_id"]


def test_task_block_fails_closed_when_lock_release_fails(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_rename = __import__("os").rename

    def deny_lock_rename(source, target):
        if __import__("os").path.abspath(source) == str(lock_path.resolve()):
            raise PermissionError("denied")
        return original_rename(source, target)

    monkeypatch.setattr(_canonical_module.os, "rename", deny_lock_rename)
    result = core.task_block("sample_tool", "blocked")

    assert result["success"] is False
    assert "Quarantine rename failed" in result["error"]
    blocked = core.load_task("sample_tool")
    assert blocked["status"] == "blocked"
    assert blocked["source_lock"] == task["source_lock"]
    assert lock_path.exists()


def test_source_lock_audit_classifies_active_stale_orphan_and_invalid(
    project_dir, base_modules
):
    base_modules["modules"]["stale_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "stale_tool.py",
    }
    base_modules["modules"]["orphan_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "orphan_tool.py",
    }
    base_modules["modules"]["invalid_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "invalid_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)

    assert core.generate_task("sample_tool")["success"] is True
    assert core.generate_task("stale_tool")["success"] is True
    stale = core.load_task("stale_tool")
    stale["status"] = "blocked"
    core._save_task("stale_tool", stale)

    orphan_lock = {
        "source_path": "orphan_tool.py",
        "node_name": "orphan_tool",
        "task_id": "orphan_tool@v1@orphan",
        "acquired_at": "2026-07-16T00:00:00+00:00",
    }
    orphan_path = project_dir / core._source_lock_path("orphan_tool.py")
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_text(json.dumps(orphan_lock), encoding="utf-8")

    assert core.generate_task("invalid_tool")["success"] is True
    invalid = core.load_task("invalid_tool")
    invalid_lock_path = project_dir / core._source_lock_path("invalid_tool.py")
    invalid_payload = json.loads(invalid_lock_path.read_text(encoding="utf-8"))
    invalid_payload["task_id"] = "mismatch"
    invalid_lock_path.write_text(json.dumps(invalid_payload), encoding="utf-8")

    report = core.audit_source_locks()

    assert report["counts"] == {"active": 1, "stale": 1, "orphan": 1, "invalid": 1}
    assert report["categories"]["active"][0]["node_name"] == "sample_tool"
    assert report["categories"]["stale"][0]["node_name"] == "stale_tool"
    assert report["categories"]["orphan"][0]["node_name"] == "orphan_tool"
    assert report["categories"]["invalid"][0]["reason"] == "task_lock_mismatch:task_id"


def test_source_lock_audit_strict_read_lock_is_uncertain_and_blocks_mutation(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_open = builtins.open

    def deny_lock_read(path, mode="r", *args, **kwargs):
        if Path(path).resolve() == lock_path.resolve():
            raise PermissionError("strict-read denied")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(_canonical_module, "open", deny_lock_read, raising=False)

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if item["reason"] == "unreadable_lock"
        and Path(item["canonical_path"]).resolve() == lock_path.resolve()
    )
    assert invalid["uncertain"] is True
    assert invalid["identity"] == invalid["lstat_identity"]
    assert invalid["evidence"]["error"] == "strict-read denied"

    pruned = core.reconcile_source_locks("prune")
    reconciled = core.reconcile_source_locks("reconcile")
    assert pruned["success"] is False and pruned["mutations"] == []
    assert reconciled["success"] is False and reconciled["mutations"] == []


def test_source_lock_audit_invalid_lock_utf8_is_uncertain_and_blocks_mutation(
    project_dir, base_modules
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    lock_payload = lock_path.read_bytes()
    lock_path.write_bytes(lock_payload + b"\xff")
    probe = core._source_lock_identity(lock_path)
    assert probe["success"] is False
    assert probe["uncertain"] is True

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if Path(item["canonical_path"]).resolve() == lock_path.resolve()
        and item["reason"] == "unreadable_lock"
    )
    assert invalid["uncertain"] is True
    assert invalid["payload_digest"] == probe["payload_digest"]
    assert invalid["identity"] == probe["identity"]
    assert invalid["evidence"]["payload_digest"] == probe["payload_digest"]
    assert invalid["evidence"]["raw_hex"] == probe["evidence"]["raw_hex"]


def test_source_lock_audit_malformed_lock_json_is_uncertain_and_blocks_mutation(
    project_dir, base_modules
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    lock_path.write_bytes(b'{"source_path": "sample_tool.py", "node_name": ')
    probe = core._source_lock_identity(lock_path)
    assert probe["success"] is False
    assert probe["uncertain"] is True

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if Path(item["canonical_path"]).resolve() == lock_path.resolve()
        and item["reason"] == "unreadable_lock"
    )
    assert invalid["uncertain"] is True
    assert invalid["payload_digest"] == probe["payload_digest"]
    assert invalid["identity"] == probe["identity"]
    assert invalid["evidence"]["error"] == probe["error"]


def test_source_lock_audit_strict_read_task_snapshot_is_uncertain_and_blocks_mutation(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task_path = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    original_open = builtins.open

    def deny_task_read(path, mode="r", *args, **kwargs):
        if Path(path).resolve() == task_path.resolve():
            raise PermissionError("strict-read denied")
        return original_open(path, mode, *args, **kwargs)

    monkeypatch.setattr(_canonical_module, "open", deny_task_read, raising=False)
    probe = core._source_lock_identity(task_path)
    assert probe["success"] is False
    assert probe["uncertain"] is True

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if Path(item["canonical_path"]).resolve() == task_path.resolve()
        and item["reason"] == "unreadable_task"
    )
    assert invalid["uncertain"] is True
    assert invalid["identity"] == probe["identity"]
    assert invalid["evidence"]["error"] == "strict-read denied"

    pruned = core.reconcile_source_locks("prune")
    reconciled = core.reconcile_source_locks("reconcile")
    assert pruned["success"] is False and pruned["mutations"] == []
    assert reconciled["success"] is False and reconciled["mutations"] == []


def test_source_lock_audit_invalid_task_snapshot_utf8_is_uncertain_and_blocks_mutation(
    project_dir, base_modules
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task_path = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    task_payload = task_path.read_bytes()
    task_path.write_bytes(task_payload + b"\xff")
    probe = core._source_lock_identity(task_path)
    assert probe["success"] is False
    assert probe["uncertain"] is True

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if Path(item["canonical_path"]).resolve() == task_path.resolve()
        and item["reason"] == "unreadable_task"
    )
    assert invalid["uncertain"] is True
    assert invalid["digest"] == probe["payload_digest"]
    assert invalid["identity"] == probe["identity"]
    assert invalid["evidence"]["payload_digest"] == probe["payload_digest"]


def test_source_lock_audit_malformed_task_snapshot_json_is_uncertain_and_blocks_mutation(
    project_dir, base_modules
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task_path = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    task_path.write_text('{"node_name": "sample_tool", "status": "assigned",', encoding="utf-8")
    probe = core._source_lock_identity(task_path)
    assert probe["success"] is False
    assert probe["uncertain"] is True

    audit = core.audit_source_locks()
    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    invalid = next(
        item for item in audit["categories"]["invalid"]
        if Path(item["canonical_path"]).resolve() == task_path.resolve()
        and item["reason"] == "unreadable_task"
    )
    assert invalid["uncertain"] is True
    assert invalid["identity"] == probe["identity"]
    assert invalid["digest"] == probe["payload_digest"]
    assert invalid["evidence"]["error"] == probe["error"]


def test_source_lock_audit_and_reconcile_missing_active_lock_are_idempotent(
    project_dir, base_modules
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    lock_path.unlink()

    audit = core.audit_source_locks()
    assert audit["counts"]["invalid"] == 1
    assert audit["categories"]["invalid"][0]["reason"] == "active_task_missing_lock"

    reconciled = core.reconcile_source_locks("reconcile")
    assert reconciled["success"] is True
    assert [item["action"] for item in reconciled["mutations"]] == ["reconciled"]
    assert json.loads(lock_path.read_text(encoding="utf-8")) == task["source_lock"]
    assert core.load_task("sample_tool") == task

    again = core.reconcile_source_locks("reconcile")
    assert again["success"] is True
    assert again["mutations"] == []


def test_source_lock_prune_removes_only_stale_and_orphan(project_dir, base_modules):
    base_modules["modules"]["stale_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "stale_tool.py",
    }
    base_modules["modules"]["orphan_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "orphan_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    assert core.generate_task("stale_tool")["success"] is True
    stale = core.load_task("stale_tool")
    stale["status"] = "approved"
    core._save_task("stale_tool", stale)
    orphan_lock = {
        "source_path": "orphan_tool.py",
        "node_name": "orphan_tool",
        "task_id": "orphan_tool@v1@orphan",
        "acquired_at": "2026-07-16T00:00:00+00:00",
    }
    orphan_path = project_dir / core._source_lock_path("orphan_tool.py")
    orphan_path.write_text(json.dumps(orphan_lock), encoding="utf-8")

    result = core.reconcile_source_locks("prune")

    assert result["success"] is True
    assert [item["action"] for item in result["mutations"]] == ["pruned", "pruned"]
    assert (project_dir / core._source_lock_path("sample_tool.py")).exists()
    assert not (project_dir / core._source_lock_path("stale_tool.py")).exists()
    assert not orphan_path.exists()
    assert core.load_task("stale_tool") == stale
    assert core.reconcile_source_locks("prune")["mutations"] == []


def test_approval_lock_mismatch_rolls_back_task_map_and_checkpoint(
    project_dir, base_modules
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["task_id"] = "other@v1@task"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")

    assert result["success"] is False
    assert core.load_task("sample_tool")["status"] == "submitted"
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "planned"
    assert list((project_dir / "checkpoints").glob("*approved.yaml")) == []
    assert lock_path.exists()
    recovery = result["transaction_recovery"]
    assert recovery["phase"] == "checkpoint_decision"
    assert recovery["primary_failure"]["type"] == "RuntimeError"
    assert recovery["task_rollback"]["status"] == "restored"
    assert recovery["system_map_rollback"]["status"] == "restored"
    assert recovery["checkpoint_audit_rollback"]["status"] == "removed"
    assert recovery["source_lock_rollback"]["status"] == "canonical_preserved"
    assert recovery["manual_action_required"] is True
    assert "transaction_recovery" not in result["error"]


def test_approval_quarantine_rename_failure_rolls_back(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_rename = _canonical_module.os.rename

    def deny_lock_rename(source, target):
        if __import__("os").path.abspath(source) == str(lock_path.resolve()):
            raise PermissionError("denied")
        return original_rename(source, target)

    monkeypatch.setattr(_canonical_module.os, "rename", deny_lock_rename)
    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")

    assert result["success"] is False
    assert core.load_task("sample_tool")["status"] == "submitted"
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "planned"
    assert list((project_dir / "checkpoints").glob("*approved.yaml")) == []
    assert lock_path.exists()
    recovery = result["transaction_recovery"]
    assert recovery["source_lock_rollback"]["status"] == "canonical_preserved"
    assert recovery["safe_to_retry"] is True
    assert recovery["manual_action_required"] is False


def test_approval_quarantine_delete_failure_keeps_approval_and_evidence(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_remove = _canonical_module.os.remove

    def deny_quarantine_delete(path):
        if ".quarantine-" in str(path):
            raise PermissionError("denied")
        return original_remove(path)

    monkeypatch.setattr(_canonical_module.os, "remove", deny_quarantine_delete)
    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")

    assert result["success"] is True
    assert core.load_task("sample_tool")["status"] == "approved"
    assert read_yaml(project_dir)["modules"]["sample_tool"]["state"] == "validated"
    assert not lock_path.exists()
    action = result["checkpoint"]["source_lock_action"]
    assert "Quarantine cleanup failed" in action["warning"]
    assert Path(action["quarantine_path"]).exists()


def test_approval_audit_failure_returns_fixed_transaction_recovery(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    monkeypatch.setattr(
        core, "_write_checkpoint_audit",
        lambda *args: (_ for _ in ()).throw(OSError("disk full")),
    )

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    recovery = result["transaction_recovery"]

    assert result["success"] is False
    assert recovery["primary_failure"] == {
        "type": "OSError", "message": "disk full",
    }
    assert recovery["task_rollback"]["status"] == "restored"
    assert recovery["system_map_rollback"]["status"] == "restored"
    assert recovery["checkpoint_audit_rollback"]["status"] == "not_created"
    assert recovery["source_lock_rollback"]["status"] == "not_needed"
    assert recovery["safe_to_retry"] is True
    assert recovery["manual_action_required"] is False


def test_approval_rollback_failure_preserves_primary_failure(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["task_id"] = "mismatch"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    original_save_task = core._save_task
    calls = {"count": 0}

    def fail_only_rollback(node_name, task_data):
        calls["count"] += 1
        if calls["count"] == 3:
            raise OSError("rollback disk full")
        return original_save_task(node_name, task_data)

    monkeypatch.setattr(core, "_save_task", fail_only_rollback)
    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    recovery = result["transaction_recovery"]

    assert result["success"] is False
    assert "Physical lock does not match" in recovery["primary_failure"]["message"]
    assert recovery["task_rollback"] == {
        "status": "restore_failed", "error": "rollback disk full",
    }
    assert recovery["manual_action_required"] is True
    assert recovery["safe_to_retry"] is False


def test_approval_checkpoint_cleanup_failure_is_compound_evidence(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["task_id"] = "mismatch"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")
    original_remove = _canonical_module.os.remove

    def deny_checkpoint_cleanup(path):
        if str(path).endswith("-approved.yaml"):
            raise PermissionError("checkpoint cleanup denied")
        return original_remove(path)

    monkeypatch.setattr(_canonical_module.os, "remove", deny_checkpoint_cleanup)
    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    recovery = result["transaction_recovery"]

    assert recovery["checkpoint_audit_rollback"]["status"] == "cleanup_failed"
    assert recovery["checkpoint_audit_rollback"]["error"] == "checkpoint cleanup denied"
    assert recovery["primary_failure"]["message"].startswith(
        "[SOURCE LOCK] Physical lock does not match"
    )
    assert recovery["manual_action_required"] is True


def test_approval_restore_conflict_requires_manual_action(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    monkeypatch.setattr(core, "_release_source_lock", lambda task_data: {
        "success": False,
        "result": "identity_mismatch",
        "error": "restore conflict",
        "quarantine_path": "lock.quarantine-test",
        "restore": {"attempted": True, "success": False, "error": "occupied"},
    })

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")
    source_recovery = result["transaction_recovery"]["source_lock_rollback"]

    assert source_recovery["status"] == "restore_failed"
    assert source_recovery["error"] == "occupied"
    assert result["transaction_recovery"]["manual_action_required"] is True
    assert result["transaction_recovery"]["safe_to_retry"] is False


def test_task_approve_preserves_generic_runtime_error_compatibility(
    project_dir, base_modules, monkeypatch
):
    (project_dir / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n", encoding="utf-8"
    )
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    generated = core.generate_task("sample_tool")
    assert core.task_submit("sample_tool")["success"] is True
    monkeypatch.setattr(
        core, "_commit_checkpoint_decision",
        lambda *args, **kwargs: (_ for _ in ()).throw(RuntimeError("legacy failure")),
    )

    result = core.task_approve("sample_tool", generated["task_id"][-6:], "Chris")

    assert result == {"success": False, "error": "legacy failure"}


def test_audit_directory_uncertainty_blocks_all_mutation(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    lock_dir = (project_dir / ".agents" / "tasks" / ".source_locks").resolve()
    original_scandir = _canonical_module.os.scandir

    def deny_lock_scan(path):
        if Path(path).resolve() == lock_dir:
            raise PermissionError("denied")
        return original_scandir(path)

    monkeypatch.setattr(_canonical_module.os, "scandir", deny_lock_scan)
    audit = core.audit_source_locks()
    pruned = core.reconcile_source_locks("prune")
    reconciled = core.reconcile_source_locks("reconcile")

    assert audit["healthy"] is False
    assert audit["mutation_blocked"] is True
    assert any(
        item["reason"] == "lock_directory_scan_failed"
        for item in audit["categories"]["invalid"]
    )
    assert pruned["success"] is False and pruned["mutations"] == []
    assert reconciled["success"] is False and reconciled["mutations"] == []


def test_prune_delete_failure_preserves_quarantine_and_never_deletes_new_lock(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    task["status"] = "blocked"
    core._save_task("sample_tool", task)
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_remove = _canonical_module.os.remove

    def deny_quarantine_delete(path):
        if ".quarantine-" in str(path):
            raise PermissionError("denied")
        return original_remove(path)

    monkeypatch.setattr(_canonical_module.os, "remove", deny_quarantine_delete)
    first = core.reconcile_source_locks("prune")
    quarantine = Path(first["mutations"][0]["quarantine"]["quarantine_path"])
    new_payload = dict(task["source_lock"])
    new_payload["task_id"] = "new-owner@v1@test"
    lock_path.write_text(json.dumps(new_payload), encoding="utf-8")
    second = core.reconcile_source_locks("prune")

    assert first["success"] is False
    assert first["mutations"][0]["action"] == "quarantined"
    assert quarantine.exists()
    assert lock_path.exists()
    assert json.loads(lock_path.read_text(encoding="utf-8"))["task_id"] == "new-owner@v1@test"
    assert second["mutations"] == []


def test_prune_restores_quarantine_when_active_claim_appears(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    task["status"] = "blocked"
    core._save_task("sample_tool", task)
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    original_scan = core._scan_source_lock_state
    calls = {"count": 0}

    def activate_after_quarantine():
        calls["count"] += 1
        # audit scan, candidate revalidation scan, then the post-quarantine
        # active-claim scan. Inject the claim immediately before that third scan.
        if calls["count"] == 3:
            current = core.load_task("sample_tool")
            current["status"] = "assigned"
            core._save_task("sample_tool", current)
        return original_scan()

    monkeypatch.setattr(core, "_scan_source_lock_state", activate_after_quarantine)
    result = core.reconcile_source_locks("prune")

    assert result["success"] is False
    assert result["mutations"][0]["action"] == "skipped"
    assert result["mutations"][0]["restore"]["success"] is True
    assert lock_path.exists()


def test_prune_preflight_uncertainty_blocks_entire_batch_before_mutation(
    project_dir, base_modules, monkeypatch
):
    base_modules["modules"]["other_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "other_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    for node_name in ("sample_tool", "other_tool"):
        assert core.generate_task(node_name)["success"] is True
        task = core.load_task(node_name)
        task["status"] = "blocked"
        core._save_task(node_name, task)
    lock_paths = [
        project_dir / core._source_lock_path(
            core.load_task(node_name)["source_lock"]["source_path"]
        )
        for node_name in ("sample_tool", "other_tool")
    ]
    original_revalidate = core._revalidate_source_lock_candidate
    calls = {"count": 0}

    def fail_second_preflight(candidate):
        calls["count"] += 1
        if calls["count"] == 2:
            return {
                "success": False,
                "uncertain": True,
                "mutation_blocked": True,
                "error": "permission uncertainty",
            }
        return original_revalidate(candidate)

    monkeypatch.setattr(
        core, "_revalidate_source_lock_candidate", fail_second_preflight
    )
    result = core.reconcile_source_locks("prune")

    assert result["success"] is False
    assert result["mutation_blocked"] is True
    assert result["mutations"] == []
    assert len(result["preflight"]) == 2
    assert all(path.exists() for path in lock_paths)


def test_reconcile_preflight_uncertainty_creates_no_lock(
    project_dir, base_modules, monkeypatch
):
    base_modules["modules"]["other_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "other_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    lock_paths = []
    for node_name in ("sample_tool", "other_tool"):
        assert core.generate_task(node_name)["success"] is True
        task = core.load_task(node_name)
        path = project_dir / core._source_lock_path(
            task["source_lock"]["source_path"]
        )
        path.unlink()
        lock_paths.append(path)
    original_revalidate = core._revalidate_source_lock_candidate
    calls = {"count": 0}

    def fail_second_preflight(candidate):
        calls["count"] += 1
        if calls["count"] == 2:
            return {
                "success": False,
                "uncertain": True,
                "mutation_blocked": True,
                "error": "read uncertainty",
            }
        return original_revalidate(candidate)

    monkeypatch.setattr(
        core, "_revalidate_source_lock_candidate", fail_second_preflight
    )
    result = core.reconcile_source_locks("reconcile")

    assert result["success"] is False
    assert result["mutation_blocked"] is True
    assert result["mutations"] == []
    assert all(not path.exists() for path in lock_paths)


def test_prune_mutation_scan_uncertainty_restores_and_stops_batch(
    project_dir, base_modules, monkeypatch
):
    base_modules["modules"]["other_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "other_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    lock_paths = []
    for node_name in ("sample_tool", "other_tool"):
        assert core.generate_task(node_name)["success"] is True
        task = core.load_task(node_name)
        task["status"] = "blocked"
        core._save_task(node_name, task)
        lock_paths.append(
            project_dir / core._source_lock_path(task["source_lock"]["source_path"])
        )
    original_scan = core._scan_source_lock_state
    calls = {"count": 0}

    def become_uncertain_after_first_quarantine():
        calls["count"] += 1
        # initial audit, two full-candidate preflights, then mutation scan.
        if calls["count"] == 4:
            state = original_scan()
            state["healthy"] = False
            state["mutation_blocked"] = True
            state["synthetic_invalid"].append({
                "classification": "invalid",
                "reason": "lock_directory_scan_failed",
                "uncertain": True,
            })
            return state
        return original_scan()

    monkeypatch.setattr(
        core, "_scan_source_lock_state", become_uncertain_after_first_quarantine
    )
    result = core.reconcile_source_locks("prune")

    assert result["success"] is False
    assert result["mutation_blocked"] is True
    assert len(result["mutations"]) == 1
    assert result["mutations"][0]["restore"]["success"] is True
    assert len(result["partial_recovery"]["remaining_candidates"]) == 1
    assert all(path.exists() for path in lock_paths)


def test_prune_mutation_uncertainty_restore_conflict_keeps_quarantine(
    project_dir, base_modules, monkeypatch
):
    base_modules["modules"]["other_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "other_tool.py",
    }
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    lock_paths = []
    for node_name in ("sample_tool", "other_tool"):
        assert core.generate_task(node_name)["success"] is True
        task = core.load_task(node_name)
        task["status"] = "blocked"
        core._save_task(node_name, task)
        lock_paths.append(
            project_dir / core._source_lock_path(task["source_lock"]["source_path"])
        )
    original_scan = core._scan_source_lock_state
    calls = {"count": 0}
    current_candidate = {"path": None, "payload": None}
    original_revalidate = core._revalidate_source_lock_candidate

    def capture_preflight_candidate(candidate):
        if current_candidate["path"] is None:
            current_candidate["path"] = Path(candidate["canonical_path"])
            current_candidate["payload"] = json.loads(
                current_candidate["path"].read_text(encoding="utf-8")
            )
        return original_revalidate(candidate)

    def conflict_during_uncertain_scan():
        calls["count"] += 1
        if calls["count"] == 4:
            conflicting = dict(current_candidate["payload"])
            conflicting["task_id"] = "new-identity@v1@test"
            current_candidate["path"].write_text(
                json.dumps(conflicting), encoding="utf-8"
            )
            state = original_scan()
            state["healthy"] = False
            state["mutation_blocked"] = True
            return state
        return original_scan()

    monkeypatch.setattr(
        core, "_revalidate_source_lock_candidate", capture_preflight_candidate
    )
    monkeypatch.setattr(core, "_scan_source_lock_state", conflict_during_uncertain_scan)
    result = core.reconcile_source_locks("prune")

    mutation = result["mutations"][0]
    quarantine = Path(mutation["quarantine"]["quarantine_path"])
    assert result["success"] is False
    assert result["mutation_blocked"] is True
    assert mutation["restore"]["success"] is False
    assert "occupied" in mutation["restore"]["error"]
    assert quarantine.exists()
    assert json.loads(
        current_candidate["path"].read_text(encoding="utf-8")
    )["task_id"] == (
        "new-identity@v1@test"
    )
    assert all(
        path.exists() for path in lock_paths if path != current_candidate["path"]
    )
    assert len(result["partial_recovery"]["remaining_candidates"]) == 1


def test_reconcile_partial_write_failure_removes_only_own_file(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    lock_path.unlink()
    original_dump = _canonical_module.json.dump

    def fail_lock_dump(payload, handle, *args, **kwargs):
        if Path(handle.name).resolve() == lock_path.resolve():
            handle.write("{")
            raise OSError("write failed")
        return original_dump(payload, handle, *args, **kwargs)

    monkeypatch.setattr(_canonical_module.json, "dump", fail_lock_dump)
    result = core.reconcile_source_locks("reconcile")

    assert result["success"] is False
    mutation = result["mutations"][0]
    assert mutation["action"] == "skipped"
    assert mutation["partial_create_cleanup"]["status"] == "removed"
    assert mutation["partial_create_cleanup"]["manual_action_required"] is False
    assert not lock_path.exists()


def test_reconcile_partial_write_cleanup_failure_requires_manual_action(
    project_dir, base_modules, monkeypatch
):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)
    assert core.generate_task("sample_tool")["success"] is True
    task = core.load_task("sample_tool")
    lock_path = project_dir / core._source_lock_path(task["source_lock"]["source_path"])
    lock_path.unlink()
    original_dump = _canonical_module.json.dump
    original_remove = _canonical_module.os.remove

    def fail_lock_dump(payload, handle, *args, **kwargs):
        if Path(handle.name).resolve() == lock_path.resolve():
            handle.write("{")
            raise OSError("write failed")
        return original_dump(payload, handle, *args, **kwargs)

    def deny_partial_cleanup(path):
        if Path(path).resolve() == lock_path.resolve():
            raise PermissionError("cleanup denied")
        return original_remove(path)

    monkeypatch.setattr(_canonical_module.json, "dump", fail_lock_dump)
    monkeypatch.setattr(_canonical_module.os, "remove", deny_partial_cleanup)
    result = core.reconcile_source_locks("reconcile")

    cleanup = result["mutations"][0]["partial_create_cleanup"]
    assert result["success"] is False
    assert cleanup["status"] == "cleanup_failed"
    assert cleanup["manual_action_required"] is True
    assert lock_path.exists()


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

    result = core.task_reject("sample_tool", "invalid", "Chris")
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
