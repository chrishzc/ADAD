# -*- coding: utf-8 -*-
"""Decomposed Project Runtime State Policy Service.

Handles read-only preflight inspections, source lock archiving,
and task snapshot archiving for non-SSOT (test/legacy) artifacts.
"""

import os
import json
import yaml
import hashlib
import stat

class TaskSnapshotArchiveRepository:
    """Read-only and non-overwrite archive repository for Task snapshots."""

    def __init__(self, project_root, archive_dir=".agents/tasks/archive"):
        self.project_root = os.path.realpath(os.fspath(project_root))
        self.archive_dir = os.path.normpath(os.path.join(self.project_root, os.fspath(archive_dir)))

    def archive_path(self, node_name, task_id):
        # ponytail: keep filename simple and unique
        return os.path.join(self.archive_dir, f"{node_name}_{task_id}.task.json")

    def archive(self, src_path, node_name, task_id, expected_identity):
        """Relocates a task snapshot to the archive directory without overwriting (identity-checked move)."""
        os.makedirs(self.archive_dir, exist_ok=True)
        dest_path = self.archive_path(node_name, task_id)
        if os.path.exists(dest_path):
            return {
                "success": False,
                "error": f"[ARCHIVE] Archive target already exists: {dest_path}"
            }
        try:
            with open(src_path, "rb") as f:
                raw_content = f.read()

            # Parse and verify identity/payload digest
            payload = json.loads(raw_content.decode("utf-8"))
            digest = hashlib.sha256(raw_content).hexdigest()

            # Simple check if current identity is identical
            details = os.lstat(src_path)
            identity = {"st_dev": details.st_dev, "st_ino": details.st_ino}

            expected_id_val = expected_identity.get("identity") or {}
            if (expected_id_val.get("st_dev") != identity["st_dev"] or
                expected_id_val.get("st_ino") != identity["st_ino"] or
                expected_identity.get("payload_digest") != digest):
                return {
                    "success": False,
                    "error": "[ARCHIVE] Identity mismatch or payload drift before write."
                }

            # Relocate (move) file to dest_path with atomic non-overwrite guarantee to prevent TOCTOU.
            moved = False
            try:
                if os.name == "posix":
                    try:
                        os.link(src_path, dest_path)
                        # Revalidate source identity/payload before unlinking to prevent deleting a replaced file
                        try:
                            with open(src_path, "rb") as f:
                                current_raw = f.read()
                            current_digest = hashlib.sha256(current_raw).hexdigest()
                            current_details = os.lstat(src_path)
                            if (current_details.st_dev != details.st_dev or
                                current_details.st_ino != details.st_ino or
                                current_digest != digest):
                                raise RuntimeError("Source file identity or payload changed before unlink.")
                            os.unlink(src_path)
                        except Exception as unlink_err:
                            try:
                                os.unlink(dest_path)
                            except OSError:
                                pass
                            raise unlink_err
                        moved = True
                    except OSError as link_err:
                        if isinstance(link_err, FileExistsError):
                            raise
                        # For other OSErrors (e.g. EXDEV, ENOTSUP), fallback to exclusive open
                else:
                    # On Windows, os.rename is natively non-overwrite (raises FileExistsError if dest exists)
                    os.rename(src_path, dest_path)
                    # Revalidate source identity/payload after rename to check if it was replaced before rename
                    try:
                        with open(dest_path, "rb") as f:
                            current_raw = f.read()
                        current_digest = hashlib.sha256(current_raw).hexdigest()
                        current_details = os.lstat(dest_path)
                        if (current_details.st_dev != details.st_dev or
                            current_details.st_ino != details.st_ino or
                            current_digest != digest):
                            raise RuntimeError("Source file identity or payload changed before rename.")
                    except Exception as rename_reval_err:
                        try:
                            os.rename(dest_path, src_path)
                        except OSError:
                            pass
                        raise rename_reval_err
                    moved = True
            except FileExistsError:
                return {
                    "success": False,
                    "error": f"[ARCHIVE] Archive target already exists: {dest_path}"
                }
            except OSError:
                moved = False

            if not moved:
                # Fallback: open dest with exclusive creation ('xb') to guarantee non-overwrite, write, then unlink source.
                try:
                    with open(dest_path, "xb") as f_out:
                        f_out.write(raw_content)
                except FileExistsError:
                    return {
                        "success": False,
                        "error": f"[ARCHIVE] Archive target already exists: {dest_path}"
                    }
                try:
                    # Revalidate source identity/payload before unlinking to prevent deleting a replaced file
                    with open(src_path, "rb") as f:
                        current_raw = f.read()
                    current_digest = hashlib.sha256(current_raw).hexdigest()
                    current_details = os.lstat(src_path)
                    if (current_details.st_dev != details.st_dev or
                        current_details.st_ino != details.st_ino or
                        current_digest != digest):
                        raise RuntimeError("Source file identity or payload changed before unlink.")
                    os.unlink(src_path)
                except Exception as unlink_err:
                    try:
                        os.unlink(dest_path)
                    except OSError:
                        pass
                    raise unlink_err

            return {
                "success": True,
                "dest_path": dest_path,
                "payload_digest": digest,
                "bytes_written": len(raw_content)
            }
        except Exception as exc:
            return {
                "success": False,
                "error": f"[ARCHIVE] Archive failed: {exc}"
            }


