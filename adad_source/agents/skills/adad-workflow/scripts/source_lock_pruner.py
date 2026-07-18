# -*- coding: utf-8 -*-
"""Source Lock pruner service (#80-A3).

Implements safe stale/orphan lock cleanup via quarantine-then-verify.
Consumed by ADADCore facade and CLI reconcile command.
"""

import os


class SourceLockPruner:
    """Prune stale and orphan Source Lock artifacts via audit + quarantine."""

    def __init__(self, audit_service, repository):
        self.audit_service = audit_service
        self.repository = repository

    def revalidate_candidate(self, candidate):
        """Re-check one candidate immediately before mutation.

        Returns dict with success, uncertain, mutation_blocked.
        Success means identity still matches audit snapshot and lock is still
        stale or orphan (not active/invalid).
        """
        lock_path = candidate.get("canonical_path")
        if not lock_path:
            return {
                "success": False,
                "uncertain": False,
                "mutation_blocked": False,
                "error": "[PRUNER] Candidate has no canonical_path.",
            }

        current = self.repository.identity(lock_path)
        if current.get("uncertain") or current.get("state") == "error":
            return {
                "success": False,
                "uncertain": True,
                "mutation_blocked": True,
                "error": "[PRUNER] Lock identity is uncertain.",
                "evidence": current,
            }

        if current.get("state") == "missing":
            return {
                "success": False,
                "uncertain": False,
                "mutation_blocked": False,
                "error": "[PRUNER] Lock already absent.",
            }

        expected_digest = candidate.get("payload_digest")
        expected_identity = candidate.get("lstat_identity")
        if (
            current.get("payload_digest") != expected_digest
            or current.get("identity") != expected_identity
        ):
            return {
                "success": False,
                "uncertain": False,
                "mutation_blocked": False,
                "error": "[PRUNER] Lock identity changed after audit.",
                "evidence": current,
            }

        fresh_scan = self.audit_service.scan_state()
        if fresh_scan.get("mutation_blocked"):
            return {
                "success": False,
                "uncertain": True,
                "mutation_blocked": True,
                "error": "[PRUNER] Fresh scan is mutation-blocked.",
            }

        classification = self.audit_service.classify(lock_path, fresh_scan)
        if classification.get("uncertain"):
            return {
                "success": False,
                "uncertain": True,
                "mutation_blocked": True,
                "error": "[PRUNER] Re-classification is uncertain.",
                "evidence": classification,
            }

        if classification.get("classification") not in {"stale", "orphan"}:
            return {
                "success": False,
                "uncertain": False,
                "mutation_blocked": False,
                "error": (
                    "[PRUNER] Lock is no longer prunable: "
                    + repr(classification.get("classification")) + "."
                ),
                "evidence": classification,
            }

        return {
            "success": True,
            "uncertain": False,
            "mutation_blocked": False,
            "classification": classification,
        }

    def prune(self):
        """Prune all stale and orphan locks identified by audit.

        Returns dict:
          success          - all candidates were pruned (no skips)
          mutations        - list of per-candidate outcomes
          post_audit       - fresh audit run after all mutations
          prune_receipt    - summary counts for CLI reporting
          mutation_blocked - True if stopped early due to uncertainty
        """
        initial_audit = self.audit_service.audit()
        if initial_audit.get("mutation_blocked"):
            return {
                "success": False,
                "mutation_blocked": True,
                "mutations": [],
                "prune_receipt": {"pruned": 0, "skipped": 0, "quarantined": 0},
                "error": "[PRUNER] Audit is mutation-blocked; no pruning performed.",
                "audit": initial_audit,
            }

        candidates = (
            initial_audit.get("categories", {}).get("stale", [])
            + initial_audit.get("categories", {}).get("orphan", [])
        )

        # Preflight pass
        preflight = []
        for candidate in candidates:
            check = self.revalidate_candidate(candidate)
            preflight.append({"candidate": candidate, "result": check})
            if check.get("uncertain") or check.get("mutation_blocked"):
                return {
                    "success": False,
                    "mutation_blocked": True,
                    "mutations": [],
                    "preflight": preflight,
                    "prune_receipt": {"pruned": 0, "skipped": 0, "quarantined": 0},
                    "error": check.get("error") or "[PRUNER] Preflight uncertain.",
                    "audit": initial_audit,
                }

        # Mutation pass
        mutations = []
        for item in preflight:
            candidate = item["candidate"]
            check = item["result"]

            if not check.get("success"):
                mutations.append({
                    "action": "skipped",
                    "candidate": candidate,
                    "error": check.get("error"),
                })
                continue

            path = candidate["canonical_path"]
            expected = {
                "identity": candidate.get("lstat_identity"),
                "payload_digest": candidate.get("payload_digest"),
            }

            quarantined = self.repository.quarantine(path, expected)
            if not quarantined.get("success"):
                mutations.append({
                    "action": "skipped",
                    "candidate": candidate,
                    "error": quarantined.get("error"),
                    "evidence": quarantined,
                })
                continue

            # Post-quarantine verification
            fresh_scan = self.audit_service.scan_state()
            qcheck = self.repository.identity(quarantined["quarantine_path"])

            active_claim = any(
                (
                    snapshot.get("validation", {}).get("valid")
                    and snapshot.get("data", {}).get("status")
                    in {"in_progress", "assigned", "submitted"}
                    and snapshot.get("data", {}).get("source_lock", {}).get(
                        "source_path"
                    ) == candidate.get("source_path")
                )
                for snapshot in fresh_scan.get("task_snapshots", {}).values()
            )

            stable = (
                fresh_scan.get("healthy") is True
                and not active_claim
                and qcheck.get("success") is True
                and qcheck.get("identity") == quarantined.get("identity")
                and qcheck.get("payload_digest") == quarantined.get("payload_digest")
            )

            if not stable:
                restore = {"attempted": False, "success": False}
                canonical_check = self.repository.identity(path)
                if canonical_check.get("state") == "missing":
                    restore["attempted"] = True
                    try:
                        os.rename(quarantined["quarantine_path"], path)
                        restore["success"] = True
                    except OSError as exc:
                        restore["error"] = str(exc)
                else:
                    restore["error"] = "Canonical path occupied or uncertain."

                mutations.append({
                    "action": "skipped",
                    "candidate": candidate,
                    "error": "[PRUNER] Claim or identity changed after quarantine.",
                    "quarantine": quarantined,
                    "restore": restore,
                })

                if not fresh_scan.get("healthy"):
                    return {
                        "success": False,
                        "mutation_blocked": True,
                        "mutations": mutations,
                        "preflight": preflight,
                        "prune_receipt": _receipt(mutations),
                        "error": "[PRUNER] Global scan became uncertain during mutation.",
                        "audit": initial_audit,
                    }
                continue

            cleanup = self.repository._terminal_cleanup_quarantine(quarantined["quarantine_path"])
            if cleanup.get("success") and cleanup.get("status") == "removed":
                mutations.append({
                    "action": "pruned",
                    "candidate": candidate,
                    "quarantine": quarantined,
                })
            else:
                mutations.append({
                    "action": "quarantined",
                    "candidate": candidate,
                    "error": "[PRUNER] Quarantine remove failed: " + str(cleanup.get("error", "unknown")),
                    "quarantine": quarantined,
                })

        post_audit = self.audit_service.audit()
        receipt = _receipt(mutations)
        success = all(m["action"] == "pruned" for m in mutations)
        return {
            "success": success,
            "mutation_blocked": False,
            "mutations": mutations,
            "preflight": preflight,
            "prune_receipt": receipt,
            "post_audit": post_audit,
            "audit": initial_audit,
        }


def _receipt(mutations):
    counts = {"pruned": 0, "skipped": 0, "quarantined": 0}
    for m in mutations:
        action = m.get("action", "skipped")
        if action in counts:
            counts[action] += 1
        else:
            counts["skipped"] += 1
    return counts


def prune(audit_service, repository):
    """Module-level entry-point mirroring audit_service module pattern."""
    return SourceLockPruner(audit_service, repository).prune()
