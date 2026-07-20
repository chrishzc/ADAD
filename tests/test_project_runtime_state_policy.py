# -*- coding: utf-8 -*-
import os
import json
import yaml
import hashlib
import pytest
from pathlib import Path

# Load core/repository and audit service test helper logic
from test_source_lock_repository import _repository, SourceLockRepository, _write_lock
from source_lock_audit_service import SourceLockAuditService

# Import the code under test
from project_runtime_state_policy import (
    inspect_non_ssot_runtime_artifacts,
    archive_non_ssot_source_locks,
    archive_non_ssot_task_snapshots,
    ProjectRuntimeStatePolicy,
    TaskSnapshotArchiveRepository
)

def _write_yaml(path, data):
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f)

def _write_task_snapshot(project_root, node_name, task_id, status="assigned", source="some_file.py::func"):
    task_dir = project_root / ".agents" / "tasks"
    task_dir.mkdir(parents=True, exist_ok=True)
    payload = {
        "schema_version": 3,
        "task_id": task_id,
        "node_name": node_name,
        "status": status,
        "exported_at": "2026-07-19T00:00:00Z",
        "system_map_version": 18,
        "source_hash": "dummy_hash",
        "history": [],
        "rollback": {"strategy": "preserve_diff", "source_path": source.split("::")[0]},
        "source_lock": {
            "source_path": source.split("::")[0],
            "node_name": node_name,
            "task_id": task_id,
            "acquired_at": "2026-07-19T00:00:00Z"
        },
        "spec": {
            "target_node": {
                "name": node_name,
                "type": "function",
                "state": "planned",
                "source": source
            }
        }
    }
    path = task_dir / f"{node_name}.task.json"
    encoded = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    path.write_text(encoded, encoding="utf-8")
    return path, payload