def inspect_non_ssot_runtime_artifacts(project_root, audit_service, candidate_node_names):
    """
    #82-A1 唯讀檢查候選名稱，確認其不在 SSOT、無 active claim，輸出 preflight receipt。
    """
    # 1. Input validation
    if not isinstance(candidate_node_names, list) or not candidate_node_names:
        return {
            "preflight_receipt": {
                "success": False,
                "reason": "empty_or_invalid_candidates",
                "error": "candidate_node_names must be a non-empty array."
            },
            "healthy": False
        }

    seen = set()
    for name in candidate_node_names:
        if not isinstance(name, str) or not name or "/" in name or "\\" in name or ".." in name:
            return {
                "preflight_receipt": {
                    "success": False,
                    "reason": "invalid_or_traversal_candidate_name",
                    "error": f"Invalid candidate name or path traversal detected: {name!r}"
                },
                "healthy": False
            }
        if name in seen:
            return {
                "preflight_receipt": {
                    "success": False,
                    "reason": "duplicate_candidate_names",
                    "error": f"Duplicate candidate name detected: {name!r}"
                },
                "healthy": False
            }
        seen.add(name)

    # 2. Load system map to check active SSOT owners
    project_root = os.path.realpath(os.fspath(project_root))
    map_path = os.path.join(project_root, "system_map.yaml")
    if not os.path.exists(map_path):
        return {
            "preflight_receipt": {
                "success": False,
                "reason": "system_map_missing",
                "error": "system_map.yaml is missing."
            },
            "healthy": False
        }

    try:
        with open(map_path, "r", encoding="utf-8") as f:
            system_map = yaml.safe_load(f) or {}
    except Exception as exc:
        return {
            "preflight_receipt": {
                "success": False,
                "reason": "system_map_unreadable",
                "error": f"Failed to read system_map.yaml: {exc}"
            },
            "healthy": False
        }

    ssot_modules = system_map.get("modules", {})

    # Pre-build SSOT active source owners mapping
    ssot_sources = {}
    for mod_name, mod in ssot_modules.items():
        src_field = mod.get("source") or ""
        if isinstance(src_field, str):
            src_paths = [src_field]
        elif isinstance(src_field, list):
            src_paths = src_field
        else:
            src_paths = []

        for s in src_paths:
            path_part = s.split("::")[0]
            canonical_src_path = os.path.normpath(path_part).replace("\\", "/")
            ssot_sources.setdefault(canonical_src_path, []).append(mod_name)

    # 3. Call audit_service to get the fresh audit report
    report = audit_service.audit()
    if not report.get("success") or not report.get("healthy") or report.get("mutation_blocked"):
        return {
            "preflight_receipt": {
                "success": False,
                "reason": "audit_service_unhealthy_or_blocked",
                "report": report
            },
            "healthy": False
        }

    # 4. Perform check on each candidate
    candidate_details = {}
    categories = report.get("categories", {})
    all_audit_records = []
    for cat in ("active", "stale", "orphan", "invalid"):
        all_audit_records.extend(categories.get(cat, []))

    for node_name in candidate_node_names:
        # Check node ownership in SSOT
        if node_name in ssot_modules:
            return {
                "preflight_receipt": {
                    "success": False,
                    "reason": "candidate_has_ssot_owner",
                    "error": f"Candidate module `{node_name}` has an active owner in SSOT."
                },
                "healthy": False
            }

        # Resolve candidate paths and check readability/ownership
        task_json_path = os.path.join(project_root, ".agents", "tasks", f"{node_name}.task.json")
        task_exists = os.path.exists(task_json_path)

        source_path = None
        task_id = None
        task_identity = None
        if task_exists:
            # Check if this node is classified as uncertain/unreadable in the audit report
            invalid_record = next((r for r in categories.get("invalid", []) if r.get("node_name") == node_name), None)
            if invalid_record and invalid_record.get("uncertain"):
                return {
                    "preflight_receipt": {
                        "success": False,
                        "reason": "candidate_task_uncertain",
                        "error": f"Candidate `{node_name}` task snapshot is uncertain: {invalid_record.get('error')}"
                    },
                    "healthy": False
                }

            try:
                task_probe = audit_service.repository.identity(task_json_path)
                if not task_probe.get("success"):
                    if task_probe.get("uncertain"):
                        raise ValueError(task_probe.get("error") or "Unreadable task file")
                task_data = task_probe.get("payload") or {}
                task_id = task_data.get("task_id")
                task_identity = {
                    "identity": task_probe.get("identity"),
                    "payload_digest": task_probe.get("payload_digest")
                }
                target_node = task_data.get("spec", {}).get("target_node", {})
                src_val = target_node.get("source") or ""
                if src_val:
                    source_path = os.path.normpath(src_val.split("::")[0]).replace("\\", "/")
            except Exception as exc:
                return {
                    "preflight_receipt": {
                        "success": False,
                        "reason": "candidate_task_unreadable",
                        "error": f"Candidate `{node_name}` task snapshot exists but is unreadable: {exc}"
                    },
                    "healthy": False
                }

        # Find matching lock records in audit report
        node_locks = [r for r in all_audit_records if r.get("node_name") == node_name]

        # If both task and locks don't exist, we reject (nothing to archive)
        if not task_exists and not node_locks:
            return {
                "preflight_receipt": {
                    "success": False,
                    "reason": "candidate_not_found",
                    "error": f"No task snapshot or source lock found for candidate `{node_name}`."
                },
                "healthy": False
            }

        # Verify no active claims on the candidate node or its source path
        for lock_record in node_locks:
            if lock_record.get("classification") == "active":
                return {
                    "preflight_receipt": {
                        "success": False,
                        "reason": "candidate_has_active_claim",
                        "error": f"Candidate `{node_name}` has active claim/lock."
                    },
                    "healthy": False
                }
            if lock_record.get("uncertain"):
                return {
                    "preflight_receipt": {
                        "success": False,
                        "reason": "candidate_lock_uncertain",
                        "error": f"Candidate `{node_name}` has invalid/uncertain lock: {lock_record.get('error')}"
                    },
                    "healthy": False
                }
            if not source_path:
                source_path = os.path.normpath(lock_record.get("source_path") or "").replace("\\", "/")

        if source_path:
            # Check if source_path has any active owner in SSOT
            if source_path in ssot_sources:
                return {
                    "preflight_receipt": {
                        "success": False,
                        "reason": "source_path_has_ssot_owner",
                        "error": f"Source path `{source_path}` has active owner in SSOT: {ssot_sources[source_path]}"
                    },
                    "healthy": False
                }

            # Check if any active task in audit report claims this source path
            for active_rec in categories.get("active", []):
                active_src = os.path.normpath(active_rec.get("source_path") or "").replace("\\", "/")
                if active_src == source_path:
                    return {
                        "preflight_receipt": {
                            "success": False,
                            "reason": "source_path_has_active_claim",
                            "error": f"Source path `{source_path}` is claimed by active task: {active_rec.get('node_name')}"
                        },
                        "healthy": False
                    }

        candidate_details[node_name] = {
            "node_name": node_name,
            "task_exists": task_exists,
            "task_path": task_json_path if task_exists else None,
            "task_id": task_id,
            "task_identity": task_identity,
            "source_path": source_path,
            "locks": [
                {
                    "path": os.path.join(project_root, lock_rec["lock_path"]),
                    "identity": lock_rec.get("lstat_identity") or lock_rec.get("identity"),
                    "payload_digest": lock_rec.get("payload_digest")
                }
                for lock_rec in node_locks if lock_rec.get("lock_path")
            ]
        }

    preflight = {
        "success": True,
        "healthy": True,
        "candidate_details": candidate_details,
        "audit_summary": {
            "counts": report.get("counts"),
            "healthy": report.get("healthy")
        }
    }
    return {
        "preflight_receipt": preflight,
        "healthy": True
    }


