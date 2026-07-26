#!/usr/bin/env python3
"""Run release gates against an immutable candidate tree."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Any


REPO_ENV_KEYS = {
    "GIT_DIR",
    "GIT_WORK_TREE",
    "GIT_INDEX_FILE",
    "GIT_COMMON_DIR",
    "GIT_OBJECT_DIRECTORY",
    "GIT_ALTERNATE_OBJECT_DIRECTORIES",
    "GIT_PREFIX",
    "GIT_IMPLICIT_WORK_TREE",
}


class PreflightError(RuntimeError):
    """Expected fail-closed release blocker."""


def _safe_env() -> dict[str, str]:
    env = os.environ.copy()
    for key in REPO_ENV_KEYS:
        env.pop(key, None)
    return env


def _run(
    argv: list[str],
    *,
    cwd: Path,
    timeout: int,
    env: dict[str, str] | None = None,
) -> dict[str, Any]:
    started = time.monotonic()
    try:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            env=env or _safe_env(),
            capture_output=True,
            text=True,
            check=False,
            shell=False,
            timeout=timeout,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "timed_out": False,
            "interrupted": False,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except subprocess.TimeoutExpired as exc:
        return {
            "returncode": None,
            "stdout": _text_tail(exc.stdout),
            "stderr": _text_tail(exc.stderr),
            "timed_out": True,
            "interrupted": False,
            "duration_seconds": round(time.monotonic() - started, 3),
        }
    except KeyboardInterrupt:
        return {
            "returncode": None,
            "stdout": "",
            "stderr": "",
            "timed_out": False,
            "interrupted": True,
            "duration_seconds": round(time.monotonic() - started, 3),
        }


def _text_tail(value: str | bytes | None) -> str:
    if value is None:
        return ""
    if isinstance(value, bytes):
        value = value.decode("utf-8", errors="replace")
    return value[-4000:]


def _strict_manifest(path: Path) -> tuple[dict[str, Any], str, str]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8", errors="strict"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise PreflightError(f"invalid manifest JSON: {exc}") from exc
    tree_hash = payload.get("candidate_tree_hash")
    release_manifest = payload.get("release_manifest")
    if (
        payload.get("manifest_valid") is not True
        or payload.get("blockers") != []
        or not isinstance(tree_hash, str)
        or not isinstance(release_manifest, dict)
    ):
        raise PreflightError("manifest is not a valid release candidate")
    version = release_manifest.get("version")
    if not isinstance(version, str) or not version:
        raise PreflightError("manifest version is missing")
    return payload, tree_hash, version


def _task_evidence(
    manifest: dict[str, Any], task_paths: list[Path]
) -> list[tuple[Path, str]]:
    expected = {
        item.get("task_id"): item.get("snapshot_sha256")
        for item in manifest["release_manifest"].get("task_authorization_evidence", [])
        if isinstance(item, dict)
    }
    validated: list[tuple[Path, str]] = []
    seen: set[str] = set()
    for path in task_paths:
        try:
            raw = path.read_bytes()
            task = json.loads(raw.decode("utf-8", errors="strict"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            raise PreflightError(f"invalid Task snapshot {path}: {exc}") from exc
        task_id = task.get("task_id")
        digest = hashlib.sha256(raw).hexdigest()
        if task.get("status") != "approved" or expected.get(task_id) != digest:
            raise PreflightError(f"Task snapshot evidence mismatch: {path}")
        validated.append((path, task_id))
        seen.add(task_id)
    if seen != set(expected):
        raise PreflightError("provided Task snapshots do not exactly match manifest evidence")
    return validated


def _git(project_root: Path, timeout: int, *args: str) -> dict[str, Any]:
    return _run(
        ["git", "-c", f"safe.directory={project_root}", "-C", str(project_root), *args],
        cwd=project_root,
        timeout=timeout,
    )


def _create_venv_link(link: Path, target: Path, timeout: int) -> None:
    if os.name == "nt":
        result = _run(
            ["cmd.exe", "/d", "/c", "mklink", "/J", str(link), str(target)],
            cwd=link.parent,
            timeout=timeout,
        )
        if result["returncode"] != 0:
            raise PreflightError(f"unable to create venv Junction: {result['stderr']}")
    else:
        os.symlink(target, link, target_is_directory=True)
    if not link.is_symlink() and not (os.lstat(link).st_file_attributes & 0x400 if os.name == "nt" else False):
        raise PreflightError("venv link identity could not be verified")


def _remove_venv_link(link: Path) -> None:
    if os.name == "nt":
        os.rmdir(link)
    else:
        link.unlink()


def _step(name: str, argv: list[str], cwd: Path, timeout: int, tree_hash: str) -> dict[str, Any]:
    result = _run(argv, cwd=cwd, timeout=timeout)
    return {
        "name": name,
        "argv": argv,
        "cwd": str(cwd),
        "timeout": timeout,
        "candidate_tree_hash": tree_hash,
        **result,
    }


def _artifact_evidence(dist: Path, version: str) -> list[dict[str, Any]]:
    files = sorted(path for path in dist.iterdir() if path.is_file())
    wheels = [path for path in files if path.suffix == ".whl" and version in path.name]
    sdists = [
        path
        for path in files
        if version in path.name and (path.name.endswith(".tar.gz") or path.suffix == ".zip")
    ]
    if not wheels or not sdists:
        raise PreflightError("build did not produce a versioned wheel and sdist")
    return [
        {
            "filename": path.name,
            "size": path.stat().st_size,
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        }
        for path in files
    ]


def run_preflight(
    *,
    manifest_path: Path,
    project_root: Path,
    project_python: Path,
    base_revision: str,
    task_snapshot_paths: list[Path],
    pytest_timeout: int,
    gate_timeout: int,
    build_timeout: int,
    outer_timeout: int,
) -> dict[str, Any]:
    manifest, tree_hash, version = _strict_manifest(manifest_path)
    tasks = _task_evidence(manifest, task_snapshot_paths)
    if outer_timeout < pytest_timeout + 2 * gate_timeout + build_timeout + 30:
        raise PreflightError("outer_timeout is smaller than the required timeout budget")
    if not project_python.is_file():
        raise PreflightError(f"project_python does not exist: {project_python}")
    tree_check = _git(project_root, gate_timeout, "cat-file", "-e", f"{tree_hash}^{{tree}}")
    if tree_check["returncode"] != 0:
        raise PreflightError("candidate tree identity cannot be revalidated")
    base_check = _git(project_root, gate_timeout, "rev-parse", "--verify", f"{base_revision}^{{commit}}")
    if base_check["returncode"] != 0:
        raise PreflightError("base_revision cannot be resolved to a commit")

    owned_root = Path(tempfile.mkdtemp(prefix="adad_release_"))
    worktree = owned_root / "worktree"
    dist = owned_root / "dist"
    basetemp = owned_root / "pytest-basetemp"
    step_results: list[dict[str, Any]] = []
    artifact_evidence: list[dict[str, Any]] = []
    deadline = time.monotonic() + outer_timeout

    script_dir = Path(__file__).resolve().parent
    if str(script_dir) not in sys.path:
        sys.path.insert(0, str(script_dir))
    from adad_core import ADADCore

    core = ADADCore(project_root / "system_map.yaml", check_validity=False)
    owned_identity = core._get_path_identity(str(owned_root))
    if not owned_identity:
        raise PreflightError("owned root identity is unavailable")

    def remaining() -> None:
        if time.monotonic() >= deadline:
            raise subprocess.TimeoutExpired(["release_preflight"], outer_timeout)

    try:
        add = _git(
            project_root,
            gate_timeout,
            "worktree",
            "add",
            "--detach",
            str(worktree),
            base_revision,
        )
        if add["returncode"] != 0:
            raise PreflightError(f"git worktree add failed: {add['stderr']}")
        read_tree = _git(
            worktree,
            gate_timeout,
            "read-tree",
            "--reset",
            "-u",
            tree_hash,
        )
        if read_tree["returncode"] != 0:
            raise PreflightError(f"git read-tree failed: {read_tree['stderr']}")

        task_dir = worktree / ".agents" / "tasks"
        task_dir.mkdir(parents=True, exist_ok=True)
        for source, task_id in tasks:
            shutil.copyfile(source, task_dir / f"{task_id.split('@', 1)[0]}.task.json")

        venv_root = project_python.parent.parent
        venv_link = worktree / ".venv"
        _create_venv_link(venv_link, venv_root, gate_timeout)

        commands = [
            ("whitespace", ["git", "-c", f"safe.directory={worktree}", "diff", "--cached", "--check"], gate_timeout),
            (
                "pytest",
                [
                    str(project_python),
                    "-m",
                    "pytest",
                    "-q",
                    "--color=no",
                    "--basetemp",
                    str(basetemp),
                    "-p",
                    "no:cacheprovider",
                ],
                pytest_timeout,
            ),
            (
                "adad_pre_commit",
                [
                    str(project_python),
                    ".agents/skills/adad-workflow/scripts/adad_pre_commit.py",
                ],
                gate_timeout,
            ),
            (
                "sync_assets",
                [str(project_python), "-m", "adad_cli.sync_assets", "--check"],
                gate_timeout,
            ),
            (
                "version",
                [
                    str(project_python),
                    "-c",
                    (
                        "import adad_cli,sys;"
                        f"sys.exit(0 if adad_cli.__version__ == {version!r} else 1)"
                    ),
                ],
                gate_timeout,
            ),
            (
                "build",
                [str(project_python), "-m", "build", "--outdir", str(dist)],
                build_timeout,
            ),
        ]
        for name, argv, timeout in commands:
            remaining()
            result = _step(name, argv, worktree, timeout, tree_hash)
            step_results.append(result)
            if result["timed_out"]:
                return _failure(
                    tree_hash,
                    step_results,
                    artifact_evidence,
                    owned_root,
                    "preserved_timeout",
                    {"stage": name, "message": "command timed out"},
                )
            if result["interrupted"]:
                return _failure(
                    tree_hash,
                    step_results,
                    artifact_evidence,
                    owned_root,
                    "preserved_termination_uncertain",
                    {"stage": name, "message": "command interrupted"},
                )
            if result["returncode"] != 0:
                return _failure(
                    tree_hash,
                    step_results,
                    artifact_evidence,
                    owned_root,
                    "preserved_command_failed",
                    {"stage": name, "message": "command returned nonzero"},
                )
        artifact_evidence = _artifact_evidence(dist, version)

        _remove_venv_link(venv_link)
        remove = _git(
            project_root,
            gate_timeout,
            "worktree",
            "remove",
            "--force",
            str(worktree),
        )
        if remove["returncode"] != 0:
            return _failure(
                tree_hash,
                step_results,
                artifact_evidence,
                owned_root,
                "preserved_cleanup_failed",
                {"stage": "git_worktree_remove", "message": remove["stderr"]},
            )
        cleanup_status, cleanup_error, _ = core._safe_cleanup_owned_root(
            str(owned_root), owned_identity
        )
        if cleanup_status != "cleaned":
            return _failure(
                tree_hash,
                step_results,
                artifact_evidence,
                owned_root,
                cleanup_status,
                cleanup_error,
            )
        return {
            "release_ready": True,
            "candidate_tree_hash": tree_hash,
            "step_results": step_results,
            "artifact_evidence": artifact_evidence,
            "cleanup_status": "cleaned",
            "cleanup_error": None,
            "preserved_paths": [],
            "manual_action_required": False,
        }
    except subprocess.TimeoutExpired:
        return _failure(
            tree_hash,
            step_results,
            artifact_evidence,
            owned_root,
            "preserved_timeout",
            {"stage": "outer_deadline", "message": "outer timeout expired"},
        )
    except (OSError, PreflightError) as exc:
        return _failure(
            tree_hash,
            step_results,
            artifact_evidence,
            owned_root,
            "preserved_preflight_rejected",
            {"stage": "preflight", "message": str(exc)},
        )


def _failure(
    tree_hash: str,
    steps: list[dict[str, Any]],
    artifacts: list[dict[str, Any]],
    owned_root: Path,
    status: str,
    error: Any,
) -> dict[str, Any]:
    return {
        "release_ready": False,
        "candidate_tree_hash": tree_hash,
        "step_results": steps,
        "artifact_evidence": artifacts,
        "cleanup_status": status,
        "cleanup_error": error,
        "preserved_paths": [str(owned_root)],
        "manual_action_required": True,
    }


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser()
    parser.add_argument("--manifest", required=True)
    parser.add_argument("--project-root", required=True)
    parser.add_argument("--project-python", required=True)
    parser.add_argument("--base-revision", required=True)
    parser.add_argument("--pytest-timeout", required=True, type=int)
    parser.add_argument("--gate-timeout", required=True, type=int)
    parser.add_argument("--build-timeout", required=True, type=int)
    parser.add_argument("--outer-timeout", required=True, type=int)
    parser.add_argument("--task-snapshot", action="append", default=[])
    return parser


def main(argv: list[str] | None = None) -> int:
    try:
        args = _parser().parse_args(argv)
        result = run_preflight(
            manifest_path=Path(args.manifest).resolve(),
            project_root=Path(args.project_root).resolve(),
            project_python=Path(args.project_python).resolve(),
            base_revision=args.base_revision,
            task_snapshot_paths=[Path(path).resolve() for path in args.task_snapshot],
            pytest_timeout=args.pytest_timeout,
            gate_timeout=args.gate_timeout,
            build_timeout=args.build_timeout,
            outer_timeout=args.outer_timeout,
        )
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0 if result["release_ready"] else 1
    except PreflightError as exc:
        result = {
            "release_ready": False,
            "candidate_tree_hash": None,
            "step_results": [],
            "artifact_evidence": [],
            "cleanup_status": "preserved_preflight_rejected",
            "cleanup_error": {"stage": "input", "message": str(exc)},
            "preserved_paths": [],
            "manual_action_required": True,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 1
    except BaseException as exc:
        result = {
            "release_ready": False,
            "candidate_tree_hash": None,
            "step_results": [],
            "artifact_evidence": [],
            "cleanup_status": "preserved_preflight_rejected",
            "cleanup_error": {
                "stage": "internal",
                "message": f"{type(exc).__name__}: {exc}",
            },
            "preserved_paths": [],
            "manual_action_required": True,
        }
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2


if __name__ == "__main__":
    sys.exit(main())
