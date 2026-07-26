import os
import sys
import tempfile
import pytest
import shutil
import stat
import importlib.util
from pathlib import Path
from unittest.mock import patch, MagicMock

CANONICAL_CORE_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_core.py"
)
sys.path.insert(0, str(CANONICAL_CORE_PATH.parent))
_canonical_spec = importlib.util.spec_from_file_location(
    "canonical_adad_core_verification_lifecycle", CANONICAL_CORE_PATH
)
_canonical_module = importlib.util.module_from_spec(_canonical_spec)
_canonical_spec.loader.exec_module(_canonical_module)
ADADCore = _canonical_module.ADADCore


def _install_owned_root_credential(core, target):
    import json

    marker = target / ".adad-owned-root.json"
    nonce = "test-owned-root-credential"
    marker.write_text(
        json.dumps({"schema": 1, "nonce": nonce}, sort_keys=True, separators=(",", ":")),
        encoding="utf-8",
    )
    return {
        "nonce": nonce,
        "marker_name": marker.name,
        "marker_identity": core._get_path_identity(str(marker)),
        "root_identity": core._get_path_identity(str(target)),
    }


class CanonicalADADCore(ADADCore):
    def __init__(self, map_path, check_validity=False, project_root=None):
        super().__init__(map_path, check_validity=check_validity, project_root=project_root)
        self.data = {"modules": {"adad_core": {"state": "validated"}}}

    def get_node(self, node_name=None):
        return self.data["modules"]["adad_core"]