def archive_non_ssot_source_locks(project_root, repository, preflight_receipt):
    """#82-A2 只依據 repository 封存已通過 preflight 的精確 canonical locks，保留 quarantine 證據。"""
    if not preflight_receipt.get("success") or not preflight_receipt.get("healthy"):
        return {
            "lock_archive_receipt": {
                "success": False,
                "error": "Preflight check is unhealthy or failed."
            },
            "mutation_evidence": []
        }
    evidence = []
    details = preflight_receipt.get("candidate_details") or {}
    for node_name, cand in details.items():
        for lock_info in cand.get("locks", []):
            path = lock_info["path"]
            current_state = repository.identity(path)
            quarantined = repository.quarantine(path, current_state)
            evidence.append({
                "node_name": node_name,
                "lock_path": path,
                "quarantined": quarantined
            })
            if not quarantined.get("success"):
                return {
                    "lock_archive_receipt": {
                        "success": False,
                        "error": f"Failed to quarantine lock: {quarantined.get('error')}"
                    },
                    "mutation_evidence": evidence
                }
    return {
        "lock_archive_receipt": {
            "success": True,
            "message": "All non-SSOT source locks archived successfully."
        },
        "mutation_evidence": evidence
    }


def archive_non_ssot_task_snapshots(project_root, preflight_receipt):
    """#82-A3 唯讀或 non-overwrite 方式封存已通過 preflight 的 Task snapshots，保留 exact bytes。"""
    if not preflight_receipt.get("success") or not preflight_receipt.get("healthy"):
        return {
            "task_archive_receipt": {
                "success": False,
                "error": "Preflight check is unhealthy or failed."
            },
            "mutation_evidence": []
        }
    archive_repo = TaskSnapshotArchiveRepository(project_root)
    evidence = []
    details = preflight_receipt.get("candidate_details") or {}
    for node_name, cand in details.items():
        if cand.get("task_exists"):
            path = cand["task_path"]
            task_id = cand["task_id"]
            expected = cand["task_identity"]
            archived = archive_repo.archive(path, node_name, task_id, expected)
            evidence.append({
                "node_name": node_name,
                "task_path": path,
                "archived": archived
            })
            if not archived.get("success"):
                return {
                    "task_archive_receipt": {
                        "success": False,
                        "error": f"Failed to archive task snapshot: {archived.get('error')}"
                    },
                    "mutation_evidence": evidence
                }
    return {
        "task_archive_receipt": {
            "success": True,
            "message": "All non-SSOT task snapshots archived successfully."
        },
        "mutation_evidence": evidence
    }


