# -*- coding: utf-8 -*-
"""
tests/conftest.py
共用 fixtures、輔助工具，以及 pytest lifecycle hooks。
測試目標在於保證 temporary 測試的隔離與清理行為，且不影響既有 CI 行為。
"""
import ast
import json
import os
import stat
import re
import subprocess
import sys
import uuid
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = (
    REPO_ROOT
    / "adad_cli"
    / "resources"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
)

CI_EVENT_ENV_VARS = {
    "CI",
    "GITHUB_ACTIONS",
    "GITHUB_BASE_REF",
    "GITHUB_HEAD_REF",
    "GITHUB_EVENT_NAME",
    "GITHUB_EVENT_PATH",
    "GITHUB_REF",
    "GITHUB_REF_NAME",
    "GITHUB_SHA",
}


def workflow_test_harness(inherited_environment, explicit_env_overrides=None):
    """建立子行程的測試環境，避免 CI env 污染。"""
    child_environment = dict(inherited_environment)
    for name in CI_EVENT_ENV_VARS:
        child_environment.pop(name, None)
    child_environment.update(explicit_env_overrides or {})
    child_environment["PYTHONIOENCODING"] = "utf-8"
    return child_environment


def script_path(name):
    """回傳指定 script 的絕對路徑。"""
    p = SCRIPTS_DIR / name
    assert p.exists(), f"script 不存在：{p}"
    return str(p)