@pytest.fixture
def mock_core(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    test_file = project_root / "dummy_test.py"
    test_file.write_text("def test_dummy():\n    assert True\n", encoding="utf-8")
    system_map = project_root / "system_map.yaml"
    system_map.write_text("adad_core:\n  state: validated\n", encoding="utf-8")

    core = CanonicalADADCore(map_path=str(system_map), project_root=str(project_root))
    core.data["modules"]["adad_core"]["verification"] = [
        {
            "command": {
                "argv": [sys.executable, "-m", "pytest", str(test_file)],
                "cwd": "project",
                "expect_exit": 0,
                "timeout": 10
            }
        }
    ]
    return core, project_root, test_file

def _extract_cmd_result(result):
    assert isinstance(result["success"], bool)
    assert len(result["command_results"]) == 1
    return result["command_results"][0]

def test_implicit_basetemp_creates_two_layer_and_cleans_outer(mock_core):
    core, project_root, test_file = mock_core
    protected_task = project_root / ".agents" / "tasks" / "codex.task.json"
    protected_task.parent.mkdir(parents=True)
    protected_task.write_text('{"node_name": "codex"}', encoding="utf-8")

    created_roots = []
    original_mkdtemp = tempfile.mkdtemp
    def spy_mkdtemp(*args, **kwargs):
        res = original_mkdtemp(*args, **kwargs)
        if kwargs.get("prefix") == "adad_verify_":
            created_roots.append(res)
        return res

    with patch("tempfile.mkdtemp", side_effect=spy_mkdtemp):
        result = core.verify_implementation("adad_core", str(test_file))

    assert result["success"] is True
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is True
    assert cmd_result["cleanup_status"] == "cleaned"
    assert cmd_result["workspace_preserved"] is False
    assert cmd_result["preflight_result"]["allowed"] is True

    assert len(created_roots) == 1
    outer_root = created_roots[0]
    assert not os.path.exists(outer_root)
    assert os.path.commonpath([outer_root, str(project_root)]) != str(project_root)
    assert cmd_result["basetemp_path"] == os.path.join(outer_root, "pytest-basetemp")
    assert protected_task.exists()

def test_explicit_basetemp_is_unowned_absolute(mock_core, tmp_path):
    core, project_root, test_file = mock_core
    explicit_basetemp = tmp_path / "explicit_basetemp"
    explicit_basetemp.mkdir()
    core.data["modules"]["adad_core"]["verification"][0]["command"]["argv"].extend(["--basetemp", str(explicit_basetemp)])

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is True
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is True
    assert cmd_result.get("basetemp_status") == "unowned"
    assert cmd_result["cleanup_status"] == "cleaned"
    assert cmd_result["workspace_preserved"] is False
    assert cmd_result["basetemp_path"] == str(explicit_basetemp)
    assert explicit_basetemp.exists()

def test_explicit_basetemp_is_unowned_relative(mock_core, tmp_path):
    core, project_root, test_file = mock_core
    explicit_basetemp = project_root / "explicit_basetemp"
    explicit_basetemp.mkdir()
    core.data["modules"]["adad_core"]["verification"][0]["command"]["argv"].extend(["--basetemp=explicit_basetemp"])
    core.data["modules"]["adad_core"]["verification"][0]["command"]["cwd"] = "project"

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is True
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is True
    assert cmd_result.get("basetemp_status") == "unowned"
    assert cmd_result["cleanup_status"] == "cleaned"
    assert cmd_result["workspace_preserved"] is False
    assert cmd_result["basetemp_path"] == "explicit_basetemp"
    assert explicit_basetemp.exists()

def test_explicit_workspace_basetemp_is_owned(mock_core, tmp_path):
    core, project_root, test_file = mock_core
    core.data["modules"]["adad_core"]["verification"][0]["command"]["argv"].extend(["--basetemp={workspace}/my_temp"])

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is True
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is True
    assert cmd_result["cleanup_status"] == "cleaned"
    assert cmd_result["workspace_preserved"] is False

def test_command_nonzero_preserves_workspace(mock_core):
    core, project_root, test_file = mock_core
    test_file.write_text("def test_dummy():\n    assert False\n", encoding="utf-8")

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is False
    assert cmd_result["cleanup_status"] == "preserved_command_failed"
    assert cmd_result["workspace_preserved"] is True
    assert os.path.exists(cmd_result["workspace_path"])
    shutil.rmtree(cmd_result["workspace_path"], ignore_errors=True)

def test_timeout_preserves_workspace(mock_core):
    core, project_root, test_file = mock_core
    test_file.write_text("import time\ndef test_dummy():\n    time.sleep(10)\n    assert True\n", encoding="utf-8")
    core.data["modules"]["adad_core"]["verification"][0]["command"]["timeout"] = 0.5

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is False
    assert cmd_result["cleanup_status"] == "preserved_timeout"
    assert cmd_result["workspace_preserved"] is True
    assert os.path.exists(cmd_result["workspace_path"])
    shutil.rmtree(cmd_result["workspace_path"], ignore_errors=True)

def test_keyboard_interrupt_preserves_workspace(mock_core):
    core, project_root, test_file = mock_core
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = KeyboardInterrupt()
        result = core.verify_implementation("adad_core", str(test_file))

    assert result["success"] is False
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is False
    assert cmd_result["cleanup_status"] == "preserved_termination_uncertain"
    assert cmd_result["interrupted"] is True
    assert cmd_result["manual_action_required"] is True
    assert cmd_result["workspace_preserved"] is True
    assert os.path.exists(cmd_result["workspace_path"])
    import shutil
    shutil.rmtree(cmd_result["workspace_path"], ignore_errors=True)

def test_popen_failure_preserves_workspace(mock_core):
    core, project_root, test_file = mock_core
    with patch("subprocess.Popen") as mock_popen:
        mock_popen.side_effect = OSError("mock OS error")
        result = core.verify_implementation("adad_core", str(test_file))

    assert result["success"] is False
    cmd_result = _extract_cmd_result(result)
    assert cmd_result["passed"] is False
    assert cmd_result["cleanup_status"] == "preserved_termination_uncertain"
    assert cmd_result["workspace_preserved"] is True
    assert cmd_result["manual_action_required"] is True
    assert cmd_result["cleanup_error"]["stage"] == "popen"
    assert os.path.exists(cmd_result["workspace_path"])
    shutil.rmtree(cmd_result["workspace_path"], ignore_errors=True)

def test_preflight_rejects_repo_equals_repo(mock_core, monkeypatch):
    core, project_root, test_file = mock_core
    identity = core._get_path_identity(str(project_root))
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(project_root), identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "repo_target_equals_repo"
    assert os.path.exists(str(project_root))

def test_preflight_rejects_repo_ancestor(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    identity = core._get_path_identity(str(tmp_path))
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(tmp_path), identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "repo_target_is_ancestor"
    assert os.path.exists(str(tmp_path))

def test_preflight_rejects_repo_inside_repo(mock_core, monkeypatch):
    core, project_root, test_file = mock_core
    child = project_root / "child"
    child.mkdir()
    identity = core._get_path_identity(str(child))
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(child), identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "repo_target_inside_repo"
    assert os.path.exists(str(child))

def test_preflight_allows_similar_prefix_but_unrelated(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    unrelated = tmp_path / "project-unrelated"
    unrelated.mkdir()
    identity = core._get_path_identity(str(unrelated))
    credential = _install_owned_root_credential(core, unrelated)
    status, error, preflight = core._safe_cleanup_owned_root(
        str(unrelated), identity, credential
    )
    assert status == "cleaned"
    assert preflight["allowed"] is True

def test_identity_mismatch_fails_closed(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = {"st_dev": 123, "st_ino": 456, "type": 16384, "reparse_tag": 0}
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(target), initial_identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "identity_mismatch"
    assert os.path.exists(str(target))

def test_identity_unavailable_fails_closed(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    # Missing st_dev or st_ino
    initial_identity = None
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(target), initial_identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "identity_unavailable"
    assert os.path.exists(str(target))

def test_symlink_fails_closed(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    link = tmp_path / "link"
    try:
        os.symlink(str(target), str(link))
    except OSError:
        pytest.skip("Symlink privilege not available")

    initial_identity = core._get_path_identity(str(link))
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))
    status, error, preflight = core._safe_cleanup_owned_root(str(link), initial_identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] in ("ancestor_symlink", "ancestor_reparse_point")
    os.unlink(str(link))

def test_rmtree_postcondition_exists_fails(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = core._get_path_identity(str(target))
    credential = _install_owned_root_credential(core, target)

    def fake_rmtree(*args, **kwargs):
        pass # don't actually delete it
    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

    status, error, preflight = core._safe_cleanup_owned_root(
        str(target), initial_identity, credential
    )
    assert status == "preserved_cleanup_failed"
    assert error["error_type"] == "ExistsError"
    assert not target.exists()
    assert os.path.isdir(preflight["quarantine_path"])

def test_rmtree_exception_propagates(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = core._get_path_identity(str(target))
    credential = _install_owned_root_credential(core, target)

    def fake_rmtree(*args, **kwargs):
        raise OSError("Permission denied from fake rmtree")
    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

    status, error, preflight = core._safe_cleanup_owned_root(
        str(target), initial_identity, credential
    )
    assert status == "preserved_cleanup_failed"
    assert error["error_type"] == "OSError"
    assert error["stage"] == "rmtree"
    assert not target.exists()
    assert os.path.isdir(preflight["quarantine_path"])

def test_rmtree_retries_transient_permission_error(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = core._get_path_identity(str(target))
    credential = _install_owned_root_credential(core, target)
    original_rmtree = shutil.rmtree
    attempts = []

    def flaky_rmtree(*args, **kwargs):
        attempts.append(args[0])
        if len(attempts) == 1:
            raise PermissionError("transient file lock")
        return original_rmtree(*args, **kwargs)

    monkeypatch.setattr(shutil, "rmtree", flaky_rmtree)
    monkeypatch.setattr("time.sleep", lambda _: None)

    status, error, preflight = core._safe_cleanup_owned_root(
        str(target), initial_identity, credential
    )

    assert status == "cleaned"
    assert error is None
    assert preflight["allowed"] is True
    assert len(attempts) == 2
    assert not target.exists()

def test_rmtree_retry_failure_propagates(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = core._get_path_identity(str(target))
    credential = _install_owned_root_credential(core, target)

    def fake_rmtree(*args, **kwargs):
        onerror = kwargs.get("onerror")
        if onerror:
            # mock chmod failure
            monkeypatch.setattr(os, "chmod", lambda *a, **k: (_ for _ in ()).throw(OSError("chmod failed")))
            onerror(os.unlink, str(target), None)

    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)

    status, error, preflight = core._safe_cleanup_owned_root(
        str(target), initial_identity, credential
    )
    assert status == "preserved_cleanup_failed"
    assert error["error_type"] == "OSError"
    assert error["stage"] == "rmtree_retry"

def test_integration_step_failure_preserves_outer_root(mock_core, tmp_path):
    core, project_root, test_file = mock_core
    test_file.write_text("def test_dummy():\n    assert False\n", encoding="utf-8")
    core.data["modules"]["adad_core"]["verification"] = [
        {
            "integration_case": {
                "name": "integration_test",
                "steps": [
                    {
                        "argv": [sys.executable, "-m", "pytest", str(test_file)],
                        "cwd": "workspace",
                        "expect_exit": 0,
                        "timeout": 10
                    }
                ]
            }
        }
    ]

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    res = result["integration_results"][0]
    assert res["passed"] is False
    assert res["aggregate_status"] == "preserved_command_failed"
    assert res["workspace_preserved"] is True
    assert os.path.exists(res["workspace_path"])
    shutil.rmtree(res["workspace_path"], ignore_errors=True)

def test_not_applicable_workspace(mock_core):
    core, project_root, test_file = mock_core
    core.data["modules"]["adad_core"]["verification"] = [
        {
            "command": {
                "argv": [sys.executable, "-c", "print('hello')"],
                "cwd": "project",
                "expect_exit": 0,
                "timeout": 10
            }
        }
    ]

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is True
    cmd = _extract_cmd_result(result)
    assert cmd["passed"] is True
    assert cmd["cleanup_status"] == "not_applicable"
    assert cmd["workspace_path"] is None
    assert cmd["workspace_preserved"] is False


def test_all_commands_success_but_cleanup_failed(mock_core, monkeypatch):
    core, project_root, test_file = mock_core

    # Mock cleanup to fail
    def fake_cleanup(*args, **kwargs):
        return "preserved_cleanup_failed", {"error_type": "mock"}, None
    monkeypatch.setattr(core, "_safe_cleanup_owned_root", fake_cleanup)

    result = core.verify_implementation("adad_core", str(test_file))

    assert result["success"] is False
    cmd = _extract_cmd_result(result)
    assert cmd["passed"] is False
    assert cmd["cleanup_status"] == "preserved_cleanup_failed"
    assert cmd["workspace_preserved"] is True
    assert cmd["manual_action_required"] is True
    assert cmd["cleanup_error"] == {"error_type": "mock"}

def test_mixed_multi_command_shared_root(mock_core):
    core, project_root, test_file = mock_core
    test_file.write_text("def test_dummy():\n    assert True\n", encoding="utf-8")
    fail_file = project_root / "fail_test.py"
    fail_file.write_text("def test_fail():\n    assert False\n", encoding="utf-8")

    core.data["modules"]["adad_core"]["verification"] = [
        {
            "command": {
                "argv": [sys.executable, "-m", "pytest", str(test_file)],
                "cwd": "workspace",
                "expect_exit": 0,
                "timeout": 10
            }
        },
        {
            "command": {
                "argv": [sys.executable, "-m", "pytest", str(fail_file)],
                "cwd": "workspace",
                "expect_exit": 0,
                "timeout": 10
            }
        }
    ]

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    assert len(result["command_results"]) == 2

    cmd1 = result["command_results"][0]
    cmd2 = result["command_results"][1]

    assert cmd1["passed"] is False
    assert cmd2["passed"] is False
    assert cmd1["cleanup_status"] == "preserved_command_failed"
    assert cmd2["cleanup_status"] == "preserved_command_failed"
    assert cmd1["workspace_preserved"] is True
    assert cmd2["workspace_preserved"] is True

    # Original failure diagnostics should still be in cmd2
    assert cmd2["diagnostics"]["exit_ok"] is False

def test_external_basetemp_and_outer_cleanup_failure(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    explicit_basetemp = tmp_path / "explicit_basetemp"
    explicit_basetemp.mkdir()
    core.data["modules"]["adad_core"]["verification"][0]["command"]["argv"].extend(["--basetemp", str(explicit_basetemp)])

    def fake_cleanup(*args, **kwargs):
        return "preserved_cleanup_failed", {"error_type": "mock"}, None
    monkeypatch.setattr(core, "_safe_cleanup_owned_root", fake_cleanup)

    result = core.verify_implementation("adad_core", str(test_file))

    assert result["success"] is False
    cmd = _extract_cmd_result(result)
    assert cmd["basetemp_status"] == "unowned"
    assert cmd["cleanup_status"] == "preserved_cleanup_failed"
    assert explicit_basetemp.exists()

def test_integration_step_failure_manual_action(mock_core):
    core, project_root, test_file = mock_core
    fail_file = project_root / "fail_test.py"
    fail_file.write_text("def test_fail():\n    assert False\n", encoding="utf-8")

    core.data["modules"]["adad_core"]["verification"] = [
        {
            "integration_case": {
                "name": "integration_test",
                "steps": [
                    {
                        "argv": [sys.executable, "-m", "pytest", str(fail_file)],
                        "cwd": "workspace",
                        "expect_exit": 0,
                        "timeout": 10
                    }
                ]
            }
        }
    ]

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    res = result["integration_results"][0]

    assert res["passed"] is False
    assert res["manual_action_required"] is True
    step = res["step_results"][0]
    assert step["workspace_preserved"] is True
    assert step["manual_action_required"] is True
    assert step["cleanup_status"] == "preserved_command_failed"

def test_command_failure_termination_uncertainty(mock_core, monkeypatch):
    core, project_root, test_file = mock_core
    # Mock popen to simulate timeout and kill failure
    class MockPopen:
        def __init__(self, *args, **kwargs):
            self.stdout = MagicMock()
            self.stdout.read.return_value = b""
            self.stderr = MagicMock()
            self.stderr.read.return_value = b""
        def communicate(self, timeout=None):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="mock", timeout=timeout)
        def kill(self):
            raise OSError("Kill failed")
        def wait(self, timeout=None):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="mock", timeout=timeout)
        def poll(self):
            return None

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    core.data["modules"]["adad_core"]["verification"][0]["command"]["timeout"] = 0.1

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    cmd = _extract_cmd_result(result)
    assert cmd["cleanup_status"] == "preserved_termination_uncertain"
    assert cmd["workspace_preserved"] is True
    assert cmd["manual_action_required"] is True

def test_timeout_termination_receipt_drain_timeout(mock_core, monkeypatch):
    core, project_root, test_file = mock_core

    class MockPopen:
        def __init__(self, *args, **kwargs):
            self.stdout = MagicMock()
            self.stdout.read.return_value = b""
            self.stderr = MagicMock()
            self.stderr.read.return_value = b""
            self.pid = 9999
        def communicate(self, timeout=None):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="mock", timeout=timeout)
        def kill(self):
            # Kill succeeds
            pass
        def wait(self, timeout=None):
            import subprocess
            raise subprocess.TimeoutExpired(cmd="mock", timeout=timeout)
        def poll(self):
            return None # still running

    import subprocess
    monkeypatch.setattr(subprocess, "Popen", MockPopen)
    core.data["modules"]["adad_core"]["verification"][0]["command"]["timeout"] = 0.1

    result = core.verify_implementation("adad_core", str(test_file))
    assert result["success"] is False
    cmd = _extract_cmd_result(result)
    assert cmd["cleanup_status"] == "preserved_termination_uncertain"

def test_deterministic_replacement_race(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()
    initial_identity = core._get_path_identity(str(target))
    credential = _install_owned_root_credential(core, target)

    # Simulate first rmtree failing with PermissionError
    # and in between, the directory identity changes
    call_count = 0
    replaced = False
    original_rmtree = shutil.rmtree
    def fake_rmtree(*args, **kwargs):
        nonlocal call_count, replaced
        call_count += 1
        if call_count == 1:
            cleanup_target = args[0]
            original_rmtree(cleanup_target)
            os.mkdir(cleanup_target)
            replaced = True
            raise PermissionError("transient")
        else:
            return original_rmtree(*args, **kwargs)

    original_get_identity = core._get_path_identity
    def reused_identity(path):
        if replaced and ".quarantine-" in str(path) and os.path.isdir(path):
            return initial_identity
        return original_get_identity(path)

    monkeypatch.setattr(shutil, "rmtree", fake_rmtree)
    monkeypatch.setattr(core, "_get_path_identity", reused_identity)
    monkeypatch.setattr("time.sleep", lambda _: None)

    status, error, preflight = core._safe_cleanup_owned_root(
        str(target), initial_identity, credential
    )

    # Even if the filesystem identity is reused, the replacement lacks the
    # in-memory ownership credential and must not be deleted.
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "credential_missing"
    assert call_count == 1

def test_windows_reparse_mocked(mock_core, tmp_path, monkeypatch):
    core, project_root, test_file = mock_core
    target = tmp_path / "target"
    target.mkdir()

    initial_identity = core._get_path_identity(str(target))

    # Mock os.lstat to return FILE_ATTRIBUTE_REPARSE_POINT (0x400)
    original_lstat = os.lstat
    def fake_lstat(path):
        st = original_lstat(path)
        if path == str(target):
            # Create a mock stat object with st_file_attributes
            class MockStat:
                def __init__(self, st):
                    self.st_mode = st.st_mode
                    self.st_ino = st.st_ino
                    self.st_dev = st.st_dev
                    self.st_nlink = st.st_nlink
                    self.st_uid = st.st_uid
                    self.st_gid = st.st_gid
                    self.st_size = st.st_size
                    self.st_atime = st.st_atime
                    self.st_mtime = st.st_mtime
                    self.st_ctime = st.st_ctime
                    self.st_file_attributes = getattr(st, "st_file_attributes", 0) | 1024 # 0x400
            return MockStat(st)
        return st

    monkeypatch.setattr(os, "lstat", fake_lstat)
    monkeypatch.setattr(shutil, "rmtree", lambda *args, **kwargs: pytest.fail("Must not call rmtree"))

    status, error, preflight = core._safe_cleanup_owned_root(str(target), initial_identity)
    assert status == "preserved_preflight_rejected"
    assert preflight["reason"] == "ancestor_reparse_point"
