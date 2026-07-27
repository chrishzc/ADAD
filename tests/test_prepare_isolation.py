import hashlib
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = (
    PROJECT_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "prepare_isolation.py"
)
SPEC = importlib.util.spec_from_file_location("prepare_isolation_under_test", SCRIPT_PATH)
prepare_isolation_module = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(prepare_isolation_module)


def _write_issued_task(tmp_path, *, status="assigned"):
    tasks_dir = tmp_path / ".agents" / "tasks"
    tasks_dir.mkdir(parents=True, exist_ok=True)
    task_path = tasks_dir / "test_node.task.json"
    task_data = {
        "node_name": "test_node",
        "status": status,
        "source_lock": {"source_path": "source.py"},
    }
    task_path.write_text(json.dumps(task_data), encoding="utf-8")
    (tmp_path / "source.py").write_text("VALUE = 1\n", encoding="utf-8")
    return task_path


def _mock_context(monkeypatch):
    def fake_run(*_args, **_kwargs):
        return SimpleNamespace(
            returncode=0,
            stdout=json.dumps({"target_node": {"source": "source.py"}}),
            stderr="",
        )

    monkeypatch.setattr(prepare_isolation_module.subprocess, "run", fake_run)


def test_rejects_traversal_before_any_workspace_cleanup(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    protected_task = tmp_path / ".agents" / "tasks" / "adad_core.task.json"
    protected_task.parent.mkdir(parents=True)
    protected_task.write_text('{"sentinel": true}', encoding="utf-8")
    original_digest = hashlib.sha256(protected_task.read_bytes()).hexdigest()

    result = prepare_isolation_module.prepare_isolation("../tasks")

    assert result["success"] is False
    assert "node_name" in result["error"]
    assert hashlib.sha256(protected_task.read_bytes()).hexdigest() == original_digest
    assert not (tmp_path / ".agents" / "workspaces").exists()


def test_missing_task_unknown_artifact_and_bad_status_do_not_write(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / ".agents" / "tasks").mkdir(parents=True)

    missing = prepare_isolation_module.prepare_isolation("missing_node")
    assert missing["success"] is False
    assert "任務快照" in missing["error"]

    issued_task = _write_issued_task(tmp_path, status="approved")
    unknown = prepare_isolation_module.prepare_isolation("test_node", "unknown")
    rejected_status = prepare_isolation_module.prepare_isolation("test_node")
    assert unknown["success"] is False
    assert "未知" in unknown["error"]
    assert rejected_status["success"] is False
    assert "status" in rejected_status["error"]
    assert issued_task.exists()
    assert not (tmp_path / ".agents" / "workspaces").exists()


def test_creates_owned_workspace_and_preserves_task_snapshot(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    task_path = _write_issued_task(tmp_path)
    original_task = task_path.read_bytes()
    _mock_context(monkeypatch)

    result = prepare_isolation_module.prepare_isolation("test_node")

    workspace = tmp_path / ".agents" / "workspaces" / "test_node"
    assert result["success"] is True
    assert Path(result["workspace"]) == workspace
    assert result["cleanup_status"] == "cleaned"
    assert (workspace / "source.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    assert (workspace / ".agents" / "tasks" / "test_node.task.json").read_bytes() == original_task
    marker = json.loads((workspace / ".adad-isolation-owner.json").read_text(encoding="utf-8"))
    assert marker["node_name"] == "test_node"
    assert task_path.read_bytes() == original_task


def test_preserves_existing_unowned_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_issued_task(tmp_path)
    _mock_context(monkeypatch)
    workspace = tmp_path / ".agents" / "workspaces" / "test_node"
    workspace.mkdir(parents=True)
    sentinel = workspace / "do-not-delete.txt"
    sentinel.write_text("preserve me", encoding="utf-8")

    result = prepare_isolation_module.prepare_isolation("test_node")

    assert result["success"] is False
    assert result["cleanup_status"] == "preserved_unowned"
    assert result["manual_action_required"] is True
    assert sentinel.read_text(encoding="utf-8") == "preserve me"
    assert result["workspace"] != str(workspace)


def test_rebuilds_only_a_marker_owned_workspace(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_issued_task(tmp_path)
    _mock_context(monkeypatch)

    first = prepare_isolation_module.prepare_isolation("test_node")
    workspace = Path(first["workspace"])
    stale_file = workspace / "stale-unmanaged-file.txt"
    stale_file.write_text("old", encoding="utf-8")

    second = prepare_isolation_module.prepare_isolation("test_node")

    assert first["success"] is True
    assert second["success"] is True
    assert second["cleanup_status"] == "cleaned"
    assert not stale_file.exists()
    marker = json.loads((workspace / ".adad-isolation-owner.json").read_text(encoding="utf-8"))
    assert marker["node_name"] == "test_node"


def test_retains_quarantine_when_nested_tree_is_not_safe(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _write_issued_task(tmp_path)
    _mock_context(monkeypatch)
    first = prepare_isolation_module.prepare_isolation("test_node")
    assert first["success"] is True
    monkeypatch.setattr(prepare_isolation_module, "_safe_tree_for_removal", lambda _path: False)

    result = prepare_isolation_module.prepare_isolation("test_node")

    assert result["success"] is False
    assert result["cleanup_status"] == "quarantine_retained"
    assert result["manual_action_required"] is True
    assert Path(result["workspace"]).is_dir()
    assert Path(result["receipt"]["quarantine"]).is_dir()
