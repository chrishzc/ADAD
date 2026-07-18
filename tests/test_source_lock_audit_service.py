# -*- coding: utf-8 -*-
import importlib.util
import sys
import json
import os
from pathlib import Path

from conftest import write_yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
CANONICAL_CORE_PATH = (
    REPO_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_core.py"
)
CANONICAL_REPO_PATH = (
    REPO_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "source_lock_repository.py"
)
CANONICAL_SERVICE_PATH = (
    REPO_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "source_lock_audit_service.py"
)
SOURCE_SCRIPTS_DIR = (
    REPO_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
)
if str(SOURCE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_SCRIPTS_DIR))


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core_module = _load_module(CANONICAL_CORE_PATH, "source_lock_audit_service_task_core")
repo_module = _load_module(CANONICAL_REPO_PATH, "source_lock_audit_service_task_repo")
service_module = _load_module(
    CANONICAL_SERVICE_PATH, "source_lock_audit_service_task_service"
)

CanonicalADADCore = core_module.ADADCore
SourceLockRepository = repo_module.SourceLockRepository
SourceLockAuditService = service_module.SourceLockAuditService

SOURCE_LOCK_DIR = os.path.join(".agents", "tasks", ".source_locks")
TASK_DIR = ".agents/tasks"


def _setup(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    core = CanonicalADADCore(project_dir / "system_map.yaml", check_validity=False)

    def source_owners_for_path(path):
        return [
            node_name
            for node_name, info in (core.data.get("modules", {}) or {}).items()
            if core._normalize_source_file_path((info or {}).get("source")) == path
        ]

    repository = SourceLockRepository(
        project_dir, SOURCE_LOCK_DIR, lambda node_name: (base_modules.get("modules", {}).get(node_name) or {}).get("source")
    )
    service = SourceLockAuditService(
        project_dir,
        TASK_DIR,
        repository,
        source_owners_for_path,
        core.validate_task_snapshot,
    )
    return core, repository, service


def test_source_lock_audit_service_matches_approved_core_audit(project_dir, base_modules):
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

    core, repository, service = _setup(project_dir, base_modules)
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
    orphan_path = project_dir / repository.lock_path("orphan_tool.py")
    orphan_path.parent.mkdir(parents=True, exist_ok=True)
    orphan_path.write_text(json.dumps(orphan_lock), encoding="utf-8")

    assert core.generate_task("invalid_tool")["success"] is True
    invalid = core.load_task("invalid_tool")
    invalid_lock_path = project_dir / repository.lock_path("invalid_tool.py")
    invalid_payload = json.loads(invalid_lock_path.read_text(encoding="utf-8"))
    invalid_payload["task_id"] = "mismatch"
    invalid_lock_path.write_text(json.dumps(invalid_payload), encoding="utf-8")
    core_report = core.audit_source_locks()
    service_report = service.audit()

    assert service_report == core_report


def test_scan_state_matches_approved_core_scan(project_dir, base_modules):
    core, _, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    core_state = core._scan_source_lock_state()
    service_state = service.scan_state()

    assert service_state == core_state


def test_classify_matches_approved_core_classify(project_dir, base_modules):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    core_state = core._scan_source_lock_state()
    lock_path = project_dir / repository.lock_path(core.load_task("sample_tool")["source_lock"]["source_path"])
    core_entry = core._classify_source_lock(str(lock_path), core_state)
    service_entry = service.classify(str(lock_path), core_state)

    assert service_entry == core_entry


def test_service_audit_does_not_call_mutating_repository_methods(monkeypatch, project_dir, base_modules):
    def forbidden(*args, **kwargs):
        raise AssertionError("SourceLockAuditService should be read-only.")

    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    monkeypatch.setattr(repository, "acquire", forbidden)
    monkeypatch.setattr(repository, "release", forbidden)
    monkeypatch.setattr(repository, "quarantine", forbidden)

    report = service.audit()
    assert report["success"] is True


def test_audit_has_three_active_two_stale_and_missing_active_classifications(project_dir, base_modules):
    base_modules["modules"]["in_progress_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "in_progress_tool.py",
    }
    base_modules["modules"]["submitted_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "submitted_tool.py",
    }
    base_modules["modules"]["approved_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "approved_tool.py",
    }
    base_modules["modules"]["blocked_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "blocked_tool.py",
    }
    base_modules["modules"]["missing_active_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "missing_active_tool.py",
    }

    core, repository, service = _setup(project_dir, base_modules)

    assert core.generate_task("sample_tool")["success"] is True
    assert core.generate_task("in_progress_tool")["success"] is True
    assert core.generate_task("submitted_tool")["success"] is True
    assert core.generate_task("approved_tool")["success"] is True
    assert core.generate_task("blocked_tool")["success"] is True
    assert core.generate_task("missing_active_tool")["success"] is True

    in_progress_task = core.load_task("in_progress_tool")
    in_progress_task["status"] = "in_progress"
    core._save_task("in_progress_tool", in_progress_task)
    submitted_task = core.load_task("submitted_tool")
    submitted_task["status"] = "submitted"
    core._save_task("submitted_tool", submitted_task)
    approved_task = core.load_task("approved_tool")
    approved_task["status"] = "approved"
    core._save_task("approved_tool", approved_task)
    blocked_task = core.load_task("blocked_tool")
    blocked_task["status"] = "blocked"
    core._save_task("blocked_tool", blocked_task)

    (project_dir / repository.lock_path("missing_active_tool.py")).unlink()

    core_report = core.audit_source_locks()
    service_report = service.audit()

    assert core_report == service_report
    assert not service_report["mutation_blocked"]
    assert service_report["counts"]["active"] == 3
    assert service_report["counts"]["stale"] == 2
    assert service_report["counts"]["invalid"] == 1
    invalid_records = [
        record
        for record in service_report["categories"]["invalid"]
        if record["reason"] == "active_task_missing_lock"
    ]
    assert len(invalid_records) == 1
    missing_record = invalid_records[0]
    assert missing_record["task_identity"] is not None
    assert missing_record["task_lstat_identity"] is not None
    assert missing_record["canonical_path"] == os.path.abspath(
        project_dir / repository.lock_path("missing_active_tool.py")
    )
    assert not service_report.get("scan_evidence")


def test_scan_ignores_retained_quarantine_paths(project_dir, base_modules):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    lock_path = project_dir / repository.lock_path("sample_tool.py")
    quarantine_path = Path(
        str(lock_path) + ".quarantine-2026-07-17T00-00-00Z-1234"
    )
    quarantine_path.write_text("retained-quarantine", encoding="utf-8")

    core_scan = core._scan_source_lock_state()
    service_scan = service.scan_state()
    core_audit = core.audit_source_locks()
    service_audit = service.audit()

    assert core_scan == service_scan
    assert core_audit == service_audit
    assert ".quarantine-" in os.path.basename(quarantine_path)
    assert all(
        ".quarantine-" not in os.path.basename(path)
        for path in service_scan["lock_paths"]
    )
    assert len(service_scan["lock_paths"]) == 1


def test_classify_mismatch_and_record_evidence_matrix(project_dir, base_modules):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    state = core._scan_source_lock_state()
    lock_path = project_dir / repository.lock_path("sample_tool.py")
    valid_payload = json.loads(lock_path.read_text(encoding="utf-8"))

    filename_lock_path = project_dir / "other"
    filename_lock_path.write_text(json.dumps(valid_payload), encoding="utf-8")

    owner_payload = dict(valid_payload)
    owner_payload["node_name"] = "not_a_owner"
    owner_lock_path = project_dir / repository.lock_path("sample_tool.py")
    owner_lock_path.parent.mkdir(parents=True, exist_ok=True)

    digest_lock_path = project_dir / repository.lock_path("digest_mismatch_tool.py")
    digest_payload = dict(valid_payload)
    digest_payload["source_path"] = "tampered_source.py"
    digest_lock_path.parent.mkdir(parents=True, exist_ok=True)
    digest_lock_path.write_text(json.dumps(digest_payload), encoding="utf-8")

    cases = {
        "metadata": {"path": lock_path, "payload": {**valid_payload, "task_id": "sample_tool@v1@modified"}},
        "filename": filename_lock_path,
        "owner": {"path": owner_lock_path, "payload": owner_payload},
        "digest": digest_lock_path,
    }
    for kind, case in cases.items():
        if isinstance(case, dict):
            case["path"].write_text(json.dumps(case["payload"]), encoding="utf-8")
            path = case["path"]
        else:
            path = case

        core_entry = core._classify_source_lock(str(path), state)
        service_entry = service.classify(str(path), state)
        assert service_entry == core_entry
        assert "payload_digest" in service_entry
        if kind == "owner":
            assert service_entry["reason"] == "source_owner_mismatch"
        elif kind == "filename":
            assert service_entry["reason"] == "lock_filename_digest_mismatch"
        elif kind == "metadata":
            assert service_entry["reason"].startswith("task_lock_mismatch:task_id")
        else:
            assert service_entry["reason"] == "lock_filename_digest_mismatch"
    lock_path.write_text(json.dumps(valid_payload), encoding="utf-8")
    valid_entry = service.classify(str(lock_path), state)
    assert valid_entry["classification"] == "active"
    assert valid_entry["reason"] == "active_task"
    assert "task_identity" in valid_entry
    assert "task_lstat_identity" in valid_entry
    assert "lstat_identity" in valid_entry
    assert "payload_digest" in valid_entry


def test_scan_and_classify_fail_closed_on_uncertain_scandir_stat_and_decode(project_dir, base_modules, monkeypatch):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    lock_path = project_dir / repository.lock_path("sample_tool.py")
    invalid_utf8_path = project_dir / repository.lock_path("sample_tool_invalid_utf8.py")
    invalid_utf8_path.parent.mkdir(parents=True, exist_ok=True)
    with open(invalid_utf8_path, "wb") as handle:
        handle.write(b"\xff\xfe\xfa")

    invalid_json_path = project_dir / repository.lock_path("sample_tool_invalid_json.py")
    invalid_json_path.parent.mkdir(parents=True, exist_ok=True)
    invalid_json_path.write_text("{invalid", encoding="utf-8")

    original_service_scandir = service_module.os.scandir
    original_core_scandir = core_module.os.scandir

    def fail_task_scandir(path):
        if str(path).replace("\\", "/").endswith(".agents/tasks"):
            raise PermissionError("task scan blocked")
        return original_service_scandir(path)

    def fail_task_scandir_for_core(path):
        if str(path).replace("\\", "/").endswith(".agents/tasks"):
            raise PermissionError("task scan blocked")
        return original_core_scandir(path)

    monkeypatch.setattr(service_module.os, "scandir", fail_task_scandir)
    monkeypatch.setattr(core_module.os, "scandir", fail_task_scandir_for_core)

    core_state = core._scan_source_lock_state()
    service_state = service.scan_state()
    assert core_state == service_state
    assert service_state["mutation_blocked"] is True
    assert service_state["healthy"] is False

    decode_state = core._scan_source_lock_state()
    decode_service_entry = service.classify(str(invalid_utf8_path), decode_state)
    assert decode_service_entry["reason"] == "unreadable_lock"
    assert decode_service_entry["classification"] == "invalid"
    assert decode_service_entry["canonical_path"] == os.path.abspath(invalid_utf8_path)
    assert decode_service_entry.get("uncertain") is True
    assert "evidence" in decode_service_entry
    assert decode_service_entry.get("identity") is not None
    assert decode_service_entry.get("payload_digest") is not None

    json_state = core._scan_source_lock_state()
    json_service_entry = service.classify(str(invalid_json_path), json_state)
    assert json_service_entry["reason"] == "unreadable_lock"
    assert json_service_entry["classification"] == "invalid"
    assert json_service_entry["canonical_path"] == os.path.abspath(invalid_json_path)
    assert json_service_entry.get("uncertain") is True
    assert "evidence" in json_service_entry
    assert json_service_entry.get("identity") is not None
    assert json_service_entry.get("payload_digest") is not None

    original_lstat = repo_module.os.lstat

    monkeypatch.setattr(service_module.os, "scandir", original_service_scandir)
    monkeypatch.setattr(core_module.os, "scandir", original_core_scandir)
    task_path = project_dir / TASK_DIR / "sample_tool.task.json"

    def fail_lstat(path):
        if os.fspath(path) == os.fspath(task_path):
            raise PermissionError("deny stat")
        return original_lstat(path)

    monkeypatch.setattr(repo_module.os, "lstat", fail_lstat)
    stat_state = service.scan_state()
    assert stat_state["mutation_blocked"] is True
    assert stat_state["healthy"] is False
    assert stat_state["task_snapshots"]["sample_tool"]["validation"]["valid"] is False
    task_record = next(
        item
        for item in service.audit()["categories"]["invalid"]
        if item.get("node_name") == "sample_tool" and item["reason"] == "unreadable_task"
    )
    assert task_record["uncertain"] is True
    assert "digest" in task_record
    assert task_record["evidence"] is not None


def test_audit_equals_core_for_invalid_utf8_lock_artifact(project_dir, base_modules):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    invalid_utf8 = project_dir / repository.lock_path("sample_tool.py")
    invalid_utf8.write_bytes(b"\xff\xfe\xfa")

    service_report = service.audit()
    core_report = core.audit_source_locks()

    assert service_report == core_report
    invalid_entries = [
        item
        for item in service_report["categories"]["invalid"]
        if item["reason"] == "unreadable_lock"
    ]
    assert len(invalid_entries) == 1
    assert invalid_entries[0]["evidence"]["raw_hex"] == b"\xff\xfe\xfa".hex()


def test_audit_equals_core_for_malformed_json_lock_artifact(project_dir, base_modules):
    core, repository, service = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    malformed_json = project_dir / repository.lock_path("sample_tool.py")
    malformed_json.write_text("{invalid", encoding="utf-8")

    service_report = service.audit()
    core_report = core.audit_source_locks()

    assert service_report == core_report
    invalid_entries = [
        item
        for item in service_report["categories"]["invalid"]
        if item["reason"] == "unreadable_lock"
    ]
    assert len(invalid_entries) == 1
    assert invalid_entries[0]["evidence"]["raw_hex"] == "{invalid".encode().hex()
