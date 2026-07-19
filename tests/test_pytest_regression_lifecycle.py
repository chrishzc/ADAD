# -*- coding: utf-8 -*-
import os
import subprocess
import importlib
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest


pytestmark = pytest.mark.regression_backlog


REPO_ROOT = Path(__file__).resolve().parents[1]
PYTEST_PYTHON = Path(sys.executable)


def _project_root(tmp_path):
    project_root = tmp_path / "project"
    tests_root = project_root / "tests"
    tests_root.mkdir(parents=True)
    (tests_root / "conftest.py").write_text(
        (REPO_ROOT / "tests" / "conftest.py").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    return project_root


def _write_test_file(project_root, relative_path, content):
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _run_isolated_pytest(project_root, *args):
    return _run_isolated_pytest_with_env(project_root, {}, *args)


def _run_isolated_pytest_with_env(project_root, env_overrides, *args):
    cmd = [
        str(PYTEST_PYTHON),
        "-m",
        "pytest",
        "-q",
        "-p",
        "no:cacheprovider",
        *args,
    ]
    base_env = dict(os.environ)
    base_env.update(env_overrides)
    return subprocess.run(cmd, cwd=project_root, capture_output=True, text=True, env=base_env)


_FIXTURE_STATE_FIELDS = {
    "temporary_files",
    "preserve",
    "run_root",
    "run_root_identity",
    "run_root_created",
    "run_root_verified",
    "fixture_status",
}


def _assert_rejected_fixture_state(state, expected_status):
    assert set(state) == _FIXTURE_STATE_FIELDS
    assert state["fixture_status"] == expected_status
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False


def test_temporary_marked_file_must_live_under_tests_temporary(tmp_path):
    project = _project_root(tmp_path)
    outside = _write_test_file(
        project,
        "tests/outside.py",
        "import pytest\n"
        "TEMPORARY_TEST_PURPOSE = \"outside\"\n"
        "@pytest.mark.temporary\n"
        "def test_outside_temporary():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        "tests/_temporary/../outside.py",
        "--basetemp",
        "tmp-lifecycle-invalid",
    )

    assert result.returncode == 4
    assert outside.exists()
    assert "tests/_temporary/**/*.py" in result.stdout + result.stderr


def test_temporary_marked_file_requires_purpose(tmp_path):
    project = _project_root(tmp_path)
    marked = _write_test_file(
        project,
        "tests/_temporary/test_no_purpose.py",
        "import pytest\n"
        "@pytest.mark.temporary\n"
        "def test_no_purpose():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        str(marked.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-no-purpose",
    )

    assert result.returncode == 4
    assert marked.exists()
    assert "TEMPORARY_TEST_PURPOSE" in (result.stderr + result.stdout)


def test_temporary_abs_path_and_temporary_marker(tmp_path):
    project = _project_root(tmp_path)
    marked = _write_test_file(
        project,
        "tests/_temporary/test_absolute_path.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"absolute\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_absolute_path():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        str(marked.resolve()),
        "--basetemp",
        "tmp-lifecycle-abs",
    )

    assert result.returncode == 0
    assert not marked.exists()


def test_temporary_cannot_be_marked_regression_backlog(tmp_path):
    project = _project_root(tmp_path)
    marked = _write_test_file(
        project,
        "tests/_temporary/test_conflict.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"conflict purpose\"\n\n"
        "@pytest.mark.temporary\n"
        "@pytest.mark.regression_backlog\n"
        "def test_conflict():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        str(marked.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-conflict",
    )

    assert result.returncode == 4
    assert marked.exists()


def test_temporary_symlink_path_is_rejected(tmp_path):
    project = _project_root(tmp_path)
    outside_root = project / "outside"
    outside_root.mkdir()
    real_test = _write_test_file(
        outside_root,
        "real_temporary.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"real\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_real():\n"
        "    assert True\n",
    )
    linked_test = project / "tests" / "_temporary" / "linked_temporary.py"
    linked_test.parent.mkdir(parents=True, exist_ok=True)
    try:
        linked_test.symlink_to(real_test)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            linked_test.write_text(
                "import pytest\n"
                "@pytest.mark.temporary\n"
                "def test_real():\n"
                "    assert True\n",
                encoding="utf-8",
            )
        else:
            raise

    result = _run_isolated_pytest(
        project,
        str(linked_test.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-symlink",
    )

    assert result.returncode == 4
    assert linked_test.exists()


def test_temporary_artifacts_cleanup_only_success_and_only_marked_files(tmp_path):
    project = _project_root(tmp_path)
    cleanup_target = _write_test_file(
        project,
        "tests/_temporary/test_cleanup_success.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"cleanup target\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_keep_temp_file():\n"
        "    assert True\n",
    )
    not_target = _write_test_file(
        project,
        "tests/_temporary/test_skipped_candidate.py",
        "def test_kept_regular_temporary_file():\n"
        "    assert True\n",
    )
    foreign_root = project / ".pytest-temporary" / "foreign-root"
    foreign_root.mkdir(parents=True, exist_ok=True)
    (foreign_root / "keep.txt").write_text("keep", encoding="utf-8")

    (project / ".pytest-temporary").mkdir(exist_ok=True)
    (project / ".pytest-temporary" / "unsafe.txt").write_text(
        "protect",
        encoding="utf-8",
    )
    (project / ".venv").mkdir(exist_ok=True)
    (project / ".venv" / "protect.txt").write_text("protect", encoding="utf-8")
    (project / "__pycache__").mkdir(exist_ok=True)
    (project / "__pycache__" / "protect.pyc").write_text("protect", encoding="utf-8")
    (project / "build").mkdir(exist_ok=True)
    (project / "build" / "protect.txt").write_text("protect", encoding="utf-8")

    result = _run_isolated_pytest(
        project,
        "tests/_temporary",
        "-m",
        "temporary",
        "--basetemp",
        "tmp-lifecycle-clean-success",
    )

    assert result.returncode == 0
    assert not cleanup_target.exists()
    assert not_target.exists()
    assert (project / ".pytest-temporary" / "unsafe.txt").exists()
    assert (project / ".venv" / "protect.txt").exists()
    assert (project / "__pycache__" / "protect.pyc").exists()
    assert (project / "build" / "protect.txt").exists()
    assert foreign_root.exists()


def test_temporary_failure_keeps_collected_file(tmp_path):
    project = _project_root(tmp_path)
    failed = _write_test_file(
        project,
        "tests/_temporary/test_failure_kept.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"failure\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_failure_kept():\n"
        "    assert False\n",
    )

    result = _run_isolated_pytest(
        project,
        str(failed.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-failure",
    )

    assert result.returncode == 1
    assert failed.exists()


def test_temporary_skip_keeps_collected_file(tmp_path):
    project = _project_root(tmp_path)
    skipped = _write_test_file(
        project,
        "tests/_temporary/test_skip_kept.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"skip\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_skip_kept():\n"
        "    pytest.skip(\"keep\")\n",
    )

    result = _run_isolated_pytest(
        project,
        str(skipped.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-skip",
    )

    assert result.returncode == 0
    assert skipped.exists()


def test_temporary_root_runs_on_empty_root_removed(tmp_path):
    project = _project_root(tmp_path)
    clean = _write_test_file(
        project,
        "tests/_temporary/test_root_removed.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"root clean\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_root_removed():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        str(clean.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-root-clean",
    )

    assert result.returncode == 0
    assert not clean.exists()
    temporary_roots = [
        path for path in (project / ".pytest-temporary").iterdir() if path.is_dir()
    ]
    assert temporary_roots == []


def test_temporary_root_non_empty_retained(tmp_path):
    project = _project_root(tmp_path)
    kept = _write_test_file(
        project,
        "tests/_temporary/test_root_nonempty.py",
        "from pathlib import Path\n"
        "import pytest\n"
        "TEMPORARY_TEST_PURPOSE = \"root retained\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_root_nonempty(temporary_artifact_root):\n"
        "    Path(temporary_artifact_root / \"keep-marker.txt\").write_text(\"keep\", encoding=\"utf-8\")\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest(
        project,
        str(kept.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-root-nonempty",
    )

    assert result.returncode == 0
    assert not kept.exists()
    roots = [path for path in (project / ".pytest-temporary").iterdir() if path.is_dir()]
    assert len(roots) == 1
    assert (roots[0] / "keep-marker.txt").exists()


def test_temporary_artifact_root_wrapped_directory_collision_kept_state_collision(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-directory-collision"
    project.mkdir()
    run_id = "0" * 32
    run_root = project / ".pytest-temporary" / run_id
    sentinel = run_root / "sentinel.txt"
    (run_root.parent).mkdir(parents=True, exist_ok=True)
    run_root.mkdir()
    sentinel.write_bytes(b"sentinel-bytes")

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    returned_root = conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert returned_root is None
    assert state["fixture_status"] == "collision"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert run_root.exists()
    assert run_root.is_dir()
    assert sentinel.read_bytes() == b"sentinel-bytes"


def test_temporary_artifact_root_regular_file_preexists_after_fentify_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-file-collision"
    project.mkdir()
    run_id = "c" * 32
    run_root = project / ".pytest-temporary" / run_id
    sentinel = run_root
    (run_root.parent).mkdir(parents=True, exist_ok=True)
    sentinel.write_bytes(b"sentinel-bytes")

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert state["fixture_status"] == "run_root_collision_not_directory"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert sentinel.exists()
    assert sentinel.read_bytes() == b"sentinel-bytes"


def test_temporary_artifact_root_symlink_preexists_after_fentify_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-symlink-collision"
    project.mkdir()
    run_id = "d" * 32
    run_root = project / ".pytest-temporary" / run_id
    target_root = project / "collision-target"
    target_root.mkdir(parents=True, exist_ok=True)
    sentinel = target_root / "sentinel.txt"
    sentinel.write_bytes(b"sentinel-bytes")
    (run_root.parent).mkdir(parents=True, exist_ok=True)

    try:
        run_root.symlink_to(target_root, target_is_directory=True)
    except OSError as exc:
        if getattr(exc, "winerror", None) == 1314:
            pytest.skip(f"symlink permission denied: {exc}")
        raise

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert state["fixture_status"] == "run_root_collision_is_symlink"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert target_root.exists()
    assert sentinel.read_bytes() == b"sentinel-bytes"


def test_temporary_artifact_root_collision_lstat_failure_after_file_exists_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-collision-lstat-io"
    project.mkdir()
    run_id = "e" * 32
    run_root = project / ".pytest-temporary" / run_id
    sentinel = run_root / "sentinel.txt"
    (run_root.parent).mkdir(parents=True, exist_ok=True)
    run_root.mkdir(parents=True)
    sentinel.write_bytes(b"sentinel-bytes")

    original_lstat = conftest.Path.lstat

    def _lstat_fail(path):
        if path == run_root:
            raise OSError("lstat denied")
        return original_lstat(path)

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, "lstat", _lstat_fail, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert state["fixture_status"] == "run_root_collision_io"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert run_root.exists()
    assert run_root.is_dir()
    assert sentinel.read_bytes() == b"sentinel-bytes"


def test_temporary_artifact_root_collision_retains_root_and_files(tmp_path):
    project = _project_root(tmp_path)
    collision_run_id = "0" * 32
    collision_root = project / ".pytest-temporary" / collision_run_id
    (project / ".pytest-temporary").mkdir(exist_ok=True)
    collision_root.mkdir(parents=True, exist_ok=True)
    (collision_root / "collide.txt").write_text("pre-existing", encoding="utf-8")

    target = _write_test_file(
        project,
        "tests/_temporary/test_collision_collision.py",
        "import pytest\n"
        "TEMPORARY_TEST_PURPOSE = \"collision\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_temporary_collision_target():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest_with_env(
        project,
        {"PYTEST_TEMPORARY_RUN_ID": collision_run_id},
        str(target.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-collision",
    )

    assert result.returncode == 0
    assert target.exists()
    assert collision_root.exists()
    assert (collision_root / "collide.txt").exists()


def test_temporary_artifact_root_collision_retains_existing_root_and_no_new_artifacts(tmp_path):
    project = _project_root(tmp_path)
    collision_run_id = "b" * 32
    collision_root = project / ".pytest-temporary" / collision_run_id
    (project / ".pytest-temporary").mkdir(exist_ok=True)
    collision_root.mkdir(parents=True, exist_ok=True)
    sentinel = collision_root / "sentinel.txt"
    sentinel.write_bytes(b"sentinel-bytes")

    target = _write_test_file(
        project,
        "tests/_temporary/test_collision_root_none_fixture.py",
        "import pytest\n"
        "from pathlib import Path\n\n"
        "TEMPORARY_TEST_PURPOSE = \"collision fixture none\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_collision_root_none_fixture(temporary_artifact_root):\n"
        "    assert temporary_artifact_root is None\n"
        "    assert Path(__file__).exists()\n",
    )

    result = _run_isolated_pytest_with_env(
        project,
        {"PYTEST_TEMPORARY_RUN_ID": collision_run_id},
        str(target.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-collision-none-fixture",
    )

    assert result.returncode == 0
    assert target.exists()
    assert sentinel.exists()
    assert sentinel.read_bytes() == b"sentinel-bytes"
    assert [p.name for p in collision_root.iterdir()] == ["sentinel.txt"]


def test_temporary_artifact_root_identity_mismatch_retains_root(tmp_path):
    project = _project_root(tmp_path)
    run_id = "f" * 32
    target = _write_test_file(
        project,
        "tests/_temporary/test_root_identity_mismatch.py",
        "import pytest\n\n"
        "TEMPORARY_TEST_PURPOSE = \"ownership\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_root_identity_mismatch(temporary_artifact_root):\n"
        "    temporary_artifact_root.rmdir()\n"
        "    temporary_artifact_root.write_text(\"identity swapped\", encoding=\"utf-8\")\n",
    )

    result = _run_isolated_pytest_with_env(
        project,
        {"PYTEST_TEMPORARY_RUN_ID": run_id},
        str(target.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-ownership",
    )

    assert result.returncode == 0
    roots = [
        path for path in (project / ".pytest-temporary").iterdir() if path.name == run_id
    ]
    assert len(roots) == 1
    assert roots[0].is_file()


def test_temporary_artifact_root_wrapped_parent_unsafe_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-unsafe-parent"
    project.mkdir()
    run_id = "a" * 32
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    original_safe = conftest._path_safe_for_temporary

    def _safe_for_temporary(path):
        if path == project / ".pytest-temporary":
            return False
        return original_safe(path)

    monkeypatch.setattr(conftest, "_path_safe_for_temporary", _safe_for_temporary)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    assert state["fixture_status"] == "run_root_parent_unsafe"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert not (project / ".pytest-temporary").exists()


def test_temporary_source_replaced_by_unsafe_type_after_collection_is_preserved(tmp_path):
    project = _project_root(tmp_path)
    marked = _write_test_file(
        project,
        "tests/_temporary/test_mutate_source_after_collection.py",
        "from pathlib import Path\n"
        "import pytest\n\n"
        "TEMPORARY_TEST_PURPOSE = \"mutate source\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_mutate_source_after_collection():\n"
        "    source = Path(__file__)\n"
        "    try:\n"
        "        source.unlink()\n"
        "    except OSError as exc:\n"
        "        pytest.skip(f\"source file unlink failed: {exc}\")\n"
        "    source.mkdir()\n"
        "    assert source.is_dir()\n",
    )

    result = _run_isolated_pytest(
        project,
        str(marked.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-unsafe-source-after-collect",
    )

    assert result.returncode == 0
    assert marked.exists()
    assert marked.is_dir()


def test_temporary_artifact_root_invalid_run_id_retains_temporary_and_never_creates_root(tmp_path):
    project = _project_root(tmp_path)
    invalid_run_id = "INVALID-RUN-ID"
    marked = _write_test_file(
        project,
        "tests/_temporary/test_invalid_run_id.py",
        "import pytest\nTEMPORARY_TEST_PURPOSE = \"invalid run id\"\n\n"
        "@pytest.mark.temporary\n"
        "def test_invalid_run_id():\n"
        "    assert True\n",
    )

    result = _run_isolated_pytest_with_env(
        project,
        {"PYTEST_TEMPORARY_RUN_ID": invalid_run_id},
        str(marked.relative_to(project)),
        "--basetemp",
        "tmp-lifecycle-invalid-run-id",
    )

    assert result.returncode == 1
    assert marked.exists()
    assert not (project / ".pytest-temporary").exists()


def test_temporary_artifact_root_wrapped_invalid_run_id_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-invalid-run-id"
    project.mkdir()
    invalid_run_id = "INVALID-RUN-ID"
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", invalid_run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    assert state["fixture_status"] == "invalid_run_id"
    assert state["preserve"] is True
    assert state["run_root"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert not (project / ".pytest-temporary").exists()


def test_temporary_artifact_root_wrapped_identity_oserror_preserves_root_and_returns_none(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-patched-repo-root"
    project.mkdir()
    run_id = "c" * 32
    run_root = project / ".pytest-temporary" / run_id

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    def _broken_identity(_path):
        raise OSError("temporary root identity denied")

    monkeypatch.setattr(conftest, "_temporary_root_identity", _broken_identity, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert state["preserve"] is True
    assert state["fixture_status"] == "run_root_metadata_failure"
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert run_root.exists()
    assert list(run_root.iterdir()) == []


def test_temporary_artifact_root_wrapped_directory_to_file_after_mkdir_is_rejected(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-root-converted-to-file"
    project.mkdir()
    run_id = "e" * 32
    run_root = project / ".pytest-temporary" / run_id
    sentinel = b"replacement-bytes"
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    original_lstat = conftest.Path.lstat
    state = {"done": False}

    def _lstat_replace_with_file(path):
        if path == run_root and not state["done"]:
            path.rmdir()
            path.write_bytes(sentinel)
            state["done"] = True
        return original_lstat(path)

    monkeypatch.setattr(conftest.Path, "lstat", _lstat_replace_with_file, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)
    lifecycle_state = conftest._temporary_lifecycle_state(request.config)

    assert lifecycle_state["preserve"] is True
    assert lifecycle_state["fixture_status"] == "run_root_not_directory"
    assert lifecycle_state["run_root"] is None
    assert lifecycle_state["run_root_identity"] is None
    assert lifecycle_state["run_root_created"] is False
    assert lifecycle_state["run_root_verified"] is False
    assert run_root.exists()
    assert run_root.is_file()
    assert run_root.read_bytes() == sentinel


def test_temporary_artifact_root_wrapped_success_returns_verified_root(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-success-root"
    project.mkdir()
    run_id = "d" * 32
    run_root = project / ".pytest-temporary" / run_id

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    returned_root = conftest.temporary_artifact_root.__wrapped__(request)
    state = conftest._temporary_lifecycle_state(request.config)

    assert returned_root == run_root
    assert returned_root is not None
    assert state["preserve"] is False
    assert state["fixture_status"] == "ready"
    assert state["run_root"] == run_root
    assert state["run_root_created"] is True
    assert state["run_root_verified"] is True
    assert state["run_root_identity"] == conftest._temporary_root_identity(run_root)
    assert returned_root.exists()
    assert list(returned_root.iterdir()) == []


def test_temporary_lifecycle_state_has_exact_fixed_fields():
    conftest = importlib.import_module("tests.conftest")
    config = SimpleNamespace()

    state = conftest._temporary_lifecycle_state(config)

    assert set(state) == _FIXTURE_STATE_FIELDS
    assert state["temporary_files"] == set()
    assert state["preserve"] is False
    assert state["run_root"] is None
    assert state["run_root_identity"] is None
    assert state["run_root_created"] is False
    assert state["run_root_verified"] is False
    assert state["fixture_status"] == "uninitialized"


def test_temporary_artifact_root_collision_junction_is_deterministically_rejected(
    tmp_path, monkeypatch
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-junction-collision"
    project.mkdir()
    run_id = "1" * 32
    run_root = project / ".pytest-temporary" / run_id
    run_root.mkdir(parents=True)
    sentinel = run_root / "sentinel.txt"
    sentinel.write_bytes(b"junction-collision")
    original_is_junction = getattr(conftest.Path, "is_junction", None)

    def _is_junction(path):
        if path == run_root:
            return True
        return bool(original_is_junction(path)) if original_is_junction else False

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, "is_junction", _is_junction, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, "run_root_collision_is_junction")
    assert run_root.exists()
    assert sentinel.read_bytes() == b"junction-collision"


@pytest.mark.parametrize(
    ("link_method", "expected_status"),
    [
        ("is_symlink", "run_root_is_symlink"),
        ("is_junction", "run_root_is_junction"),
    ],
)
def test_temporary_artifact_root_post_mkdir_link_is_deterministically_rejected(
    tmp_path, monkeypatch, link_method, expected_status
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-post-mkdir-{link_method}"
    project.mkdir()
    run_id = "2" * 32
    run_root = project / ".pytest-temporary" / run_id
    original_link_check = getattr(conftest.Path, link_method, None)

    def _is_link(path):
        if path == run_root:
            return True
        return bool(original_link_check(path)) if original_link_check else False

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, link_method, _is_link, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, expected_status)
    assert run_root.exists()
    assert list(run_root.iterdir()) == []


@pytest.mark.parametrize("link_method", ["is_symlink", "is_junction"])
def test_temporary_artifact_root_parent_link_is_rejected_before_mkdir(
    tmp_path, monkeypatch, link_method
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-parent-{link_method}"
    project.mkdir()
    run_id = "3" * 32
    temporary_parent = project / ".pytest-temporary"
    original_link_check = getattr(conftest.Path, link_method, None)

    def _is_link(path):
        if path == temporary_parent:
            return True
        return bool(original_link_check(path)) if original_link_check else False

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, link_method, _is_link, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, "run_root_parent_unsafe")
    assert not temporary_parent.exists()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("boundary", "run_root_parent_outside_boundary"),
        ("io", "run_root_parent_io"),
    ],
)
def test_temporary_artifact_root_parent_boundary_and_io_reject_before_mkdir(
    tmp_path, monkeypatch, failure, expected_status
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-parent-{failure}"
    project.mkdir()
    run_id = "4" * 32
    temporary_parent = project / ".pytest-temporary"
    original_resolve = conftest.Path.resolve
    calls = {"parent": 0}

    def _resolve(path, *args, **kwargs):
        if path == temporary_parent:
            calls["parent"] += 1
            if failure == "io":
                raise OSError("parent resolve denied")
            if calls["parent"] == 2:
                return project / "outside-boundary"
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, "resolve", _resolve, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, expected_status)
    assert not temporary_parent.exists()


def test_temporary_artifact_root_mkdir_noncollision_io_rejects(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-mkdir-io"
    project.mkdir()
    run_id = "5" * 32
    run_root = project / ".pytest-temporary" / run_id
    original_mkdir = conftest.Path.mkdir

    def _mkdir(path, *args, **kwargs):
        if path == run_root:
            raise OSError("mkdir denied")
        return original_mkdir(path, *args, **kwargs)

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest.Path, "mkdir", _mkdir, raising=False)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, "run_root_create_io")
    assert not run_root.exists()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("symlink", "run_root_parent_unsafe"),
        ("junction", "run_root_parent_unsafe"),
        ("boundary", "run_root_parent_boundary_changed"),
    ],
)
def test_temporary_artifact_root_post_mkdir_parent_race_rejects(
    tmp_path, monkeypatch, failure, expected_status
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-post-mkdir-parent-{failure}"
    project.mkdir()
    run_id = "6" * 32
    temporary_parent = project / ".pytest-temporary"
    run_root = temporary_parent / run_id

    if failure in {"symlink", "junction"}:
        method_name = "is_symlink" if failure == "symlink" else "is_junction"
        original_link_check = getattr(conftest.Path, method_name, None)
        calls = {"parent_link": 0}

        def _is_link(path):
            if path == temporary_parent:
                calls["parent_link"] += 1
                return calls["parent_link"] >= 2
            return bool(original_link_check(path)) if original_link_check else False

        monkeypatch.setattr(conftest.Path, method_name, _is_link, raising=False)
    else:
        original_resolve = conftest.Path.resolve
        calls = {"parent": 0}

        def _resolve(path, *args, **kwargs):
            if path == temporary_parent:
                calls["parent"] += 1
                if calls["parent"] == 3:
                    return project / "outside-boundary"
            return original_resolve(path, *args, **kwargs)

        monkeypatch.setattr(conftest.Path, "resolve", _resolve, raising=False)

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, expected_status)
    assert run_root.exists()


@pytest.mark.parametrize(
    ("failure", "expected_status"),
    [
        ("unsafe", "run_root_collision_parent_unsafe"),
        ("boundary", "run_root_collision_parent_boundary_changed"),
    ],
)
def test_temporary_artifact_root_collision_parent_race_rejects(
    tmp_path, monkeypatch, failure, expected_status
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-collision-parent-{failure}"
    project.mkdir()
    run_id = "7" * 32
    temporary_parent = project / ".pytest-temporary"
    run_root = temporary_parent / run_id
    run_root.mkdir(parents=True)
    sentinel = run_root / "sentinel.txt"
    sentinel.write_bytes(b"collision-parent-race")

    if failure == "unsafe":
        original_safe = conftest._path_safe_for_temporary
        calls = {"parent": 0}

        def _safe(path):
            if path == temporary_parent:
                calls["parent"] += 1
                return calls["parent"] == 1
            return original_safe(path)

        monkeypatch.setattr(conftest, "_path_safe_for_temporary", _safe)
    else:
        original_resolve = conftest.Path.resolve
        calls = {"parent": 0}

        def _resolve(path, *args, **kwargs):
            if path == temporary_parent:
                calls["parent"] += 1
                if calls["parent"] == 3:
                    return project / "outside-boundary"
            return original_resolve(path, *args, **kwargs)

        monkeypatch.setattr(conftest.Path, "resolve", _resolve, raising=False)

    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    request = SimpleNamespace(config=SimpleNamespace())
    with pytest.raises(pytest.UsageError):
        conftest.temporary_artifact_root.__wrapped__(request)

    state = conftest._temporary_lifecycle_state(request.config)
    _assert_rejected_fixture_state(state, expected_status)
    assert sentinel.read_bytes() == b"collision-parent-race"


def test_temporary_collection_io_is_usage_error_with_zero_mutation(tmp_path, monkeypatch):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-collection-io"
    path = _write_test_file(
        project,
        "tests/_temporary/test_collection_io.py",
        "TEMPORARY_TEST_PURPOSE = 'collection io'\ndef test_collection_io(): assert True\n",
    )
    sentinel = path.read_bytes()

    class _Item:
        def __init__(self, item_path):
            self.path = item_path

        def get_closest_marker(self, name):
            return object() if name == "temporary" else None

    def _purpose_io(_path):
        raise OSError("purpose read denied")

    monkeypatch.setattr(conftest, "REPO_ROOT", project)
    monkeypatch.setattr(conftest, "_temporary_test_purpose", _purpose_io)
    config = SimpleNamespace()

    with pytest.raises(pytest.UsageError):
        conftest.pytest_collection_modifyitems(None, config, [_Item(path)])

    state = conftest._temporary_lifecycle_state(config)
    assert state["preserve"] is True
    assert state["temporary_files"] == set()
    assert path.read_bytes() == sentinel
    assert not (project / ".pytest-temporary").exists()


@pytest.mark.parametrize(
    "failure",
    ["missing", "outside", "symlink", "junction", "nonregular", "io"],
)
def test_temporary_cleanup_batch_preflight_failure_has_zero_unlink(
    tmp_path, monkeypatch, failure
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-cleanup-preflight-{failure}"
    project.mkdir()
    run_id = "8" * 32
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    config = SimpleNamespace()
    request = SimpleNamespace(config=config)
    run_root = conftest.temporary_artifact_root.__wrapped__(request)
    safe = _write_test_file(
        project,
        "tests/_temporary/test_a_safe.py",
        "TEMPORARY_TEST_PURPOSE = 'safe'\ndef test_safe(): assert True\n",
    )
    bad = project / "tests" / "_temporary" / "test_z_bad.py"
    if failure == "outside":
        bad = _write_test_file(
            project,
            "outside/test_z_bad.py",
            "TEMPORARY_TEST_PURPOSE = 'outside'\ndef test_bad(): assert True\n",
        )
    elif failure == "nonregular":
        bad.mkdir(parents=True)
    elif failure != "missing":
        _write_test_file(
            project,
            "tests/_temporary/test_z_bad.py",
            "TEMPORARY_TEST_PURPOSE = 'bad'\ndef test_bad(): assert True\n",
        )

    if failure in {"symlink", "junction"}:
        method_name = "is_symlink" if failure == "symlink" else "is_junction"
        original_link_check = getattr(conftest.Path, method_name, None)

        def _is_link(path):
            if path == bad:
                return True
            return bool(original_link_check(path)) if original_link_check else False

        monkeypatch.setattr(conftest.Path, method_name, _is_link, raising=False)
    elif failure == "io":
        original_lstat = conftest.Path.lstat

        def _lstat(path):
            if path == bad:
                raise OSError("source lstat denied")
            return original_lstat(path)

        monkeypatch.setattr(conftest.Path, "lstat", _lstat, raising=False)

    original_unlink = conftest.Path.unlink
    unlinked = []

    def _unlink(path, *args, **kwargs):
        unlinked.append(path)
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(conftest.Path, "unlink", _unlink, raising=False)
    state = conftest._temporary_lifecycle_state(config)
    state["temporary_files"] = {safe, bad}

    conftest.pytest_sessionfinish(SimpleNamespace(config=config), 0)

    assert state["fixture_status"] == "ready"
    assert state["preserve"] is True
    assert unlinked == []
    assert safe.exists()
    assert run_root.exists()
    if failure != "missing":
        assert bad.exists()


@pytest.mark.parametrize("link_method", ["is_symlink", "is_junction"])
def test_temporary_cleanup_rejects_run_root_link_before_source_unlink(
    tmp_path, monkeypatch, link_method
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / f"project-with-cleanup-root-{link_method}"
    project.mkdir()
    run_id = "9" * 32
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    config = SimpleNamespace()
    run_root = conftest.temporary_artifact_root.__wrapped__(
        SimpleNamespace(config=config)
    )
    source = _write_test_file(
        project,
        "tests/_temporary/test_root_link.py",
        "TEMPORARY_TEST_PURPOSE = 'root link'\ndef test_root_link(): assert True\n",
    )
    state = conftest._temporary_lifecycle_state(config)
    state["temporary_files"] = {source}
    original_link_check = getattr(conftest.Path, link_method, None)

    def _is_link(path):
        if path == run_root:
            return True
        return bool(original_link_check(path)) if original_link_check else False

    monkeypatch.setattr(conftest.Path, link_method, _is_link, raising=False)

    conftest.pytest_sessionfinish(SimpleNamespace(config=config), 0)

    assert state["fixture_status"] == "ready"
    assert state["preserve"] is True
    assert source.exists()
    assert run_root.exists()


def test_temporary_cleanup_rmdir_error_preserves_root_after_source_cleanup(
    tmp_path, monkeypatch
):
    conftest = importlib.import_module("tests.conftest")
    project = tmp_path / "project-with-rmdir-error"
    project.mkdir()
    run_id = "a" * 32
    monkeypatch.setenv("PYTEST_TEMPORARY_RUN_ID", run_id)
    monkeypatch.setattr(conftest, "REPO_ROOT", project)

    config = SimpleNamespace()
    run_root = conftest.temporary_artifact_root.__wrapped__(
        SimpleNamespace(config=config)
    )
    source = _write_test_file(
        project,
        "tests/_temporary/test_rmdir_error.py",
        "TEMPORARY_TEST_PURPOSE = 'rmdir error'\ndef test_rmdir_error(): assert True\n",
    )
    state = conftest._temporary_lifecycle_state(config)
    state["temporary_files"] = {source}
    original_rmdir = conftest.Path.rmdir

    def _rmdir(path):
        if path == run_root:
            raise OSError("rmdir denied")
        return original_rmdir(path)

    monkeypatch.setattr(conftest.Path, "rmdir", _rmdir, raising=False)

    conftest.pytest_sessionfinish(SimpleNamespace(config=config), 0)

    assert state["fixture_status"] == "ready"
    assert state["preserve"] is True
    assert not source.exists()
    assert run_root.exists()
