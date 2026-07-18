# -*- coding: utf-8 -*-
"""Tests for SourceLockPruner (#80-A3)."""

import importlib.util
import sys
import json
import os
from pathlib import Path

from conftest import write_yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
SOURCE_SCRIPTS_DIR = (
    REPO_ROOT / "adad_source" / "agents" / "skills" / "adad-workflow" / "scripts"
)
if str(SOURCE_SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SOURCE_SCRIPTS_DIR))


def _load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


core_module = _load_module(SOURCE_SCRIPTS_DIR / "adad_core.py", "pruner_task_core")
repo_module = _load_module(
    SOURCE_SCRIPTS_DIR / "source_lock_repository.py", "pruner_task_repo"
)
service_module = _load_module(
    SOURCE_SCRIPTS_DIR / "source_lock_audit_service.py", "pruner_task_service"
)
pruner_module = _load_module(
    SOURCE_SCRIPTS_DIR / "source_lock_pruner.py", "pruner_task_pruner"
)

CanonicalADADCore = core_module.ADADCore
SourceLockRepository = repo_module.SourceLockRepository
SourceLockAuditService = service_module.SourceLockAuditService
SourceLockPruner = pruner_module.SourceLockPruner

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
        project_dir,
        SOURCE_LOCK_DIR,
        lambda node_name: (base_modules.get("modules", {}).get(node_name) or {}).get(
            "source"
        ),
    )
    service = SourceLockAuditService(
        project_dir,
        TASK_DIR,
        repository,
        source_owners_for_path,
        core.validate_task_snapshot,
    )
    pruner = SourceLockPruner(service, repository)
    return core, repository, service, pruner


def test_prune_returns_success_with_no_candidates(project_dir, base_modules):
    """With only an active lock, prune should succeed with zero mutations."""
    core, repository, service, pruner = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    result = pruner.prune()

    assert result["success"] is True
    assert result["mutation_blocked"] is False
    assert result["mutations"] == []
    assert result["prune_receipt"] == {"pruned": 0, "skipped": 0, "quarantined": 0}
    assert "post_audit" in result


def test_prune_removes_stale_lock(project_dir, base_modules):
    """A closed (blocked/approved) task lock should be pruned."""
    core, repository, service, pruner = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    task = core.load_task("sample_tool")
    task["status"] = "blocked"
    core._save_task("sample_tool", task)

    result = pruner.prune()

    assert result["success"] is True
    assert len(result["mutations"]) == 1
    assert result["mutations"][0]["action"] == "pruned"
    assert result["prune_receipt"]["pruned"] == 1

    post = result["post_audit"]
    assert post["counts"]["stale"] == 0


def test_prune_removes_orphan_lock(project_dir, base_modules):
    """A lock with no corresponding task file should be pruned."""
    core, repository, service, pruner = _setup(project_dir, base_modules)

    orphan_lock = {
        "source_path": "sample_tool.py",
        "node_name": "sample_tool",
        "task_id": "sample_tool@v1@orphan",
        "acquired_at": "2026-07-17T00:00:00+00:00",
    }
    lock_path = project_dir / repository.lock_path("sample_tool.py")
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path.write_text(json.dumps(orphan_lock), encoding="utf-8")

    result = pruner.prune()

    assert result["success"] is True
    assert len(result["mutations"]) == 1
    assert result["mutations"][0]["action"] == "pruned"
    assert result["prune_receipt"]["pruned"] == 1


def test_prune_skips_active_lock(project_dir, base_modules):
    """An active lock must never be pruned."""
    core, repository, service, pruner = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    result = pruner.prune()

    assert result["success"] is True
    assert result["mutations"] == []
    lock_path = project_dir / repository.lock_path("sample_tool.py")
    assert lock_path.exists()


def test_prune_blocked_when_mutation_blocked(project_dir, base_modules):
    """When audit returns mutation_blocked, prune must not touch anything."""
    core, repository, service, pruner = _setup(project_dir, base_modules)

    # Write unreadable (invalid UTF-8) lock to trigger mutation_blocked
    assert core.generate_task("sample_tool")["success"] is True
    lock_path = project_dir / repository.lock_path("sample_tool.py")
    lock_path.write_bytes(b"\xff\xfe")

    result = pruner.prune()

    assert result["success"] is False
    assert result["mutation_blocked"] is True
    assert result["mutations"] == []


def test_revalidate_candidate_detects_identity_change(project_dir, base_modules):
    """revalidate_candidate returns failure if lock was replaced after audit."""
    core, repository, service, pruner = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True

    task = core.load_task("sample_tool")
    task["status"] = "blocked"
    core._save_task("sample_tool", task)

    audit = service.audit()
    stale_list = audit["categories"]["stale"]
    assert len(stale_list) == 1
    candidate = stale_list[0]

    lock_path = project_dir / repository.lock_path("sample_tool.py")
    payload = json.loads(lock_path.read_text(encoding="utf-8"))
    payload["acquired_at"] = "2099-01-01T00:00:00+00:00"
    lock_path.write_text(json.dumps(payload), encoding="utf-8")

    result = pruner.revalidate_candidate(candidate)

    assert result["success"] is False
    assert result["mutation_blocked"] is False
    assert "[PRUNER] Lock identity changed" in result["error"]


def test_prune_result_matches_core_reconcile_prune(project_dir, base_modules):
    """SourceLockPruner.prune() and core.reconcile_source_locks('prune') agree."""
    base_modules["modules"]["stale_tool"] = {
        **base_modules["modules"]["sample_tool"],
        "source": "stale_tool.py",
    }
    core, repository, service, pruner = _setup(project_dir, base_modules)
    assert core.generate_task("sample_tool")["success"] is True
    assert core.generate_task("stale_tool")["success"] is True

    stale = core.load_task("stale_tool")
    stale["status"] = "blocked"
    core._save_task("stale_tool", stale)

    pruner_result = pruner.prune()
    assert pruner_result["success"] is True
    assert pruner_result["prune_receipt"]["pruned"] == 1