def test_inspect_input_validation(tmp_path):
    audit_service = SourceLockAuditService(tmp_path, ".agents/tasks", None, None, None)

    # 1. Empty candidate node names
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, [])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "empty_or_invalid_candidates"

    # 2. Path traversal
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["../test"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "invalid_or_traversal_candidate_name"

    # 3. Duplicate candidate names
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["node_a", "node_a"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "duplicate_candidate_names"

def test_inspect_system_map_missing_or_unreadable(tmp_path):
    audit_service = SourceLockAuditService(tmp_path, ".agents/tasks", None, None, None)

    # Missing system_map.yaml
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["node_a"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "system_map_missing"

    # Unreadable system_map.yaml
    map_file = tmp_path / "system_map.yaml"
    map_file.write_text("invalid: yaml: :", encoding="utf-8")
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["node_a"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "system_map_unreadable"

def test_inspect_audit_unhealthy(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "system_map.yaml", {"version": 18, "modules": {}})
    audit_service = SourceLockAuditService(tmp_path, ".agents/tasks", None, None, None)

    # Mock audit to return unhealthy
    monkeypatch.setattr(audit_service, "audit", lambda: {"success": False, "healthy": False})
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["node_a"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "audit_service_unhealthy_or_blocked"

def test_inspect_rejects_ssot_owner(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "system_map.yaml", {
        "version": 18,
        "modules": {
            "active_node": {"state": "validated", "source": "active_file.py::active_func"}
        }
    })
    repo = _repository(tmp_path)
    audit_service = SourceLockAuditService(
        tmp_path,
        ".agents/tasks",
        repo,
        lambda p: ["active_node"] if p == "active_file.py" else [],
        lambda payload, name: {"valid": True, "errors": []}
    )

    # inspect candidate active_node which is in SSOT
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["active_node"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "candidate_has_ssot_owner"

def test_inspect_rejects_active_claims_and_source_owner(tmp_path, monkeypatch):
    _write_yaml(tmp_path / "system_map.yaml", {
        "version": 18,
        "modules": {
            "active_node": {"state": "validated", "source": "active_file.py::active_func"}
        }
    })
    repo = _repository(tmp_path)
    # Write an active task snapshot for non-SSOT node candidate_node, but it references active_file.py which has active owner
    _write_task_snapshot(tmp_path, "candidate_node", "cand@v1", status="assigned", source="active_file.py::active_func")

    audit_service = SourceLockAuditService(
        tmp_path,
        ".agents/tasks",
        repo,
        lambda p: ["active_node"] if p == "active_file.py" else [],
        lambda payload, name: {"valid": True, "errors": []}
    )

    # Candidate node references source file owned by active_node in SSOT
    res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["candidate_node"])
    assert res["healthy"] is False
    assert res["preflight_receipt"]["reason"] == "source_path_has_ssot_owner"

def test_inspect_success_and_archive(tmp_path):
    _write_yaml(tmp_path / "system_map.yaml", {
        "version": 18,
        "modules": {}
    })
    repo = _repository(tmp_path)
    task_path, task_data = _write_task_snapshot(tmp_path, "legacy_node", "legacy@v1", status="approved", source="legacy_file.py::func")
    # Write a stale lock matching the task snapshot
    lock_payload = task_data["source_lock"]
    lock_path = _write_lock(tmp_path, repo, lock_payload)

    audit_service = SourceLockAuditService(
        tmp_path,
        ".agents/tasks",
        repo,
        lambda p: [],
        lambda payload, name: {"valid": True, "errors": []}
    )

    # 1. Preflight Inspect
    inspect_res = inspect_non_ssot_runtime_artifacts(tmp_path, audit_service, ["legacy_node"])
    assert inspect_res["healthy"] is True
    preflight = inspect_res["preflight_receipt"]
    assert preflight["success"] is True
    details = preflight["candidate_details"]["legacy_node"]
    assert details["task_exists"] is True
    assert details["task_id"] == "legacy@v1"
    assert len(details["locks"]) == 1

    # 2. Archive Source Locks
    lock_res = archive_non_ssot_source_locks(tmp_path, repo, preflight)
    assert lock_res["lock_archive_receipt"]["success"] is True
    # The lock file must be quarantined (meaning it is moved/quarantined from the repository)
    assert not lock_path.exists()

    # 3. Archive Task Snapshots
    task_res = archive_non_ssot_task_snapshots(tmp_path, preflight)
    assert task_res["task_archive_receipt"]["success"] is True
    # The original task snapshot must be moved (no longer exists in original location)
    assert not task_path.exists()
    # The archive repository must contain the archived snapshot
    archive_repo = TaskSnapshotArchiveRepository(tmp_path)
    archived_path = Path(archive_repo.archive_path("legacy_node", "legacy@v1"))
    assert archived_path.exists()
    archived_data = json.loads(archived_path.read_text(encoding="utf-8"))
    assert archived_data["task_id"] == "legacy@v1"

def test_task_snapshot_archive_repository_validation(tmp_path):
    repo = TaskSnapshotArchiveRepository(tmp_path)

    def write_src(task_id="legacy@v1"):
        src_file = tmp_path / f"legacy_{task_id}.task.json"
        payload = {"task_id": task_id, "node_name": "legacy"}
        content = json.dumps(payload) + "\n"
        src_file.write_text(content, encoding="utf-8")
        raw_bytes = src_file.read_bytes()
        details = os.lstat(src_file)
        expected_identity = {
            "identity": {"st_dev": details.st_dev, "st_ino": details.st_ino},
            "payload_digest": hashlib.sha256(raw_bytes).hexdigest()
        }
        return src_file, expected_identity

    src_file, expected_identity = write_src()

    # 1. First archive succeeds
    res = repo.archive(src_file, "legacy", "legacy@v1", expected_identity)
    assert res["success"] is True
    assert Path(res["dest_path"]).exists()
    assert not src_file.exists()

    # 2. Duplicate archive fails (non-overwrite)
    src_file, expected_identity = write_src()
    res2 = repo.archive(src_file, "legacy", "legacy@v1", expected_identity)
    assert res2["success"] is False
    assert "already exists" in res2["error"]

    # 3. Identity mismatch fails
    src_file, expected_identity = write_src()
    mismatched_identity = expected_identity.copy()
    mismatched_identity["payload_digest"] = "wrong_digest"
    res3 = repo.archive(src_file, "legacy", "legacy@v2", mismatched_identity)
    assert res3["success"] is False
    assert "Identity mismatch" in res3["error"]

def test_aggregator_policy_service(tmp_path):
    _write_yaml(tmp_path / "system_map.yaml", {
        "version": 18,
        "modules": {}
    })
    repo = _repository(tmp_path)
    task_path, task_data = _write_task_snapshot(tmp_path, "legacy_node", "legacy@v1", status="approved", source="legacy_file.py::func")
    lock_payload = task_data["source_lock"]
    lock_path = _write_lock(tmp_path, repo, lock_payload)

    audit_service = SourceLockAuditService(
        tmp_path,
        ".agents/tasks",
        repo,
        lambda p: [],
        lambda payload, name: {"valid": True, "errors": []}
    )

    policy_service = ProjectRuntimeStatePolicy(tmp_path, audit_service, repo)
    result = policy_service.archive_non_ssot_task_artifacts(["legacy_node"])

    assert result["success"] is True
    assert result["archive_receipt"]["preflight"]["success"] is True
    assert result["archive_receipt"]["locks_archive"]["success"] is True
    assert result["archive_receipt"]["tasks_archive"]["success"] is True
    assert not task_path.exists()
    assert len(result["mutation_evidence"]) > 0
    assert result["post_audit_report"]["success"] is True

def test_archive_relocate_non_overwrite_atomic_prevention(tmp_path):
    repo = TaskSnapshotArchiveRepository(tmp_path)

    src_file = tmp_path / "test_toctou.task.json"
    payload = {"task_id": "toctou@v1", "node_name": "test_toctou"}
    src_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    raw_bytes = src_file.read_bytes()
    details = os.lstat(src_file)
    expected_identity = {
        "identity": {"st_dev": details.st_dev, "st_ino": details.st_ino},
        "payload_digest": hashlib.sha256(raw_bytes).hexdigest()
    }

    os.makedirs(repo.archive_dir, exist_ok=True)
    dest_path = repo.archive_path("test_toctou", "toctou@v1")

    with open(dest_path, "w", encoding="utf-8") as f:
        f.write("existing_evidence\n")

    res = repo.archive(src_file, "test_toctou", "toctou@v1", expected_identity)
    assert res["success"] is False
    assert "already exists" in res["error"]

    with open(dest_path, "r", encoding="utf-8") as f:
        content = f.read()
    assert content == "existing_evidence\n"
    assert src_file.exists()

def test_archive_relocate_unlink_race_prevention(tmp_path, monkeypatch):
    repo = TaskSnapshotArchiveRepository(tmp_path)

    src_file = tmp_path / "test_race.task.json"
    payload = {"task_id": "race@v1", "node_name": "test_race"}
    src_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    raw_bytes = src_file.read_bytes()
    details = os.lstat(src_file)
    expected_identity = {
        "identity": {"st_dev": details.st_dev, "st_ino": details.st_ino},
        "payload_digest": hashlib.sha256(raw_bytes).hexdigest()
    }

    dest_path = Path(repo.archive_path("test_race", "race@v1"))

    monkeypatch.setattr(os, "name", "nt")

    def mock_rename(src, dst):
        with open(src_file, "w", encoding="utf-8") as f:
            f.write("malicious_tamper\n")
        raise OSError("Simulated cross-device link failure")
    monkeypatch.setattr(os, "rename", mock_rename)

    res = repo.archive(src_file, "test_race", "race@v1", expected_identity)
    assert res["success"] is False
    assert "Archive failed" in res["error"] or "identity or payload changed" in res["error"]

    assert src_file.exists()
    assert src_file.read_text(encoding="utf-8") == "malicious_tamper\n"
    assert not dest_path.exists()

def test_archive_windows_rename_tamper_race_prevention(tmp_path, monkeypatch):
    repo = TaskSnapshotArchiveRepository(tmp_path)

    src_file = tmp_path / "test_win_race.task.json"
    payload = {"task_id": "win_race@v1", "node_name": "test_win_race"}
    src_file.write_text(json.dumps(payload) + "\n", encoding="utf-8")
    raw_bytes = src_file.read_bytes()
    details = os.lstat(src_file)
    expected_identity = {
        "identity": {"st_dev": details.st_dev, "st_ino": details.st_ino},
        "payload_digest": hashlib.sha256(raw_bytes).hexdigest()
    }

    dest_path = Path(repo.archive_path("test_win_race", "win_race@v1"))

    monkeypatch.setattr(os, "name", "nt")

    original_rename = os.rename
    def mock_rename(src, dst):
        # Simulate race: another process replaces src with a new inode right before rename
        os.remove(src)
        with open(src, "w", encoding="utf-8") as f:
            f.write("malicious_tamper\n")
        original_rename(src, dst)

    monkeypatch.setattr(os, "rename", mock_rename)

    res = repo.archive(src_file, "test_win_race", "win_race@v1", expected_identity)
    assert res["success"] is False
    assert "Archive failed" in res["error"] or "changed before rename" in res["error"]

    assert src_file.exists()
    assert src_file.read_text(encoding="utf-8") == "malicious_tamper\n"
    assert not dest_path.exists()
