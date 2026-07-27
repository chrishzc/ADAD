#!/usr/bin/env python3
"""Build fail-closed release evidence from an immutable Git candidate tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import subprocess
import sys
from typing import Any, Iterable

import yaml


VERSION_PATH = "adad_cli/__init__.py"
VERSION_RE = re.compile(r'^__version__\s*=\s*["\']([^"\']+)["\']', re.MULTILINE)


class ManifestError(RuntimeError):
    """An expected contract blocker."""


def _git(project_root: Path, *args: str, text: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["git", "-C", str(project_root), *args],
        check=False,
        capture_output=True,
        text=text,
        shell=False,
    )


def _normalize_path(value: str) -> str:
    raw = value.replace("\\", "/").strip()
    if raw.startswith("/") or re.match(r"^[A-Za-z]:/", raw):
        raise ManifestError(f"invalid project-relative path: {value}")
    parts = PurePosixPath(raw).parts
    if not parts or any(part in {"", ".", ".."} for part in parts):
        raise ManifestError(f"invalid project-relative path: {value}")
    normalized = "/".join(parts)
    return normalized


def _resolve_tree(project_root: Path, mode: str, revision: str | None) -> str:
    if mode == "commit":
        if not revision:
            raise ManifestError("candidate_revision is required for candidate_mode=commit")
        result = _git(project_root, "rev-parse", "--verify", f"{revision}^{{tree}}")
    elif mode == "staged_index":
        if revision:
            raise ManifestError(
                "candidate_revision must be omitted for candidate_mode=staged_index"
            )
        unmerged = _git(project_root, "ls-files", "-u")
        if unmerged.returncode != 0:
            raise ManifestError(f"unable to inspect index: {unmerged.stderr.strip()}")
        if unmerged.stdout.strip():
            raise ManifestError("staged index contains unmerged entries")
        result = _git(project_root, "write-tree")
    else:
        raise ManifestError(f"unsupported candidate_mode: {mode}")
    if result.returncode != 0:
        raise ManifestError(result.stderr.strip() or "unable to resolve candidate tree")
    tree_hash = result.stdout.strip()
    if not re.fullmatch(r"[0-9a-fA-F]{40,64}", tree_hash):
        raise ManifestError("Git returned an invalid candidate tree identity")
    return tree_hash.lower()


def _tree_entries(project_root: Path, tree_hash: str) -> dict[str, dict[str, str]]:
    result = _git(project_root, "ls-tree", "-r", "-z", tree_hash, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(stderr or "unable to enumerate candidate tree")
    entries: dict[str, dict[str, str]] = {}
    for record in result.stdout.split(b"\0"):
        if not record:
            continue
        metadata, raw_path = record.split(b"\t", 1)
        mode, kind, object_id = metadata.decode("ascii").split(" ", 2)
        path = raw_path.decode("utf-8", errors="strict")
        entries[path] = {"mode": mode, "type": kind, "blob_hash": object_id}
    return entries


def _blob_bytes(project_root: Path, object_id: str) -> bytes:
    result = _git(project_root, "cat-file", "blob", object_id, text=False)
    if result.returncode != 0:
        stderr = result.stderr.decode("utf-8", errors="replace").strip()
        raise ManifestError(stderr or f"unable to read Git blob {object_id}")
    return result.stdout


def _parse_allowed_files(raw_value: Any) -> set[str]:
    if isinstance(raw_value, list):
        values = raw_value
    elif isinstance(raw_value, str) and raw_value.startswith("[") and raw_value.endswith("]"):
        values = [item.strip() for item in raw_value[1:-1].split(",")]
    else:
        values = []
    return {_normalize_path(str(value)) for value in values if str(value).strip()}


def _load_checkpoint_evidence(
    project_root: Path,
    task: dict[str, Any],
    approval: dict[str, Any],
    task_path: Path,
) -> tuple[str, str]:
    checkpoint_raw = approval.get("checkpoint_path")
    if not isinstance(checkpoint_raw, str) or not checkpoint_raw:
        raise ManifestError(f"Task approval checkpoint metadata is incomplete: {task_path}")
    checkpoint_path = Path(checkpoint_raw)
    if not checkpoint_path.is_absolute():
        checkpoint_path = project_root / checkpoint_path
    checkpoint_path = checkpoint_path.resolve()
    try:
        checkpoint_bytes = checkpoint_path.read_bytes()
        checkpoint = yaml.safe_load(checkpoint_bytes.decode("utf-8", errors="strict"))
    except (OSError, UnicodeError, yaml.YAMLError) as exc:
        raise ManifestError(
            f"invalid approval checkpoint {checkpoint_path}: {exc}"
        ) from exc
    payload = checkpoint.get("checkpoint_payload") if isinstance(checkpoint, dict) else None
    if not isinstance(payload, dict):
        raise ManifestError(f"approval checkpoint payload is invalid: {checkpoint_path}")
    target = payload.get("target")
    decision = payload.get("decision")
    expected_target = {
        "node_name": task.get("node_name"),
        "task_id": task.get("task_id"),
        "system_map_version": task.get("system_map_version"),
        "source_hash": task.get("source_hash"),
    }
    if (
        payload.get("id") != approval.get("checkpoint_id")
        or payload.get("triggered_by") != "human"
        or payload.get("status") != "approved"
        or not isinstance(decision, dict)
        or decision.get("action") != "approved"
        or not isinstance(target, dict)
        or any(target.get(key) != value for key, value in expected_target.items())
    ):
        raise ManifestError(
            f"approval checkpoint does not match Task snapshot: {checkpoint_path}"
        )
    return str(payload["id"]), hashlib.sha256(checkpoint_bytes).hexdigest()


def _load_task_evidence(
    task_paths: Iterable[str],
    project_root: Path,
    entries: dict[str, dict[str, str]],
) -> tuple[list[dict[str, Any]], set[str]]:
    evidence: list[dict[str, Any]] = []
    authorized_files: set[str] = set()
    for raw_path in task_paths:
        path = Path(raw_path).resolve()
        try:
            payload_bytes = path.read_bytes()
            task = json.loads(payload_bytes.decode("utf-8", errors="strict"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise ManifestError(f"invalid Task snapshot {path}: {exc}") from exc
        if task.get("status") != "approved":
            raise ManifestError(f"Task snapshot is not approved: {path}")
        approved_hash = task.get("approved_implementation_hash")
        if not isinstance(approved_hash, str) or not re.fullmatch(
            r"[0-9a-fA-F]{64}", approved_hash
        ):
            raise ManifestError(f"Task snapshot lacks approved implementation hash: {path}")
        approved_events = [
            event
            for event in task.get("history", [])
            if isinstance(event, dict) and event.get("event") == "approved"
        ]
        if not approved_events:
            raise ManifestError(f"Task snapshot lacks approval checkpoint metadata: {path}")
        approval = approved_events[-1]
        if not approval.get("checkpoint_id") or not approval.get("checkpoint_path"):
            raise ManifestError(f"Task approval checkpoint metadata is incomplete: {path}")
        source_lock = task.get("source_lock")
        rollback = task.get("rollback")
        if not isinstance(source_lock, dict) or not isinstance(rollback, dict):
            raise ManifestError(f"Task snapshot lacks canonical source metadata: {path}")
        source_path = _normalize_path(str(source_lock.get("source_path", "")))
        rollback_path = _normalize_path(str(rollback.get("source_path", "")))
        if source_path != rollback_path:
            raise ManifestError(f"Task canonical source paths do not match: {path}")
        source_entry = entries.get(source_path)
        if not source_entry or source_entry.get("type") != "blob":
            raise ManifestError(
                f"Task canonical source is absent from candidate tree: {source_path}"
            )
        candidate_source_sha256 = hashlib.sha256(
            _blob_bytes(project_root, source_entry["blob_hash"])
        ).hexdigest()
        if candidate_source_sha256 != approved_hash.lower():
            raise ManifestError(
                f"candidate source does not match approved implementation: {source_path}"
            )
        checkpoint_id, checkpoint_sha256 = _load_checkpoint_evidence(
            project_root, task, approval, path
        )
        target_input = (
            task.get("spec", {}).get("target_node", {}).get("input", {})
            if isinstance(task.get("spec"), dict)
            else {}
        )
        authorized_files.update(_parse_allowed_files(target_input.get("allowed_files")))
        evidence.append(
            {
                "task_id": task.get("task_id"),
                "node_name": task.get("node_name"),
                "snapshot_sha256": hashlib.sha256(payload_bytes).hexdigest(),
                "canonical_source_path": source_path,
                "candidate_source_sha256": candidate_source_sha256,
                "approved_implementation_hash": approved_hash.lower(),
                "checkpoint_id": checkpoint_id,
                "checkpoint_sha256": checkpoint_sha256,
            }
        )
    return evidence, authorized_files


def _dirty_required_tests(
    project_root: Path,
    mode: str,
    tree_hash: str,
    required_tests: list[str],
) -> set[str]:
    if not required_tests:
        return set()
    if mode == "staged_index":
        result = _git(project_root, "diff", "--name-only", "--", *required_tests)
    else:
        result = _git(
            project_root,
            "diff",
            "--name-only",
            tree_hash,
            "--",
            *required_tests,
        )
    if result.returncode != 0:
        raise ManifestError(result.stderr.strip() or "unable to inspect required test drift")
    return {_normalize_path(line) for line in result.stdout.splitlines() if line.strip()}


def build_manifest(
    *,
    project_root: Path,
    candidate_mode: str,
    candidate_revision: str | None,
    version: str,
    approved_task_snapshots: list[str],
    expected_release_files: list[str],
    required_test_files: list[str],
    source_replica_groups: list[list[str]],
) -> dict[str, Any]:
    blockers: list[dict[str, Any]] = []
    tree_hash = _resolve_tree(project_root, candidate_mode, candidate_revision)
    entries = _tree_entries(project_root, tree_hash)
    expected = [_normalize_path(path) for path in expected_release_files]
    required_tests = [_normalize_path(path) for path in required_test_files]
    replica_groups = [
        [_normalize_path(path) for path in group]
        for group in source_replica_groups
    ]
    task_evidence, authorized_files = _load_task_evidence(
        approved_task_snapshots, project_root, entries
    )

    inspected_paths = sorted(set([VERSION_PATH, *expected, *required_tests, *sum(replica_groups, [])]))
    file_evidence: dict[str, dict[str, Any]] = {}
    for path in inspected_paths:
        entry = entries.get(path)
        file_evidence[path] = {
            "present": entry is not None,
            "blob_hash": entry.get("blob_hash") if entry else None,
        }

    for path in expected:
        if path not in entries:
            blockers.append({"code": "expected_file_missing", "path": path})
    for path in required_tests:
        if path not in entries:
            blockers.append({"code": "required_test_missing", "path": path})
        if path not in authorized_files:
            blockers.append({"code": "required_test_not_authorized", "path": path})

    dirty_tests = _dirty_required_tests(
        project_root, candidate_mode, tree_hash, required_tests
    )
    for path in sorted(dirty_tests):
        blockers.append({"code": "required_test_not_in_candidate", "path": path})

    for group_index, group in enumerate(replica_groups):
        hashes = [entries.get(path, {}).get("blob_hash") for path in group]
        if any(object_id is None for object_id in hashes):
            blockers.append(
                {"code": "replica_file_missing", "group_index": group_index, "paths": group}
            )
        elif len(set(hashes)) != 1:
            blockers.append(
                {"code": "replica_hash_mismatch", "group_index": group_index, "paths": group}
            )

    version_entry = entries.get(VERSION_PATH)
    actual_version = None
    if version_entry:
        version_text = _blob_bytes(project_root, version_entry["blob_hash"]).decode(
            "utf-8", errors="strict"
        )
        match = VERSION_RE.search(version_text)
        actual_version = match.group(1) if match else None
    if actual_version != version:
        blockers.append(
            {
                "code": "version_mismatch",
                "expected": version,
                "actual": actual_version,
                "path": VERSION_PATH,
            }
        )

    manifest_valid = not blockers
    return {
        "manifest_valid": manifest_valid,
        "candidate_tree_hash": tree_hash,
        "release_manifest": {
            "version": version,
            "candidate_mode": candidate_mode,
            "candidate_revision": candidate_revision,
            "files": file_evidence,
            "task_authorization_evidence": task_evidence,
            "source_replica_groups": replica_groups,
        },
        "blockers": blockers,
        "manual_action_required": not manifest_valid,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--candidate-mode", required=True, choices=("commit", "staged_index"))
    parser.add_argument("--candidate-revision")
    parser.add_argument("--version", required=True)
    parser.add_argument("--task-snapshot", action="append", default=[])
    parser.add_argument("--expected-file", action="append", default=[])
    parser.add_argument("--required-test-file", action="append", default=[])
    parser.add_argument("--replica-group", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        groups = [
            [item.strip() for item in raw_group.split(",") if item.strip()]
            for raw_group in args.replica_group
        ]
        result = build_manifest(
            project_root=Path.cwd(),
            candidate_mode=args.candidate_mode,
            candidate_revision=args.candidate_revision,
            version=args.version,
            approved_task_snapshots=args.task_snapshot,
            expected_release_files=args.expected_file,
            required_test_files=args.required_test_file,
            source_replica_groups=groups,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["manifest_valid"] else 1
    except ManifestError as exc:
        print(
            json.dumps(
                {
                    "manifest_valid": False,
                    "candidate_tree_hash": None,
                    "release_manifest": {},
                    "blockers": [{"code": "contract_error", "error": str(exc)}],
                    "manual_action_required": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 1
    except BaseException as exc:
        print(
            json.dumps(
                {
                    "manifest_valid": False,
                    "candidate_tree_hash": None,
                    "release_manifest": {},
                    "blockers": [
                        {"code": "internal_error", "error": f"{type(exc).__name__}: {exc}"}
                    ],
                    "manual_action_required": True,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
        return 2


if __name__ == "__main__":
    sys.exit(main())