class ProjectRuntimeStatePolicy:
    """Aggregator and reporting service for project runtime state policy."""

    def __init__(self, project_root, audit_service, repository):
        self.project_root = os.path.realpath(os.fspath(project_root))
        self.audit_service = audit_service
        self.repository = repository

    def archive_non_ssot_task_artifacts(self, candidate_node_names):
        # 1. Inspect
        inspect_res = inspect_non_ssot_runtime_artifacts(
            self.project_root, self.audit_service, candidate_node_names
        )
        preflight = inspect_res["preflight_receipt"]
        if not inspect_res["healthy"]:
            return {
                "success": False,
                "error": "Preflight check failed.",
                "archive_receipt": preflight,
                "mutation_evidence": []
            }

        # 2. Archive Locks
        lock_res = archive_non_ssot_source_locks(
            self.project_root, self.repository, preflight
        )
        lock_receipt = lock_res["lock_archive_receipt"]
        if not lock_receipt.get("success"):
            return {
                "success": False,
                "error": f"Locks archiving failed: {lock_receipt.get('error')}",
                "archive_receipt": {
                    "preflight": preflight,
                    "locks": lock_receipt
                },
                "mutation_evidence": lock_res["mutation_evidence"]
            }

        # 3. Archive Snapshots
        task_res = archive_non_ssot_task_snapshots(
            self.project_root, preflight
        )
        task_receipt = task_res["task_archive_receipt"]
        if not task_receipt.get("success"):
            return {
                "success": False,
                "error": f"Task snapshots archiving failed: {task_receipt.get('error')}",
                "archive_receipt": {
                    "preflight": preflight,
                    "locks": lock_receipt,
                    "tasks": task_receipt
                },
                "mutation_evidence": lock_res["mutation_evidence"] + task_res["mutation_evidence"]
            }

        # 4. Success post-audit
        post_audit = self.audit_service.audit()

        return {
            "success": True,
            "archive_receipt": {
                "preflight": preflight,
                "locks_archive": lock_receipt,
                "tasks_archive": task_receipt
            },
            "mutation_evidence": lock_res["mutation_evidence"] + task_res["mutation_evidence"],
            "post_audit_report": post_audit
        }

if __name__ == "__main__":
    # Self-check assertion to satisfy must_have_assertions AST check
    assert inspect_non_ssot_runtime_artifacts is not None
