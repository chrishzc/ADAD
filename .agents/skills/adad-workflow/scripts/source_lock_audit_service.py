# -*- coding: utf-8 -*-
"""Read-only Source Lock audit service extracted from #78.

The service mirrors the approved ADADCore Source Lock scan/classify/audit policy
without triggering any mutation operation.
"""

import os


class SourceLockAuditService:
    """Provide read-only Source Lock discovery and classification helpers."""

    def __init__(
        self,
        project_root,
        task_dir,
        repository,
        source_owners_for_path,
        validate_task_snapshot,
    ):
        self.project_root = os.path.realpath(os.fspath(project_root))
        self.task_dir = os.path.normpath(
            os.path.join(self.project_root, os.fspath(task_dir))
        )
        self.repository = repository
        self.source_owners_for_path = source_owners_for_path
        self.validate_task_snapshot = validate_task_snapshot

    def _relpath(self, path):
        return os.path.relpath(path, self.project_root).replace("\\", "/")

    def _source_lock_path(self, source_path):
        return self.repository.lock_path(source_path)

    def _is_uncertain_artifact(self, artifact):
        if artifact.get("uncertain"):
            return True
        if artifact.get("state") != "invalid":
            return False
        error = artifact.get("error") or ""
        return "JSON payload must be an object." not in error

    def _artifact_evidence(self, artifact):
        evidence = artifact.get("evidence")
        if evidence is not None:
            return evidence
        if artifact.get("state") == "invalid":
            error = artifact.get("error") or ""
            if "JSON payload must be an object." not in error:
                return {
                    "path": artifact.get("path"),
                    "state": "invalid",
                    "error": error,
                    "identity": artifact.get("identity"),
                    "payload_digest": artifact.get("payload_digest"),
                    "raw_hex": artifact.get("raw_hex"),
                }
        return artifact

    def scan_state(self):
        task_dir = self.task_dir
        lock_dir = os.path.join(self.project_root, self.repository.lock_dir)
        synthetic = []
        mutation_blocked = False

        def scan(directory, suffix, kind):
            nonlocal mutation_blocked
            try:
                with os.scandir(directory) as iterator:
                    return sorted(
                        [entry.path for entry in iterator if entry.name.endswith(suffix)]
                    )
            except FileNotFoundError:
                return []
            except OSError as exc:
                mutation_blocked = True
                synthetic.append(
                    {
                        "classification": "invalid",
                        "reason": f"{kind}_directory_scan_failed",
                        "canonical_path": os.path.abspath(directory),
                        "uncertain": True,
                        "error": str(exc),
                        "mutation_eligible": False,
                    }
                )
                return None

        task_paths = scan(task_dir, ".task.json", "task")
        lock_paths = scan(lock_dir, ".lock.json", "lock")

        if lock_paths is not None:
            for path in lock_paths:
                probe = self.repository.identity(path)
                if not probe["success"] and self._is_uncertain_artifact(probe):
                    mutation_blocked = True

        snapshots = {}
        if task_paths is not None:
            for path in task_paths:
                node_name = os.path.basename(path)[:-len(".task.json")]
                artifact = self.repository.identity(path)
                if not artifact["success"]:
                    artifact_uncertain = self._is_uncertain_artifact(artifact)
                    if artifact_uncertain:
                        mutation_blocked = True
                    snapshots[node_name] = {
                        "data": None,
                        "path": path,
                        "artifact": artifact,
                        "validation": {
                            "valid": False,
                            "errors": [artifact["error"]],
                        },
                    }
                    continue
                validation = self.validate_task_snapshot(artifact["payload"], node_name)
                snapshots[node_name] = {
                    "data": artifact["payload"],
                    "path": path,
                    "artifact": artifact,
                    "validation": validation,
                }

        return {
            "healthy": (
                task_paths is not None and lock_paths is not None and not mutation_blocked
            ),
            "mutation_blocked": mutation_blocked,
            "task_listing_complete": task_paths is not None,
            "lock_listing_complete": lock_paths is not None,
            "task_snapshots": snapshots,
            "lock_paths": lock_paths or [],
            "synthetic_invalid": synthetic,
        }

    def classify(self, lock_path, scan_state=None):
        """Classify one physical Source Lock without mutating either artifact."""
        lock_path = os.path.abspath(os.fspath(lock_path))
        scan_state = scan_state or self.scan_state()
        task_snapshots = scan_state["task_snapshots"]
        entry = {
            "classification": "invalid",
            "canonical_path": lock_path,
            "lock_path": self._relpath(lock_path),
            "mutation_eligible": False,
        }
        artifact = self.repository.identity(lock_path)
        if not artifact["success"]:
            entry["reason"] = "unreadable_lock"
            entry["error"] = artifact["error"]
            entry["uncertain"] = self._is_uncertain_artifact(artifact)
            entry["identity"] = artifact.get("identity")
            entry["lstat_identity"] = artifact.get("identity")
            entry["payload_digest"] = artifact.get("payload_digest")
            entry["evidence"] = self._artifact_evidence(artifact)
            return entry

        lock = artifact["payload"]
        entry["lstat_identity"] = artifact["identity"]
        entry["payload_digest"] = artifact["payload_digest"]
        entry["lock_identity"] = artifact["payload_digest"]
        for field in ("source_path", "node_name", "task_id", "acquired_at"):
            value = lock.get(field)
            if not isinstance(value, str) or not value:
                entry.update(lock)
                entry["reason"] = f"missing_lock_field:{field}"
                return entry

        entry.update(lock)
        expected_name = os.path.basename(self._source_lock_path(lock["source_path"]))
        if os.path.basename(lock_path) != expected_name:
            entry["reason"] = "lock_filename_digest_mismatch"
            return entry

        owners = self.source_owners_for_path(lock["source_path"]) or []
        if lock["node_name"] not in owners:
            entry["reason"] = "source_owner_mismatch"
            return entry

        snapshot = task_snapshots.get(lock["node_name"])
        if snapshot is None:
            if scan_state["task_listing_complete"]:
                entry["classification"] = "orphan"
                entry["reason"] = "task_missing"
                entry["mutation_eligible"] = True
                return entry
            entry["reason"] = "task_scan_incomplete"
            entry["uncertain"] = True
            return entry

        entry["task_path"] = self._relpath(snapshot["path"])
        entry["task_identity"] = snapshot["artifact"].get("payload_digest")
        entry["task_lstat_identity"] = snapshot["artifact"].get("identity")
        validation = snapshot.get("validation") or {"valid": False, "errors": []}
        if not validation.get("valid"):
            entry["reason"] = "invalid_task"
            entry["task_errors"] = validation.get("errors", [])
            entry["uncertain"] = self._is_uncertain_artifact(snapshot["artifact"])
            return entry

        task_data = snapshot["data"]
        task_lock = task_data.get("source_lock") or {}
        for field in ("source_path", "node_name", "task_id", "acquired_at"):
            if task_lock.get(field) != lock.get(field):
                entry["reason"] = f"task_lock_mismatch:{field}"
                return entry

        status = task_data.get("status")
        entry["task_status"] = status
        if status in {"assigned", "in_progress", "submitted"}:
            entry["classification"] = "active"
            entry["reason"] = "active_task"
        elif status in {"approved", "blocked"}:
            entry["classification"] = "stale"
            entry["reason"] = "closed_task"
            entry["mutation_eligible"] = True
        else:
            entry["reason"] = "unsupported_task_status"
        return entry

    def audit(self):
        scan = self.scan_state()
        snapshots = scan["task_snapshots"]
        invalid_tasks = []
        for node_name, snapshot in snapshots.items():
            if not snapshot["validation"]["valid"]:
                invalid_tasks.append(
                    {
                        "classification": "invalid",
                        "reason": (
                            "unreadable_task"
                            if not snapshot["artifact"]["success"]
                            else "invalid_task"
                        ),
                        "node_name": node_name,
                        "canonical_path": os.path.abspath(snapshot["path"]),
                        "task_path": self._relpath(snapshot["path"]),
                        "task_identity": snapshot["artifact"].get("payload_digest"),
                        "digest": snapshot["artifact"].get("payload_digest"),
                        "identity": snapshot["artifact"].get("identity"),
                        "lstat_identity": snapshot["artifact"].get("identity"),
                        "task_errors": snapshot["validation"]["errors"],
                        "uncertain": self._is_uncertain_artifact(snapshot["artifact"]),
                        "evidence": self._artifact_evidence(snapshot["artifact"]),
                        "mutation_eligible": False,
                    }
                )

        entries = []
        seen_lock_paths = set()
        for path in scan["lock_paths"]:
            path = os.path.abspath(path)
            seen_lock_paths.add(path)
            entry = self.classify(path, scan)
            entries.append(entry)
            if entry.get("uncertain"):
                scan["mutation_blocked"] = True

        entries.extend(invalid_tasks)
        entries.extend(scan["synthetic_invalid"])

        for node_name, snapshot in snapshots.items():
            if not snapshot["validation"].get("valid"):
                continue
            task_data = snapshot["data"]
            if task_data.get("status") not in {"assigned", "in_progress", "submitted"}:
                continue

            source_path = task_data["source_lock"]["source_path"]
            expected_path = os.path.abspath(
                os.path.join(self.project_root, self._source_lock_path(source_path))
            )
            if expected_path not in seen_lock_paths:
                probe = self.repository.identity(expected_path)
                if probe["state"] != "missing":
                    entries.append(
                        {
                            "classification": "invalid",
                            "reason": "active_lock_state_uncertain",
                            "node_name": node_name,
                            "canonical_path": expected_path,
                            "lock_path": self._relpath(expected_path),
                            "uncertain": True,
                            "error": probe.get("error"),
                            "mutation_eligible": False,
                        }
                    )
                    scan["mutation_blocked"] = True
                    continue
                entries.append(
                    {
                        "classification": "invalid",
                        "reason": "active_task_missing_lock",
                        "node_name": node_name,
                        "task_id": task_data["task_id"],
                        "source_path": source_path,
                        "canonical_path": expected_path,
                        "task_path": self._relpath(snapshot["path"]),
                        "task_identity": snapshot["artifact"].get("payload_digest"),
                        "task_lstat_identity": snapshot["artifact"].get("identity"),
                        "lock_path": self._relpath(expected_path),
                        "mutation_eligible": True,
                    }
                )

        categories = {
            category: [entry for entry in entries if entry["classification"] == category]
            for category in ("active", "stale", "orphan", "invalid")
        }
        return {
            "success": True,
            "mode": "audit",
            "healthy": scan["healthy"] and not scan["mutation_blocked"],
            "mutation_blocked": scan["mutation_blocked"],
            "categories": categories,
            "counts": {name: len(items) for name, items in categories.items()},
        }


def scan_state(project_root, task_dir, repository, source_owners_for_path, validate_task_snapshot):
    return SourceLockAuditService(
        project_root,
        task_dir,
        repository,
        source_owners_for_path,
        validate_task_snapshot,
    ).scan_state()


def classify(
    lock_path,
    project_root,
    task_dir,
    repository,
    source_owners_for_path,
    validate_task_snapshot,
    state=None,
):
    return SourceLockAuditService(
        project_root,
        task_dir,
        repository,
        source_owners_for_path,
        validate_task_snapshot,
    ).classify(lock_path, state)


def audit(
    project_root,
    task_dir,
    repository,
    source_owners_for_path,
    validate_task_snapshot,
):
    return SourceLockAuditService(
        project_root,
        task_dir,
        repository,
        source_owners_for_path,
        validate_task_snapshot,
    ).audit()
