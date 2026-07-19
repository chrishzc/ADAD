# -*- coding: utf-8 -*-
import json
import os
import sys
import pytest
from pathlib import Path

# Load core and repository modules using the standard test harness setup
from test_source_lock_repository import _repository, SourceLockRepository, _write_lock

def test_cleanup_owned_artifact_aborts_on_competitor_task_id(tmp_path, monkeypatch):
    repo = _repository(tmp_path)

    # 1. We mock write to fail by raising OSError during payload write,
    # but we intercept the owned fd dev/ino.
    captured_fd_identity = None

    # We want to force a cleanup after open is successful.
    # To do that, we can mock `os.fdopen` to capture the fd stats and then raise an OSError!
    # We do NOT close the fd here because the except block in acquire will close it.
    def fake_fdopen(fd, mode):
        nonlocal captured_fd_identity
        details = os.fstat(fd)
        captured_fd_identity = {"st_dev": details.st_dev, "st_ino": details.st_ino}
        raise OSError("Simulated write failure during acquire")

    monkeypatch.setattr(os, "fdopen", fake_fdopen)

    # We also need to mock `repo.identity` during the cleanup phase.
    # When cleanup calls `self.identity(path)`, we want it to return a competitor's valid lock payload
    # but claiming the SAME st_dev/st_ino!
    original_identity = repo.identity
    def fake_identity(path):
        # When called inside cleanup_owned_artifact, captured_fd_identity is set.
        if captured_fd_identity is not None:
            return {
                "success": True,
                "state": "present",
                "identity": captured_fd_identity,  # Reuse the exact same inode/dev!
                "payload": {
                    "source_path": "sample_tool.py",
                    "node_name": "sample_tool",
                    "task_id": "competitor_task_v1_xyz",  # DIFFERENT task_id!
                    "acquired_at": "some-date"
                },
                "payload_digest": "some-digest"
            }
        return original_identity(path)

    monkeypatch.setattr(repo, "identity", fake_identity)

    # Call repo.acquire. It will trigger OSError during fdopen, go to cleanup,
    # and fail validation/cleanup because of different task_id!
    result = repo.acquire("sample_tool", "our_task_v1_abc")

    # Assert that acquire returned success = False
    assert result["success"] is False
    # Check that cleanup reports failure because the canonical lock belongs to a different task
    cleanup = result["cleanup"]
    assert cleanup["success"] is False
    assert "belongs to a different task" in cleanup["error"]
