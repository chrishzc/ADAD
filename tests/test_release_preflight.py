import hashlib
import importlib.util
import json
from pathlib import Path


SOURCE = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "release_preflight.py"
)
SPEC = importlib.util.spec_from_file_location("release_preflight", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _task_and_manifest(tmp_path: Path, *, approved=True):
    task = tmp_path / "node.task.json"
    payload = {
        "task_id": "node@v1@abcdef",
        "status": "approved" if approved else "assigned",
    }
    raw = json.dumps(payload).encode()
    task.write_bytes(raw)
    manifest = {
        "manifest_valid": True,
        "candidate_tree_hash": "a" * 40,
        "blockers": [],
        "release_manifest": {
            "version": "1.6.4",
            "task_authorization_evidence": [
                {
                    "task_id": "node@v1@abcdef",
                    "snapshot_sha256": hashlib.sha256(raw).hexdigest(),
                }
            ],
        },
    }
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    return task, manifest_path, manifest


def test_manifest_and_task_evidence_must_match(tmp_path):
    task, manifest_path, manifest = _task_and_manifest(tmp_path)

    loaded, tree_hash, version = MODULE._strict_manifest(manifest_path)
    evidence = MODULE._task_evidence(loaded, [task])

    assert tree_hash == "a" * 40
    assert version == "1.6.4"
    assert evidence == [(task, "node@v1@abcdef")]


def test_task_digest_drift_is_rejected(tmp_path):
    task, manifest_path, _ = _task_and_manifest(tmp_path)
    task.write_text('{"task_id":"node@v1@abcdef","status":"approved","drift":true}')
    loaded, _, _ = MODULE._strict_manifest(manifest_path)

    try:
        MODULE._task_evidence(loaded, [task])
    except MODULE.PreflightError as exc:
        assert "evidence mismatch" in str(exc)
    else:
        raise AssertionError("Task digest drift must fail closed")


def test_invalid_manifest_is_rejected_before_workspace_creation(tmp_path):
    _, manifest_path, manifest = _task_and_manifest(tmp_path)
    manifest["manifest_valid"] = False
    manifest["blockers"] = [{"code": "test"}]
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")

    try:
        MODULE._strict_manifest(manifest_path)
    except MODULE.PreflightError as exc:
        assert "not a valid release candidate" in str(exc)
    else:
        raise AssertionError("blocked manifest must fail closed")


def test_timeout_budget_is_checked_before_owned_root(tmp_path, monkeypatch):
    task, manifest_path, _ = _task_and_manifest(tmp_path)
    monkeypatch.setattr(
        MODULE,
        "_git",
        lambda *_args, **_kwargs: {
            "returncode": 0,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "interrupted": False,
            "duration_seconds": 0,
        },
    )
    called = {"mkdtemp": False}

    def forbidden_mkdtemp(*_args, **_kwargs):
        called["mkdtemp"] = True
        raise AssertionError("owned root must not be created")

    monkeypatch.setattr(MODULE.tempfile, "mkdtemp", forbidden_mkdtemp)

    try:
        MODULE.run_preflight(
            manifest_path=manifest_path,
            project_root=tmp_path,
            project_python=Path(__file__),
            base_revision="HEAD",
            task_snapshot_paths=[task],
            pytest_timeout=60,
            gate_timeout=30,
            build_timeout=30,
            outer_timeout=100,
        )
    except MODULE.PreflightError as exc:
        assert "timeout budget" in str(exc)
    else:
        raise AssertionError("invalid timeout budget must fail")
    assert called["mkdtemp"] is False


def test_failure_receipt_preserves_owned_root(tmp_path):
    receipt = MODULE._failure(
        "b" * 40,
        [{"name": "pytest", "returncode": 1}],
        [],
        tmp_path,
        "preserved_command_failed",
        {"stage": "pytest"},
    )

    assert receipt["release_ready"] is False
    assert receipt["cleanup_status"] == "preserved_command_failed"
    assert receipt["preserved_paths"] == [str(tmp_path)]
    assert receipt["manual_action_required"] is True


def test_artifact_evidence_requires_versioned_wheel_and_sdist(tmp_path):
    (tmp_path / "adad-1.6.4-py3-none-any.whl").write_bytes(b"wheel")
    (tmp_path / "adad-1.6.4.tar.gz").write_bytes(b"sdist")

    evidence = MODULE._artifact_evidence(tmp_path, "1.6.4")

    assert {item["filename"] for item in evidence} == {
        "adad-1.6.4-py3-none-any.whl",
        "adad-1.6.4.tar.gz",
    }
    assert all(len(item["sha256"]) == 64 for item in evidence)
