# -*- coding: utf-8 -*-
import importlib.util
import hashlib
import json
import os
import sys
import builtins
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = (
    REPO_ROOT
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
)
CORE_PATH = SCRIPTS_DIR / "adad_core.py"
REPOSITORY_PATH = SCRIPTS_DIR / "source_lock_repository.py"
LOCK_DIR = os.path.join(".agents", "tasks", ".source_locks")


def _load(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


sys.path.insert(0, str(SCRIPTS_DIR))
core_module = _load(CORE_PATH, "source_lock_repository_parity_core")
repository_module = _load(REPOSITORY_PATH, "source_lock_repository_under_test")
ADADCore = core_module.ADADCore
SourceLockRepository = repository_module.SourceLockRepository


def _repository(project_root, source_path="sample_tool.py"):
    return SourceLockRepository(
        project_root,
        LOCK_DIR,
        lambda node_name: source_path if node_name in {"sample_tool", "other_tool"} else None,
    )


def _write_lock(project_root, repository, payload):
    path = project_root / repository.lock_path(payload["source_path"])
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return path


def _without_artifact_details(value):
    if isinstance(value, dict):
        return {
            key: _without_artifact_details(item)
            for key, item in value.items()
            if key
            not in {
                "path",
                "canonical_path",
                "quarantine_path",
                "identity",
                "after_identity",
                "cleanup",
            }
        }
    if isinstance(value, list):
        return [_without_artifact_details(item) for item in value]
    return value


def test_direct_parity_for_path_read_identity_and_release(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    core = ADADCore(tmp_path / "system_map.yaml", check_validity=False)
    repository = _repository(tmp_path)
    payload = {
        "source_path": "sample_tool.py",
        "node_name": "sample_tool",
        "task_id": "sample_tool@v1@abcdef",
        "acquired_at": "2026-07-16T00:00:00+00:00",
    }
    path = _write_lock(tmp_path, repository, payload)

    assert repository.lock_path(payload["source_path"]) == core._source_lock_path(
        payload["source_path"]
    )
    assert repository.read(payload["source_path"]) == core._read_source_lock(
        payload["source_path"]
    )
    assert repository.identity(path) == core._source_lock_identity(path)

    task_data = {
        "node_name": payload["node_name"],
        "task_id": payload["task_id"],
        "source_lock": payload,
    }
    repository_result = repository.release(task_data)
    _write_lock(tmp_path, repository, payload)
    core_result = core._release_source_lock(task_data)
    assert _without_artifact_details(repository_result) == _without_artifact_details(
        core_result
    )


def test_acquire_is_exclusive_and_same_node_reissue_replaces_payload(tmp_path):
    repository = _repository(tmp_path)

    first = repository.acquire("sample_tool", "sample_tool@v1@first")
    conflict = repository.acquire("other_tool", "other_tool@v1@second")
    reissued = repository.acquire("sample_tool", "sample_tool@v1@third")
    path = tmp_path / repository.lock_path("sample_tool.py")

    assert first["success"] is True
    assert conflict["success"] is False
    assert conflict["conflict"] == first["lock"]
    assert reissued["success"] is True
    assert json.loads(path.read_text(encoding="utf-8")) == reissued["lock"]
    assert not list(path.parent.glob("*.tmp-*"))


def test_release_permission_failure_preserves_canonical_lock(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    acquired = repository.acquire("sample_tool", "sample_tool@v1@abcdef")
    task_data = {
        "node_name": "sample_tool",
        "task_id": "sample_tool@v1@abcdef",
        "source_lock": acquired["lock"],
    }
    path = tmp_path / repository.lock_path("sample_tool.py")

    def deny_rename(source, target):
        raise PermissionError("denied")

    monkeypatch.setattr(repository_module.os, "rename", deny_rename)
    result = repository.release(task_data)

    assert result["success"] is False
    assert result["result"] == "error"
    assert "Quarantine rename failed" in result["error"]
    assert path.exists()


def test_release_succeeds_and_preserves_competitor_sentinel_quarantine(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    acquired = repository.acquire("sample_tool", "sample_tool@v1@abcdef")
    task_data = {
        "node_name": "sample_tool",
        "task_id": "sample_tool@v1@abcdef",
        "source_lock": acquired["lock"],
    }
    path = tmp_path / repository.lock_path("sample_tool.py")
    original_quarantine = repository.quarantine
    remove_calls = []

    def block_remove(path_to_remove):
        remove_calls.append(path_to_remove)
        raise AssertionError("os.remove should not be called")

    def quarantine_with_sentinel(source, expected):
        result = original_quarantine(source, expected)
        if result["success"]:
            with open(result["quarantine_path"], "wb") as handle:
                handle.write(b"COMPETITOR-SENTINEL-\xff")
        return result

    monkeypatch.setattr(repository, "quarantine", quarantine_with_sentinel)
    monkeypatch.setattr(repository_module.os, "remove", block_remove)
    result = repository.release(task_data)

    assert result["success"] is True
    assert result["result"] == "released"
    assert result["released"] is True
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert result["cleanup"]["status"] == "quarantine_retained"
    assert result["cleanup"]["quarantine_retained"] is True
    assert result["cleanup"]["canonical_cleared"] is True
    assert result["cleanup"]["artifact_deleted"] is False
    assert result["cleanup"]["delete_attempted"] is False
    assert result["cleanup"]["manual_action_required"] is False
    assert len(remove_calls) == 0
    assert not path.exists()
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == b"COMPETITOR-SENTINEL-\xff"


def test_quarantine_rejects_identity_race_without_deleting_new_lock(tmp_path):
    repository = _repository(tmp_path)
    first = repository.acquire("sample_tool", "sample_tool@v1@first")
    path = tmp_path / repository.lock_path("sample_tool.py")
    expected = repository.identity(path)
    replacement = dict(first["lock"])
    replacement["task_id"] = "sample_tool@v1@replacement"
    path.write_text(json.dumps(replacement), encoding="utf-8")

    result = repository.quarantine(path, expected)

    assert result["success"] is False
    assert result["result"] == "identity_mismatch"
    assert json.loads(path.read_text(encoding="utf-8")) == replacement
    assert not list(path.parent.glob("*.quarantine-*"))


def test_read_and_identity_fail_closed_for_invalid_payloads(tmp_path):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    path.parent.mkdir(parents=True)
    path.write_bytes(b"\xff")

    assert repository.read("sample_tool.py") == {
        "invalid": True,
        "path": repository.lock_path("sample_tool.py"),
    }
    invalid = repository.identity(path)
    assert invalid["success"] is False
    assert invalid["state"] == "invalid"
    assert invalid["uncertain"] is True

    path.write_text("[]", encoding="utf-8")
    assert repository.read("sample_tool.py")["invalid"] is True
    assert repository.identity(path)["error"] == "JSON payload must be an object."


def test_identity_invalid_utf8_bytes_preserve_raw_hex(tmp_path):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    path.parent.mkdir(parents=True)

    raw = b"\xff\x00invalid-utf8"
    path.write_bytes(raw)
    result = repository.identity(path)

    assert result["success"] is False
    assert result["state"] == "invalid"
    assert result["uncertain"] is True
    assert result["raw_hex"] == raw.hex()
    assert bytes.fromhex(result["raw_hex"]) == raw
    assert result["identity"] is not None
    assert result["path"] == os.path.abspath(path)
    assert result["payload_digest"] == hashlib.sha256(raw).hexdigest()
    assert isinstance(result["error"], str) and result["error"]


def test_identity_malformed_json_preserve_raw_hex(tmp_path):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    path.parent.mkdir(parents=True)

    raw = b"{invalid-json"
    path.write_bytes(raw)
    result = repository.identity(path)

    assert result["success"] is False
    assert result["state"] == "invalid"
    assert result["uncertain"] is True
    assert result["raw_hex"] == raw.hex()
    assert bytes.fromhex(result["raw_hex"]) == raw
    assert result["identity"] is not None
    assert result["path"] == os.path.abspath(path)
    assert result["payload_digest"] == hashlib.sha256(raw).hexdigest()
    assert isinstance(result["error"], str) and result["error"]


def test_read_only_treats_file_not_found_as_missing(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    real_open = builtins.open

    def deny_lock(path, *args, **kwargs):
        if os.fspath(path).endswith(".lock.json"):
            raise PermissionError("denied")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", deny_lock)
    denied = repository.read("sample_tool.py")

    assert denied["invalid"] is True
    assert denied["uncertain"] is True
    assert denied["state"] == "error"
    assert "denied" in denied["error"]

    monkeypatch.setattr(
        builtins,
        "open",
        lambda *args, **kwargs: (_ for _ in ()).throw(FileNotFoundError()),
    )
    assert repository.read("sample_tool.py") is None


def test_force_reissue_does_not_overwrite_competitor_after_quarantine(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@first")
    path = tmp_path / repository.lock_path("sample_tool.py")
    competitor = {
        "source_path": "sample_tool.py",
        "node_name": "other_tool",
        "task_id": "other_tool@v1@racer",
        "acquired_at": "2026-07-16T00:00:00+00:00",
    }
    real_open = repository_module.os.open
    exclusive_calls = 0

    def race_open(target, flags, mode=0o777):
        nonlocal exclusive_calls
        if os.fspath(target) == os.fspath(path) and flags & os.O_EXCL:
            exclusive_calls += 1
            if exclusive_calls == 2:
                descriptor = real_open(target, flags, mode)
                os.write(descriptor, json.dumps(competitor).encode("utf-8"))
                os.close(descriptor)
        return real_open(target, flags, mode)

    monkeypatch.setattr(repository_module.os, "open", race_open)
    result = repository.acquire("sample_tool", "sample_tool@v1@reissued")

    assert result["success"] is False
    assert result["result"] == "conflict"
    assert result["restore"]["attempted"] is False
    assert json.loads(path.read_text(encoding="utf-8")) == competitor
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1
    assert (
        json.loads(quarantines[0].read_text(encoding="utf-8"))["task_id"]
        == "sample_tool@v1@first"
    )


def test_force_reissue_rejects_raw_byte_sentinel_competitor(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@first")
    path = tmp_path / repository.lock_path("sample_tool.py")
    original_quarantine = repository.quarantine
    remove_calls = []

    def block_remove(path_to_remove):
        remove_calls.append(path_to_remove)
        raise AssertionError("os.remove should not be called")

    def quarantine_with_sentinel(source, expected):
        result = original_quarantine(source, expected)
        if result["success"]:
            with open(result["quarantine_path"], "wb") as handle:
                handle.write(b"COMPETITOR-SENTINEL-\xff")
        return result

    monkeypatch.setattr(repository, "quarantine", quarantine_with_sentinel)
    monkeypatch.setattr(repository_module.os, "remove", block_remove)
    result = repository.acquire("sample_tool", "sample_tool@v1@reissued")

    assert result["success"] is True
    assert result["reissued"] is True
    assert result["lock"]["task_id"] == "sample_tool@v1@reissued"
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert result["cleanup"]["status"] == "quarantine_retained"
    assert result["cleanup"]["quarantine_retained"] is True
    assert result["cleanup"]["canonical_cleared"] is True
    assert result["cleanup"]["artifact_deleted"] is False
    assert result["cleanup"]["delete_attempted"] is False
    assert result["cleanup"]["manual_action_required"] is False
    assert len(remove_calls) == 0
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes() == b"COMPETITOR-SENTINEL-\xff"


def test_exclusive_create_appends_raw_byte_sentinel_and_uses_cleanup_path(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    remove_calls = []

    def block_remove(path_to_remove):
        remove_calls.append(path_to_remove)
        raise AssertionError("os.remove should not be called")

    def append_raw_and_fail(descriptor):
        os.lseek(descriptor, 0, os.SEEK_END)
        os.write(descriptor, b"COMPETITOR-SENTINEL-\xff")
        raise PermissionError("fsync denied")

    monkeypatch.setattr(repository_module.os, "fsync", append_raw_and_fail)
    monkeypatch.setattr(repository_module.os, "remove", block_remove)
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["result"] == "error"
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is False
    assert result["cleanup"]["evidence"]["state"] == "invalid"
    assert result["cleanup"]["evidence"]["uncertain"] is True
    assert result["cleanup"]["evidence"]["raw_hex"].endswith("2dff")
    assert len(remove_calls) == 0
    assert path.exists()
    assert path.read_bytes().endswith(b"COMPETITOR-SENTINEL-\xff")
    assert not list(path.parent.glob("*.quarantine-*"))


def test_quarantine_restores_raw_byte_race_preserves_terminal_quarantine_copy(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    first = repository.acquire("sample_tool", "sample_tool@v1@first")
    path = tmp_path / repository.lock_path("sample_tool.py")
    expected = repository.identity(path)
    real_rename = repository_module.os.rename
    raced = False
    remove_calls = []

    def block_remove(path_to_remove):
        remove_calls.append(path_to_remove)
        raise AssertionError("os.remove should not be called")

    def race_rename_with_raw(source, target):
        nonlocal raced
        if not raced and os.fspath(source) == os.fspath(path):
            raced = True
            raw = json.dumps(first["lock"]).encode("utf-8") + b"COMPETITOR-SENTINEL-\xff"
            path.write_bytes(raw)
        return real_rename(source, target)

    monkeypatch.setattr(repository_module.os, "rename", race_rename_with_raw)
    monkeypatch.setattr(repository_module.os, "remove", block_remove)
    result = repository.quarantine(path, expected)

    assert result["success"] is False
    assert result["result"] == "identity_mismatch"
    assert result["restore"]["attempted"] is True
    assert result["restore"]["success"] is True
    assert path.read_bytes().endswith(b"COMPETITOR-SENTINEL-\xff")
    assert len(remove_calls) == 0
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1
    assert quarantines[0].read_bytes().endswith(b"COMPETITOR-SENTINEL-\xff")


def test_quarantine_restores_raced_artifact_without_overwrite(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    first = repository.acquire("sample_tool", "sample_tool@v1@first")
    path = tmp_path / repository.lock_path("sample_tool.py")
    expected = repository.identity(path)
    competitor = dict(first["lock"])
    competitor["task_id"] = "sample_tool@v1@competitor"
    real_rename = repository_module.os.rename
    raced = False

    def race_rename(source, target):
        nonlocal raced
        if not raced and os.fspath(source) == os.fspath(path):
            raced = True
            path.write_text(json.dumps(competitor), encoding="utf-8")
        return real_rename(source, target)

    monkeypatch.setattr(repository_module.os, "rename", race_rename)
    result = repository.quarantine(path, expected)

    assert result["success"] is False
    assert result["result"] == "identity_mismatch"
    assert result["restore"]["attempted"] is True
    assert result["restore"]["success"] is True
    assert json.loads(path.read_text(encoding="utf-8")) == competitor
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1
    assert json.loads(quarantines[0].read_text(encoding="utf-8")) == competitor


def test_exclusive_create_reports_identity_checked_partial_cleanup(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")

    monkeypatch.setattr(
        repository_module.os,
        "fsync",
        lambda descriptor: (_ for _ in ()).throw(PermissionError("fsync denied")),
    )
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["result"] == "error"
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert not path.exists()
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1


def test_exclusive_create_captures_fd_identity_before_writing(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")

    monkeypatch.setattr(
        repository_module.os,
        "fstat",
        lambda descriptor: (_ for _ in ()).throw(PermissionError("fstat denied")),
    )
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["cleanup"]["attempted"] is False
    assert "ownership is uncertain" in result["cleanup"]["error"]
    assert path.read_bytes() == b""


def test_exclusive_create_final_fstat_failure_cleans_only_owned_artifact(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    real_fstat = repository_module.os.fstat
    calls = 0

    def fail_final_fstat(descriptor):
        nonlocal calls
        calls += 1
        if calls == 2:
            raise PermissionError("final fstat denied")
        return real_fstat(descriptor)

    monkeypatch.setattr(repository_module.os, "fstat", fail_final_fstat)
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert not path.exists()


def test_exclusive_create_file_exists_error_after_open_is_a_write_failure(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")

    monkeypatch.setattr(
        repository_module.os,
        "fsync",
        lambda descriptor: (_ for _ in ()).throw(FileExistsError("write race")),
    )
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["result"] == "error"
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert not path.exists()
    quarantines = list(path.parent.glob("*.quarantine-*"))
    assert len(quarantines) == 1


def test_exclusive_create_preserves_replacement_before_final_validation(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    competitor = {
        "source_path": "sample_tool.py",
        "node_name": "other_tool",
        "task_id": "other_tool@v1@racer",
        "acquired_at": "2026-07-17T00:00:00+00:00",
    }
    real_identity = repository.identity
    identity_calls = 0

    def replace_before_validation(target):
        nonlocal identity_calls
        identity_calls += 1
        if identity_calls == 1:
            path.unlink()
            path.write_text(json.dumps(competitor), encoding="utf-8")
        return real_identity(target)

    monkeypatch.setattr(repository, "identity", replace_before_validation)
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["cleanup"]["attempted"] is False
    assert "not the descriptor-owned artifact" in result["cleanup"]["error"]
    assert json.loads(path.read_text(encoding="utf-8")) == competitor
    assert not list(path.parent.glob("*.quarantine-*"))


def test_exclusive_create_uncertain_cleanup_performs_no_mutation(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")

    monkeypatch.setattr(
        repository_module.os,
        "fsync",
        lambda descriptor: (_ for _ in ()).throw(PermissionError("fsync denied")),
    )
    monkeypatch.setattr(
        repository,
        "identity",
        lambda target: {
            "success": False,
            "state": "error",
            "uncertain": True,
            "path": os.fspath(target),
            "error": "lstat denied",
        },
    )
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["cleanup"]["attempted"] is False
    assert path.exists()
    assert not list(path.parent.glob("*.quarantine-*"))


def test_exclusive_create_rejects_digest_mismatch_before_success(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    path = tmp_path / repository.lock_path("sample_tool.py")
    real_identity = repository.identity
    identity_calls = 0

    def corrupt_first_digest(target):
        nonlocal identity_calls
        identity_calls += 1
        current = real_identity(target)
        if identity_calls == 1:
            current["payload_digest"] = "not-the-created-payload"
        return current

    monkeypatch.setattr(repository, "identity", corrupt_first_digest)
    result = repository.acquire("sample_tool", "sample_tool@v1@first")

    assert result["success"] is False
    assert result["cleanup"]["attempted"] is True
    assert result["cleanup"]["success"] is True
    assert not path.exists()


def test_flat_script_import_has_no_adad_core_dependency():
    source = REPOSITORY_PATH.read_text(encoding="utf-8")
    module = _load(REPOSITORY_PATH, "source_lock_repository_flat_script")

    assert "adad_core" not in source
    assert module.SourceLockRepository is not None


def _quarantine_receipt(repository, source_path="sample_tool.py"):
    canonical = Path(repository.project_root) / repository.lock_path(source_path)
    receipt = repository.quarantine(canonical, repository.identity(canonical))
    assert receipt["success"] is True
    return canonical, receipt


def test_restore_quarantine_preserves_exact_payload_and_is_idempotent(tmp_path):
    repository = _repository(tmp_path)
    acquired = repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)
    original = Path(receipt["quarantine_path"]).read_bytes()

    restored = repository.restore_quarantine(receipt)
    repeated = repository.restore_quarantine(receipt)

    assert restored["success"] is True
    assert canonical.read_bytes() == original
    assert json.loads(canonical.read_text(encoding="utf-8")) == acquired["lock"]
    assert Path(receipt["quarantine_path"]).read_bytes() == original
    assert repeated["success"] is False
    assert repeated["result"] == "occupied"
    assert canonical.read_bytes() == original


def test_restore_quarantine_rejects_receipt_and_artifact_drift(tmp_path):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)

    forged = dict(receipt)
    forged["payload_digest"] = "0" * 64
    assert repository.restore_quarantine(forged)["result"] == "identity_mismatch"
    assert not canonical.exists()

    Path(receipt["quarantine_path"]).write_bytes(b"drift")
    drifted = repository.restore_quarantine(receipt)
    assert drifted["success"] is False
    assert drifted["result"] == "identity_mismatch"
    assert not canonical.exists()


def test_restore_quarantine_fails_closed_for_canonical_uncertainty(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)
    real_identity = repository.identity

    def uncertain(path):
        if os.path.abspath(os.fspath(path)) == os.path.abspath(canonical):
            return {"success": False, "state": "error", "uncertain": True}
        return real_identity(path)

    monkeypatch.setattr(repository, "identity", uncertain)
    result = repository.restore_quarantine(receipt)

    assert result["success"] is False
    assert result["result"] == "error"
    assert result["attempted"] is False
    assert Path(receipt["quarantine_path"]).exists()


def test_restore_quarantine_reports_link_race_and_preserves_both_artifacts(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)
    competitor = b"competitor"

    def race_link(source, target):
        Path(target).write_bytes(competitor)
        raise FileExistsError("raced")

    monkeypatch.setattr(repository_module.os, "link", race_link)
    result = repository.restore_quarantine(receipt)

    assert result["success"] is False
    assert result["result"] == "conflict"
    assert canonical.read_bytes() == competitor
    assert Path(receipt["quarantine_path"]).exists()


def test_restore_quarantine_preserves_raw_invalid_artifact(tmp_path):
    repository = _repository(tmp_path)
    canonical = tmp_path / repository.lock_path("sample_tool.py")
    canonical.parent.mkdir(parents=True)
    canonical.write_bytes(b"[]")
    canonical, receipt = _quarantine_receipt(repository)

    result = repository.restore_quarantine(receipt)

    assert result["success"] is True
    assert canonical.read_bytes() == b"[]"
    assert Path(receipt["quarantine_path"]).read_bytes() == b"[]"


def test_restore_quarantine_rejects_raw_paths_traversal_and_symlink(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)

    assert repository.restore_quarantine(receipt["quarantine_path"])["result"] == (
        "invalid_receipt"
    )
    unsafe_receipts = [
        dict(receipt, canonical_path=str(tmp_path / "external.lock.json")),
        dict(receipt, quarantine_path=str(tmp_path / "external.quarantine")),
        dict(
            receipt,
            canonical_path=os.path.join(LOCK_DIR, "..", "x.lock.json"),
        ),
        dict(
            receipt,
            quarantine_path=os.path.join(
                LOCK_DIR, "..", "x.lock.json.quarantine-forged"
            ),
        ),
    ]

    def unsafe_touch(*args, **kwargs):
        raise AssertionError("lexical rejection must not touch candidate paths")

    with monkeypatch.context() as gate:
        gate.setattr(repository, "identity", unsafe_touch)
        gate.setattr(repository_module.os, "link", unsafe_touch)
        for unsafe_receipt in unsafe_receipts:
            rejected = repository.restore_quarantine(unsafe_receipt)
            assert rejected["result"] == "unsafe_path"
            assert rejected["attempted"] is False
            assert rejected["evidence"]["lock_root"] == os.path.abspath(
                tmp_path / LOCK_DIR
            )
            assert set(rejected["evidence"]) == {
                "lock_root",
                "canonical",
                "quarantine",
                "canonical_suffix",
                "quarantine_prefix",
            }
            for path_evidence in ("canonical", "quarantine"):
                assert set(rejected["evidence"][path_evidence]) == {
                    "raw",
                    "normalized",
                    "traversal",
                    "within_lock_dir",
                    "same_directory",
                }

    quarantine_path = Path(receipt["quarantine_path"])
    target = tmp_path / "target.lock.json"
    target.write_bytes(quarantine_path.read_bytes())
    quarantine_path.unlink()
    try:
        quarantine_path.symlink_to(target)
    except OSError:
        return
    linked = repository.restore_quarantine(receipt)
    assert linked["success"] is False
    assert linked["result"] == "identity_mismatch"
    assert not canonical.exists()


def test_restore_quarantine_rejects_canonical_symlink_without_following_target(
    tmp_path, monkeypatch
):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)
    target = tmp_path / "external-target.lock.json"
    target.write_bytes(b"do-not-read")
    try:
        canonical.symlink_to(target)
    except OSError:
        return
    real_open = builtins.open

    def deny_target(path, *args, **kwargs):
        if os.path.abspath(os.fspath(path)) == os.path.abspath(target):
            raise AssertionError("symlink target must not be opened")
        return real_open(path, *args, **kwargs)

    monkeypatch.setattr(builtins, "open", deny_target)
    monkeypatch.setattr(
        repository_module.os,
        "link",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            AssertionError("canonical symlink must not be replaced")
        ),
    )
    result = repository.restore_quarantine(receipt)

    assert result["success"] is False
    assert result["result"] == "occupied"
    assert result["attempted"] is False
    assert canonical.is_symlink()
    assert Path(receipt["quarantine_path"]).exists()


def test_restore_quarantine_never_calls_destructive_operations(tmp_path, monkeypatch):
    repository = _repository(tmp_path)
    repository.acquire("sample_tool", "sample_tool@v1@restore")
    canonical, receipt = _quarantine_receipt(repository)

    def forbidden(*args, **kwargs):
        raise AssertionError("destructive operation is forbidden")

    monkeypatch.setattr(repository_module.os, "remove", forbidden)
    monkeypatch.setattr(repository_module.os, "unlink", forbidden)
    monkeypatch.setattr(repository_module.os, "replace", forbidden)
    monkeypatch.setattr(repository_module.os, "rename", forbidden)

    result = repository.restore_quarantine(receipt)
    assert result["success"] is True
    assert canonical.exists()
    assert Path(receipt["quarantine_path"]).exists()
