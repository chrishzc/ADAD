# -*- coding: utf-8 -*-
"""Filesystem repository for Source Lock artifacts."""

import datetime
import hashlib
import json
import os
import stat


class SourceLockRepository:
    """Preserve the existing Source Lock artifact behavior behind one service."""

    def __init__(self, project_root, lock_dir, source_path_for_node):
        self.project_root = os.path.realpath(os.fspath(project_root))
        self.lock_dir = os.fspath(lock_dir)
        self.source_path_for_node = source_path_for_node

    def lock_path(self, source_path):
        digest = hashlib.sha256(source_path.encode("utf-8")).hexdigest()
        return os.path.join(self.lock_dir, f"{digest}.lock.json")

    def read(self, source_path):
        path = os.path.join(self.project_root, self.lock_path(source_path))
        try:
            with open(path, "r", encoding="utf-8", errors="strict") as handle:
                payload = json.load(handle)
            if not isinstance(payload, dict):
                raise ValueError("JSON payload must be an object.")
            return payload
        except FileNotFoundError:
            return None
        except OSError as exc:
            return {
                "invalid": True,
                "uncertain": True,
                "state": "error",
                "path": self.lock_path(source_path),
                "error": str(exc),
            }
        except (UnicodeError, json.JSONDecodeError, ValueError):
            return {"invalid": True, "path": self.lock_path(source_path)}

    def identity(self, path):
        canonical = os.path.abspath(os.fspath(path))
        try:
            before = os.lstat(canonical)
        except FileNotFoundError:
            return {"success": True, "state": "missing", "path": canonical}
        except OSError as exc:
            return {
                "success": False,
                "state": "error",
                "path": canonical,
                "uncertain": True,
                "error": str(exc),
            }
        artifact_identity = {
            "st_dev": before.st_dev,
            "st_ino": before.st_ino,
            "st_size": before.st_size,
            "st_mtime_ns": getattr(
                before, "st_mtime_ns", int(before.st_mtime * 1_000_000_000)
            ),
        }
        if not stat.S_ISREG(before.st_mode):
            return {
                "success": False,
                "state": "invalid",
                "path": canonical,
                "uncertain": False,
                "error": "Source Lock artifact is not a regular file.",
                "identity": artifact_identity,
            }
        try:
            with open(canonical, "rb") as handle:
                raw = handle.read()
                after = os.fstat(handle.fileno())
        except FileNotFoundError:
            return {
                "success": False,
                "state": "error",
                "uncertain": True,
                "path": canonical,
                "error": "Artifact disappeared during read.",
                "identity": artifact_identity,
            }
        except OSError as exc:
            return {
                "success": False,
                "state": "error",
                "path": canonical,
                "uncertain": True,
                "error": str(exc),
                "identity": artifact_identity,
            }
        after_identity = {
            "st_dev": after.st_dev,
            "st_ino": after.st_ino,
            "st_size": after.st_size,
            "st_mtime_ns": getattr(
                after, "st_mtime_ns", int(after.st_mtime * 1_000_000_000)
            ),
        }
        if after_identity != artifact_identity:
            return {
                "success": False,
                "state": "error",
                "path": canonical,
                "uncertain": True,
                "error": "Artifact identity changed during read.",
                "identity": artifact_identity,
                "after_identity": after_identity,
            }
        digest = hashlib.sha256(raw).hexdigest()
        try:
            payload = json.loads(raw.decode("utf-8", errors="strict"))
        except (UnicodeError, json.JSONDecodeError) as exc:
            res = {
                "success": False,
                "state": "invalid",
                "path": canonical,
                "uncertain": True,
                "error": str(exc),
                "identity": artifact_identity,
                "payload_digest": digest,
                "raw_hex": raw.hex(),
            }
            res["evidence"] = res.copy()
            return res
        if not isinstance(payload, dict):
            res = {
                "success": False,
                "state": "invalid",
                "path": canonical,
                "uncertain": False,
                "error": "JSON payload must be an object.",
                "identity": artifact_identity,
                "payload_digest": digest,
            }
            res["evidence"] = res.copy()
            return res
        return {
            "success": True,
            "state": "present",
            "path": canonical,
            "identity": artifact_identity,
            "payload_digest": digest,
            "payload": payload,
        }

    def _terminal_cleanup_quarantine(self, quarantine_path):
        cleanup = {
            "attempted": True,
            "success": True,
            "status": "quarantine_retained",
            "quarantine_retained": True,
            "canonical_cleared": True,
            "artifact_deleted": False,
            "delete_attempted": True,
            "manual_action_required": False,
            "quarantine_path": quarantine_path,
        }
        if not quarantine_path or not os.path.exists(quarantine_path):
            cleanup["quarantine_retained"] = False
            cleanup["status"] = "not_needed"
            cleanup["delete_attempted"] = False
            return cleanup
        probe = self.identity(quarantine_path)
        if not probe.get("success") or probe.get("state") != "present":
            cleanup["success"] = True
            cleanup["quarantine_retained"] = True
            cleanup["artifact_deleted"] = False
            cleanup["delete_attempted"] = False
            cleanup["status"] = "quarantine_retained"
            cleanup["error"] = "[SOURCE LOCK] Competitor sentinel or invalid lock found in quarantine."
            return cleanup
        try:
            os.remove(quarantine_path)
            cleanup["success"] = True
            cleanup["quarantine_retained"] = False
            cleanup["artifact_deleted"] = True
            cleanup["status"] = "removed"
        except OSError as exc:
            cleanup["success"] = False
            cleanup["quarantine_retained"] = True
            cleanup["artifact_deleted"] = False
            cleanup["manual_action_required"] = True
            cleanup["status"] = "cleanup_failed"
            cleanup["error"] = str(exc)
        return cleanup

    def quarantine(self, canonical_path, expected):
        current = self.identity(canonical_path)
        current_is_exact = (
            not current.get("uncertain", False)
            and current.get("state") in {"present", "invalid"}
            and current.get("payload_digest") == expected.get("payload_digest")
            and current.get("identity") == expected.get("identity")
        )
        if not current_is_exact:
            return {
                "success": False,
                "result": "identity_mismatch",
                "error": "[SOURCE LOCK] Lock identity changed before quarantine.",
                "evidence": current,
            }
        stamp = datetime.datetime.now(datetime.timezone.utc).strftime(
            "%Y%m%dT%H%M%S%fZ"
        )
        quarantine_path = f"{canonical_path}.quarantine-{stamp}-{os.getpid()}"
        try:
            os.rename(canonical_path, quarantine_path)
        except OSError as exc:
            return {
                "success": False,
                "result": "error",
                "error": f"[SOURCE LOCK] Quarantine rename failed: {exc}",
                "evidence": current,
            }
        quarantined = self.identity(quarantine_path)
        stable = (
            not quarantined.get("uncertain", False)
            and quarantined.get("state") in {"present", "invalid"}
            and quarantined.get("payload_digest") == expected.get("payload_digest")
            and quarantined.get("identity") == expected.get("identity")
        )
        if not stable:
            restore = {"attempted": False, "success": False}
            canonical = self.identity(canonical_path)
            if canonical["state"] == "missing":
                restore["attempted"] = True
                try:
                    os.link(quarantine_path, canonical_path)
                    restore["success"] = True
                    restore.update(
                        {
                            "delete_attempted": False,
                            "artifact_deleted": False,
                            "manual_action_required": False,
                            "quarantine_retained": True,
                        }
                    )
                except OSError as exc:
                    restore["error"] = str(exc)
                    restore["manual_action_required"] = True
            else:
                restore["error"] = "Canonical path is occupied or uncertain."
                restore["manual_action_required"] = True
            restore.update(
                {
                    "canonical_cleared": False,
                    "quarantine_path": quarantine_path,
                    "artifact_deleted": restore.get("artifact_deleted", False),
                }
            )
            return {
                "success": False,
                "result": "identity_mismatch",
                "error": "[SOURCE LOCK] Quarantine identity validation failed.",
                "quarantine_path": quarantine_path,
                "restore": restore,
                "evidence": quarantined,
            }
        return {
            "success": True,
            "result": "quarantined",
            "canonical_path": canonical_path,
            "quarantine_path": quarantine_path,
            "identity": quarantined["identity"],
            "payload_digest": quarantined["payload_digest"],
            "quarantine_retained": True,
            "canonical_cleared": True,
            "artifact_deleted": False,
            "delete_attempted": False,
            "manual_action_required": False,
        }

    def restore_quarantine(self, quarantine_receipt):
        """Restore an exact quarantined artifact without overwriting canonical state."""

        def rejected(result, error, evidence=None, attempted=False):
            response = {
                "success": False,
                "result": result,
                "status": "manual_action_required",
                "attempted": attempted,
                "manual_action_required": True,
                "quarantine_retained": True,
                "artifact_deleted": False,
                "delete_attempted": False,
                "error": error,
            }
            if evidence is not None:
                response["evidence"] = evidence
            return response

        required_receipt = (
            isinstance(quarantine_receipt, dict)
            and quarantine_receipt.get("success") is True
            and quarantine_receipt.get("result") == "quarantined"
            and quarantine_receipt.get("quarantine_retained") is True
            and quarantine_receipt.get("canonical_cleared") is True
            and quarantine_receipt.get("artifact_deleted") is False
            and quarantine_receipt.get("delete_attempted") is False
            and isinstance(quarantine_receipt.get("identity"), dict)
            and isinstance(quarantine_receipt.get("payload_digest"), str)
        )
        if not required_receipt:
            return rejected(
                "invalid_receipt",
                "[SOURCE LOCK] Restore requires a successful quarantine receipt.",
            )

        canonical_value = quarantine_receipt.get("canonical_path")
        quarantine_value = quarantine_receipt.get("quarantine_path")
        path_types = (str, bytes, os.PathLike)
        if not isinstance(canonical_value, path_types) or not isinstance(
            quarantine_value, path_types
        ):
            return rejected(
                "invalid_receipt",
                "[SOURCE LOCK] Quarantine receipt paths are invalid.",
            )

        lock_root = os.path.abspath(os.path.join(self.project_root, self.lock_dir))

        def lexical_path_evidence(value):
            raw = os.fsdecode(os.fspath(value))
            if os.path.isabs(raw):
                normalized = os.path.abspath(raw)
            else:
                normalized = os.path.abspath(os.path.join(self.project_root, raw))
            traversal = ".." in raw.replace("\\", "/").split("/")
            try:
                within = (
                    os.path.normcase(os.path.commonpath([normalized, lock_root]))
                    == os.path.normcase(lock_root)
                )
            except (OSError, ValueError):
                within = False
            return {
                "raw": raw,
                "normalized": normalized,
                "traversal": traversal,
                "within_lock_dir": within,
                "same_directory": (
                    os.path.normcase(os.path.dirname(normalized))
                    == os.path.normcase(lock_root)
                ),
            }

        canonical_path_evidence = lexical_path_evidence(canonical_value)
        quarantine_path_evidence = lexical_path_evidence(quarantine_value)
        canonical_path = canonical_path_evidence["normalized"]
        quarantine_path = quarantine_path_evidence["normalized"]
        canonical_suffix = canonical_path.endswith(".lock.json")
        quarantine_prefix = quarantine_path.startswith(
            canonical_path + ".quarantine-"
        )
        lexical_evidence = {
            "lock_root": lock_root,
            "canonical": canonical_path_evidence,
            "quarantine": quarantine_path_evidence,
            "canonical_suffix": canonical_suffix,
            "quarantine_prefix": quarantine_prefix,
        }
        path_pair_is_valid = (
            not canonical_path_evidence["traversal"]
            and not quarantine_path_evidence["traversal"]
            and canonical_path_evidence["within_lock_dir"]
            and quarantine_path_evidence["within_lock_dir"]
            and canonical_path_evidence["same_directory"]
            and quarantine_path_evidence["same_directory"]
            and canonical_suffix
            and quarantine_prefix
        )
        if not path_pair_is_valid:
            return rejected(
                "unsafe_path",
                "[SOURCE LOCK] Quarantine receipt paths are outside the lock boundary.",
                lexical_evidence,
            )

        resolved_lock_root = os.path.realpath(lock_root)
        if os.path.normcase(resolved_lock_root) != os.path.normcase(lock_root):
            lexical_evidence["resolved_lock_root"] = resolved_lock_root
            return rejected(
                "unsafe_path",
                "[SOURCE LOCK] Source Lock directory uses an unsafe symlink boundary.",
                lexical_evidence,
            )

        quarantined = self.identity(quarantine_path)
        quarantine_is_exact = (
            not quarantined.get("uncertain", False)
            and quarantined.get("state") in {"present", "invalid"}
            and quarantined.get("identity") == quarantine_receipt["identity"]
            and quarantined.get("payload_digest")
            == quarantine_receipt["payload_digest"]
        )
        if not quarantine_is_exact:
            return rejected(
                "identity_mismatch",
                "[SOURCE LOCK] Quarantine artifact identity changed before restore.",
                {"quarantine": quarantined},
            )

        canonical = self.identity(canonical_path)
        canonical_is_missing = (
            canonical.get("success") is True
            and canonical.get("state") == "missing"
            and not canonical.get("uncertain", False)
        )
        if not canonical_is_missing:
            result = "occupied" if canonical.get("state") != "error" else "error"
            return rejected(
                result,
                "[SOURCE LOCK] Canonical path is occupied or uncertain.",
                {"canonical": canonical, "quarantine": quarantined},
            )

        try:
            os.link(quarantine_path, canonical_path)
        except FileExistsError as exc:
            return rejected(
                "conflict",
                f"[SOURCE LOCK] Canonical path was occupied during restore: {exc}",
                {"canonical": self.identity(canonical_path), "quarantine": quarantined},
                attempted=True,
            )
        except OSError as exc:
            return rejected(
                "error",
                f"[SOURCE LOCK] Exact quarantine restore failed: {exc}",
                {"canonical": canonical, "quarantine": quarantined},
                attempted=True,
            )

        restored = self.identity(canonical_path)
        restored_is_exact = (
            not restored.get("uncertain", False)
            and restored.get("state") in {"present", "invalid"}
            and restored.get("identity") == quarantine_receipt["identity"]
            and restored.get("payload_digest")
            == quarantine_receipt["payload_digest"]
        )
        if not restored_is_exact:
            return rejected(
                "identity_mismatch",
                "[SOURCE LOCK] Restored canonical artifact failed exact validation.",
                {"canonical": restored, "quarantine": quarantined},
                attempted=True,
            )
        return {
            "success": True,
            "result": "restored",
            "status": "restored",
            "attempted": True,
            "manual_action_required": False,
            "canonical_path": canonical_path,
            "quarantine_path": quarantine_path,
            "identity": restored["identity"],
            "payload_digest": restored["payload_digest"],
            "quarantine_retained": True,
            "canonical_cleared": False,
            "artifact_deleted": False,
            "delete_attempted": False,
            "evidence": {"canonical": restored, "quarantine": quarantined},
        }

    def release(self, task_data):
        lock = task_data.get("source_lock") or {}
        source_path = lock.get("source_path")
        task_id = task_data.get("task_id")
        node_name = task_data.get("node_name")
        if not source_path or not task_id or not node_name:
            return {
                "success": False,
                "result": "invalid",
                "error": "[SOURCE LOCK] Task lock metadata is incomplete.",
            }
        if lock.get("task_id") != task_id or lock.get("node_name") != node_name:
            return {
                "success": False,
                "result": "invalid",
                "error": "[SOURCE LOCK] Task lock metadata does not match this Task.",
            }
        path = os.path.join(self.project_root, self.lock_path(source_path))
        current = self.identity(path)
        if current["state"] == "missing":
            return {"success": True, "result": "already_absent", "released": False}
        if not current["success"]:
            return {
                "success": False,
                "result": "error" if current.get("uncertain") else "invalid",
                "error": current["error"],
                "evidence": current,
            }
        existing = current["payload"]
        if any(
            existing.get(field) != lock.get(field)
            for field in ("source_path", "node_name", "task_id", "acquired_at")
        ):
            return {
                "success": False,
                "result": "identity_mismatch",
                "error": "[SOURCE LOCK] Physical lock does not match this Task.",
                "evidence": current,
            }
        quarantined = self.quarantine(path, current)
        if not quarantined["success"]:
            return quarantined
        terminal_cleanup = self._terminal_cleanup_quarantine(
            quarantined["quarantine_path"]
        )
        evidence = {
            "success": quarantined["success"],
            "result": quarantined["result"],
            "canonical_path": quarantined.get("canonical_path"),
            "quarantine_path": quarantined["quarantine_path"],
            "identity": quarantined["identity"],
            "payload_digest": quarantined["payload_digest"],
        }
        cleanup = {
            "attempted": terminal_cleanup["attempted"],
            "success": terminal_cleanup["success"],
            "status": terminal_cleanup["status"],
            "quarantine_retained": terminal_cleanup["quarantine_retained"],
            "canonical_cleared": terminal_cleanup["canonical_cleared"],
            "artifact_deleted": terminal_cleanup["artifact_deleted"],
            "delete_attempted": terminal_cleanup["delete_attempted"],
            "manual_action_required": terminal_cleanup["manual_action_required"],
            "quarantine_path": quarantined["quarantine_path"],
        }
        if not terminal_cleanup["success"]:
            return {
                "success": True,
                "result": "released",
                "released": True,
                "warning": "[SOURCE LOCK] Quarantine cleanup failed: "
                + terminal_cleanup.get("error", "unknown"),
                "quarantine_path": quarantined["quarantine_path"],
                "evidence": evidence,
                "cleanup": cleanup,
            }
        return {
            "success": True,
            "result": "released",
            "released": True,
            "quarantine_path": quarantined["quarantine_path"],
            "cleanup": cleanup,
            "evidence": evidence,
        }

    def acquire(self, node_name, task_id):
        source_path = self.source_path_for_node(node_name)
        if not source_path:
            return {"success": False, "error": "[SOURCE LOCK] Task has no source path."}
        directory = os.path.join(self.project_root, self.lock_dir)
        os.makedirs(directory, exist_ok=True)
        relative_path = self.lock_path(source_path)
        path = os.path.join(self.project_root, relative_path)
        payload = {
            "source_path": source_path,
            "node_name": node_name,
            "task_id": task_id,
            "acquired_at": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        }
        encoded = (
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
        ).encode("utf-8")
        expected_digest = hashlib.sha256(encoded).hexdigest()

        def exclusive_create():
            descriptor = None
            owned_fd_identity = None
            open_succeeded = False

            def descriptor_identity(fd):
                details = os.fstat(fd)
                identity = {"st_dev": details.st_dev, "st_ino": details.st_ino}
                if not stat.S_ISREG(details.st_mode):
                    raise OSError("Created Source Lock artifact is not a regular file.")
                return identity

            def cleanup_owned_artifact():
                cleanup = {"attempted": False, "success": False}
                current = self.identity(path)
                cleanup["evidence"] = current
                if owned_fd_identity is None:
                    cleanup["error"] = "Created artifact ownership is uncertain."
                    return cleanup
                if current.get("state") == "missing":
                    cleanup["success"] = True
                    return cleanup
                current_identity = current.get("identity") or {}
                if (
                    current.get("state") not in {"present", "invalid"}
                    or current_identity.get("st_dev")
                    != owned_fd_identity["st_dev"]
                    or current_identity.get("st_ino")
                    != owned_fd_identity["st_ino"]
                ):
                    cleanup["error"] = (
                        "Canonical artifact is not the descriptor-owned artifact; "
                        "manual action is required."
                    )
                    return cleanup
                cleanup["attempted"] = True
                quarantined = self.quarantine(path, current)
                cleanup["quarantine"] = quarantined
                if quarantined["success"]:
                    cleanup.update(
                        {
                            "success": True,
                            "status": "quarantined",
                            "quarantine_retained": True,
                            "canonical_cleared": True,
                            "artifact_deleted": False,
                            "delete_attempted": False,
                            "manual_action_required": False,
                            "quarantine_path": quarantined["quarantine_path"],
                        }
                    )
                return cleanup

            try:
                descriptor = os.open(
                    path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600
                )
                open_succeeded = True
                owned_fd_identity = descriptor_identity(descriptor)
                with os.fdopen(descriptor, "wb") as handle:
                    descriptor = None
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                    final_fd_identity = descriptor_identity(handle.fileno())
                    if final_fd_identity != owned_fd_identity:
                        raise OSError(
                            "Created artifact descriptor identity changed during write."
                        )
                canonical = self.identity(path)
                canonical_identity = canonical.get("identity") or {}
                valid = (
                    canonical.get("success") is True
                    and canonical.get("state") == "present"
                    and canonical_identity.get("st_dev") == owned_fd_identity["st_dev"]
                    and canonical_identity.get("st_ino") == owned_fd_identity["st_ino"]
                    and canonical.get("payload_digest") == expected_digest
                    and canonical.get("payload") == payload
                )
                if not valid:
                    cleanup = cleanup_owned_artifact()
                    return {
                        "success": False,
                        "result": "error",
                        "error": (
                            "[SOURCE LOCK] Created artifact failed final identity "
                            "or payload validation."
                        ),
                        "cleanup": cleanup,
                        "evidence": canonical,
                    }
                return {"success": True, "result": "created", "evidence": canonical}
            except FileExistsError:
                if descriptor is not None:
                    os.close(descriptor)
                if open_succeeded:
                    cleanup = cleanup_owned_artifact()
                    return {
                        "success": False,
                        "result": "error",
                        "error": (
                            "[SOURCE LOCK] Exclusive create failed after open: "
                            "artifact unexpectedly reported as existing."
                        ),
                        "cleanup": cleanup,
                        "evidence": cleanup["evidence"],
                    }
                return {
                    "success": False,
                    "result": "exists",
                    "evidence": self.identity(path),
                }
            except OSError as exc:
                if descriptor is not None:
                    os.close(descriptor)
                cleanup = cleanup_owned_artifact()
                return {
                    "success": False,
                    "result": "error",
                    "error": f"[SOURCE LOCK] Exclusive create failed: {exc}",
                    "cleanup": cleanup,
                    "evidence": cleanup["evidence"],
                }

        created = exclusive_create()
        if created["success"]:
            return {"success": True, "lock": payload}
        if created["result"] != "exists":
            return created

        existing_identity = created["evidence"]
        if not existing_identity.get("success"):
            return {
                "success": False,
                "error": (
                    f"[SOURCE LOCK] `{source_path}` has an unreadable lock; "
                    "resolve it before issuing another Task."
                ),
                "result": (
                    "error"
                    if existing_identity.get("uncertain")
                    else "invalid"
                ),
                "evidence": existing_identity,
            }
        existing = existing_identity["payload"]
        if existing.get("node_name") != node_name:
            return {
                "success": False,
                "error": (
                    f"[SOURCE LOCK] `{source_path}` is reserved by Task "
                    f"`{existing.get('task_id', 'unknown')}` for module "
                    f"`{existing.get('node_name', 'unknown')}`."
                ),
                "conflict": existing,
            }

        quarantined = self.quarantine(path, existing_identity)
        if not quarantined["success"]:
            return quarantined

        reissued = exclusive_create()
        if reissued["success"]:
            terminal_cleanup = self._terminal_cleanup_quarantine(
                quarantined["quarantine_path"]
            )
            cleanup = {
                "attempted": True,
                "success": terminal_cleanup["success"],
                "status": terminal_cleanup["status"],
                "quarantine_retained": terminal_cleanup["quarantine_retained"],
                "canonical_cleared": True,
                "artifact_deleted": terminal_cleanup["artifact_deleted"],
                "delete_attempted": terminal_cleanup["delete_attempted"],
                "manual_action_required": terminal_cleanup["manual_action_required"],
                "quarantine_path": quarantined["quarantine_path"],
            }
            return {"success": True, "lock": payload, "reissued": True, "cleanup": cleanup}

        canonical = self.identity(path)
        restore = {"attempted": False, "success": False}
        if canonical.get("state") == "missing":
            restore["attempted"] = True
            try:
                os.link(quarantined["quarantine_path"], path)
                restore["success"] = True
            except OSError as exc:
                restore["error"] = str(exc)
            restore.update(
                {
                    "quarantine_retained": True,
                    "canonical_cleared": False,
                    "artifact_deleted": False,
                    "delete_attempted": False,
                    "quarantine_path": quarantined["quarantine_path"],
                }
            )
        else:
            restore["error"] = "Canonical path is occupied or uncertain."
        return {
            "success": False,
            "result": ("conflict" if reissued["result"] == "exists" else "error"),
            "error": (
                "[SOURCE LOCK] Canonical lock changed during force-reissue."
                if reissued["result"] == "exists"
                else reissued["error"]
            ),
            "restore": restore,
            "quarantine_path": quarantined["quarantine_path"],
            "evidence": {
                "canonical": canonical,
                "create": reissued,
                "quarantine": quarantined,
            },
        }