def run_script(name, args=None, cwd=None, input_text=None, env=None):
    """
    執行 adad-workflow 腳本並回傳 (returncode, parsed_json_or_None, stdout, stderr)。
    """
    cmd = [sys.executable, script_path(name)] + (args or [])
    env_vars = workflow_test_harness(os.environ, env)
    # Prepend REPO_ROOT to PYTHONPATH so that local packages (adad_cli) are importable
    python_path = env_vars.get("PYTHONPATH", "")
    repo_root_str = str(REPO_ROOT)
    if python_path:
        env_vars["PYTHONPATH"] = f"{repo_root_str}{os.pathsep}{python_path}"
    else:
        env_vars["PYTHONPATH"] = repo_root_str
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        encoding="utf-8",
        input=input_text if input_text is not None else "",
        env=env_vars,
    )
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return proc.returncode, parsed, proc.stdout, proc.stderr


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """
    建立 isolated 工作目錄並切換 cwd，避免影響主專案。
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_yaml(project_dir, data):
    """將 dict 寫成 YAML。"""
    assert yaml is not None, "缺少 PyYAML，請先安裝：pip install pyyaml"
    with open(project_dir / "system_map.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def read_yaml(project_dir):
    """讀取 YAML。"""
    assert yaml is not None, "缺少 PyYAML，請先安裝：pip install pyyaml"
    with open(project_dir / "system_map.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


_LIFECYCLE_TRACKER_KEY = "_adad_temporary_cleanup_state"
_TEMPORARY_RUN_ID_RE = re.compile(r"[0-9a-f]{32}")


def _temporary_lifecycle_state(config):
    state = getattr(config, _LIFECYCLE_TRACKER_KEY, None)
    if state is None:
        state = {
            "temporary_files": set(),
            "preserve": False,
            "run_root": None,
            "run_root_identity": None,
            "fixture_status": "uninitialized",
            "run_root_created": False,
            "run_root_verified": False,
        }
        setattr(config, _LIFECYCLE_TRACKER_KEY, state)
    return state


def _is_temporary_marker(item):
    return item.get_closest_marker("temporary") is not None


def _is_regression_backlog_marker(item):
    return item.get_closest_marker("regression_backlog") is not None


def _item_path(item):
    raw_path = getattr(item, "path", None) or getattr(item, "fspath", None)
    assert raw_path is not None, "pytest item path unavailable"
    return Path(str(raw_path))


def _is_temporary_path_allowed(repo_root, candidate):
    candidate = Path(candidate)
    if ".." in candidate.as_posix().split("/"):
        return False
    if candidate.suffix.lower() != ".py":
        return False
    if not candidate.is_absolute():
        return False
    try:
        relative = candidate.resolve().relative_to(repo_root.resolve())
    except ValueError:
        return False
    return (
        len(relative.parts) >= 3
        and relative.parts[0] == "tests"
        and relative.parts[1] == "_temporary"
    )


def _path_safe_for_temporary(candidate):
    for part in [candidate, *candidate.parents]:
        if part.is_symlink():
            return False
        is_junction = getattr(part, "is_junction", lambda: False)
        if bool(is_junction()):
            return False
    return True


def _temporary_test_purpose(path):
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source)
    for node in tree.body:
        if (
            isinstance(node, ast.Assign)
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
        ):
            for target in node.targets:
                if (
                    isinstance(target, ast.Name)
                    and target.id == "TEMPORARY_TEST_PURPOSE"
                ):
                    return node.value.value
        if (
            isinstance(node, ast.AnnAssign)
            and node.value is not None
            and isinstance(node.value, ast.Constant)
            and isinstance(node.value.value, str)
            and isinstance(node.target, ast.Name)
            and node.target.id == "TEMPORARY_TEST_PURPOSE"
        ):
            return node.value.value
    return ""


def _is_own_temporary_root(candidate):
    return (
        candidate is not None
        and candidate.parent == REPO_ROOT / ".pytest-temporary"
        and bool(_TEMPORARY_RUN_ID_RE.fullmatch(candidate.name))
    )


def _temporary_root_identity(path):
    info = path.lstat()
    return (
        info.st_mode,
        info.st_ino,
        info.st_dev,
        getattr(info, "st_uid", None),
        getattr(info, "st_gid", None),
    )


@pytest.fixture(scope="session", autouse=True)
def temporary_artifact_root(request):
    state = _temporary_lifecycle_state(request.config)
    run_id = os.environ.get("PYTEST_TEMPORARY_RUN_ID") or uuid.uuid4().hex

    def _reject(status, message):
        state["preserve"] = True
        state["run_root"] = None
        state["run_root_identity"] = None
        state["run_root_created"] = False
        state["run_root_verified"] = False
        state["fixture_status"] = status
        raise pytest.UsageError(message)

    run_root = REPO_ROOT / ".pytest-temporary" / run_id
    state["run_root"] = None
    state["run_root_identity"] = None
    state["run_root_created"] = False
    state["run_root_verified"] = False
    temporary_parent = run_root.parent
    state["fixture_status"] = "initializing"
    if not _TEMPORARY_RUN_ID_RE.fullmatch(run_id):
        _reject("invalid_run_id", f"invalid run-id for temporary fixture: {run_id}")

    try:
        if not _path_safe_for_temporary(temporary_parent):
            _reject("run_root_parent_unsafe", "temporary parent path is unsafe")
        if temporary_parent.resolve() != (REPO_ROOT / ".pytest-temporary").resolve():
            _reject(
                "run_root_parent_outside_boundary",
                "temporary parent outside boundary",
            )
    except OSError:
        _reject("run_root_parent_io", "temporary parent I/O uncertain")

    try:
        run_root.mkdir(parents=True, exist_ok=False)
        state["run_root_created"] = True
    except FileExistsError:
        state["preserve"] = True
        state["run_root"] = None
        state["run_root_identity"] = None
        state["run_root_created"] = False
        state["run_root_verified"] = False
        try:
            if run_root.is_symlink():
                _reject(
                    "run_root_collision_is_symlink",
                    "temporary run-root collision is symlink",
                )
            is_run_root_junction = getattr(run_root, "is_junction", lambda: False)
            if bool(is_run_root_junction()):
                _reject(
                    "run_root_collision_is_junction",
                    "temporary run-root collision is junction",
                )
            info = run_root.lstat()
            if not stat.S_ISDIR(info.st_mode):
                _reject(
                    "run_root_collision_not_directory",
                    "temporary run-root collision not directory",
                )
            if not _path_safe_for_temporary(run_root.parent):
                _reject(
                    "run_root_collision_parent_unsafe",
                    "temporary run-root collision parent unsafe",
                )
            if run_root.parent.resolve() != (REPO_ROOT / ".pytest-temporary").resolve():
                _reject(
                    "run_root_collision_parent_boundary_changed",
                    "temporary run-root collision parent boundary changed",
                )
            state["fixture_status"] = "collision"
            return None
        except OSError:
            _reject(
                "run_root_collision_io",
                "temporary run-root collision I/O uncertain",
            )
    except OSError:
        _reject("run_root_create_io", "temporary run-root create failed")

    try:
        if run_root.is_symlink():
            _reject("run_root_is_symlink", "temporary run-root became symlink")
        is_run_root_junction = getattr(run_root, "is_junction", lambda: False)
        if bool(is_run_root_junction()):
            _reject("run_root_is_junction", "temporary run-root became junction")
        info = run_root.lstat()
        if not stat.S_ISDIR(info.st_mode):
            _reject(
                "run_root_not_directory",
                "temporary run-root became non-directory",
            )
        if not _path_safe_for_temporary(run_root.parent):
            _reject("run_root_parent_unsafe", "temporary run-root parent unsafe")
        if run_root.parent.resolve() != (REPO_ROOT / ".pytest-temporary").resolve():
            _reject(
                "run_root_parent_boundary_changed",
                "temporary run-root parent boundary changed",
            )
        state["run_root_identity"] = _temporary_root_identity(run_root)
        state["run_root"] = run_root
        state["run_root_verified"] = True
        state["fixture_status"] = "ready"
    except OSError:
        _reject("run_root_metadata_failure", "temporary run-root identity failed")
    return run_root


def pytest_configure(config):
    _temporary_lifecycle_state(config)
    config.addinivalue_line(
        "markers",
        "temporary: temporary test that belongs to a controlled artifact lifetime",
    )


def pytest_collection_modifyitems(session, config, items):
    state = _temporary_lifecycle_state(config)
    for item in items:
        if not _is_temporary_marker(item):
            continue

        try:
            path = _item_path(item)
            if not _is_temporary_path_allowed(REPO_ROOT, path):
                state["preserve"] = True
                raise pytest.UsageError(
                    f"temporary 測試只能位於 tests/_temporary/**/*.py：{path}"
                )
            if not _path_safe_for_temporary(path):
                state["preserve"] = True
                raise pytest.UsageError(f"temporary 測試路徑不安全：{path}")
            if _is_regression_backlog_marker(item):
                state["preserve"] = True
                raise pytest.UsageError(
                    f"temporary 測試不可同時標記 regression_backlog：{path}"
                )
            purpose = _temporary_test_purpose(path)
            if not purpose.strip():
                state["preserve"] = True
                raise pytest.UsageError(f"TEMPORARY_TEST_PURPOSE 未提供：{path}")
            state["temporary_files"].add(path)
        except pytest.UsageError:
            raise
        except (OSError, RuntimeError, SyntaxError, UnicodeError) as exc:
            state["preserve"] = True
            raise pytest.UsageError(
                f"temporary 測試 collection I/O 不確定：{getattr(item, 'path', '<unknown>')}"
            ) from exc


@pytest.hookimpl(hookwrapper=True)
def pytest_runtest_makereport(item, call):
    outcome = yield
    report = outcome.get_result()
    if _is_temporary_marker(item) and report.outcome in {"failed", "skipped"}:
        _temporary_lifecycle_state(item.config)["preserve"] = True


def pytest_sessionfinish(session, exitstatus):
    state = _temporary_lifecycle_state(session.config)
    if (
        exitstatus != 0
        or state.get("preserve")
        or state.get("fixture_status") != "ready"
        or not state.get("run_root_verified")
    ):
        return

    run_root = state.get("run_root")
    run_root_identity = state.get("run_root_identity")
    if not run_root_identity:
        state["preserve"] = True
        return
    if not _is_own_temporary_root(run_root):
        state["preserve"] = True
        return

    try:
        if run_root.is_symlink():
            state["preserve"] = True
            return
        is_run_root_junction = getattr(run_root, "is_junction", lambda: False)
        if bool(is_run_root_junction()):
            state["preserve"] = True
            return
        if not _path_safe_for_temporary(run_root.parent):
            state["preserve"] = True
            return
        if run_root.parent.resolve() != (REPO_ROOT / ".pytest-temporary").resolve():
            state["preserve"] = True
            return
        if _temporary_root_identity(run_root) != run_root_identity:
            state["preserve"] = True
            return
    except OSError:
        state["preserve"] = True
        return

    preflight_paths = []
    for path in sorted(state["temporary_files"]):
        try:
            if not _is_temporary_path_allowed(REPO_ROOT, path):
                state["preserve"] = True
                return
            if not _path_safe_for_temporary(path):
                state["preserve"] = True
                return
            mode = path.lstat().st_mode
        except FileNotFoundError:
            state["preserve"] = True
            return
        except OSError:
            state["preserve"] = True
            return
        if not stat.S_ISREG(mode):
            state["preserve"] = True
            return
        preflight_paths.append(path)

    for path in preflight_paths:
        try:
            path.unlink()
        except OSError:
            state["preserve"] = True
            return

    try:
        run_root.rmdir()
    except OSError:
        state["preserve"] = True
        return


def make_module(**overrides):
    base = {
        "type": "tool",
        "description": "測試專用 sample tool",
        "source": "sample_tool.py",
        "domain": None,
        "subsystem": None,
        "map_file": "system_map.md",
        "dependencies": [],
        "input": {"x": "int"},
        "output": {"y": "int"},
        "invariants": [],
        "preferred_pattern": "none",
        "verification": [],
        "observability": {"mode": "not_required", "signals": []},
        "decisions": [],
        "todo": [],
        "checkpoint": [],
        "complexity": "low",
        "algorithm": [],
        "state": "planned",
    }
    base.update(overrides)
    return base


@pytest.fixture
def base_modules():
    return {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "sample_tool": make_module(),
        },
        "domains": {},
    }
