import importlib.util
import json
from pathlib import Path
import subprocess


SOURCE = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "release_candidate_manifest.py"
)
SPEC = importlib.util.spec_from_file_location("release_candidate_manifest", SOURCE)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(MODULE)


def _git(repo: Path, *args: str) -> str:
    result = subprocess.run(
        ["git", "-C", str(repo), *args],
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Test")
    (repo / "adad_cli").mkdir()
    (repo / "src").mkdir()
    (repo / "replica").mkdir()
    (repo / "tests").mkdir()
    (repo / "adad_cli" / "__init__.py").write_text(
        '__version__ = "1.6.4"\n', encoding="utf-8"
    )
    (repo / "src" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "replica" / "tool.py").write_text("VALUE = 1\n", encoding="utf-8")
    (repo / "tests" / "test_tool.py").write_text(
        "def test_tool():\n    assert True\n", encoding="utf-8"
    )
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "initial")
    return repo


def _approved_task(tmp_path: Path) -> Path:
    path = tmp_path / "tool.task.json"
    path.write_text(
        json.dumps(
            {
                "task_id": "tool@v1@abcdef",
                "node_name": "tool",
                "status": "approved",
                "approved_implementation_hash": "abc123",
                "history": [
                    {
                        "event": "approved",
                        "checkpoint_id": "CP-2-test",
                        "checkpoint_path": "checkpoints/CP-2-test.yaml",
                    }
                ],
                "spec": {
                    "target_node": {
                        "input": {
                            "allowed_files": (
                                "[src/tool.py, replica/tool.py, tests/test_tool.py]"
                            )
                        }
                    }
                },
            }
        ),
        encoding="utf-8",
    )
    return path


def _build(repo: Path, task: Path, mode: str, revision: str | None):
    return MODULE.build_manifest(
        project_root=repo,
        candidate_mode=mode,
        candidate_revision=revision,
        version="1.6.4",
        approved_task_snapshots=[str(task)],
        expected_release_files=["src/tool.py", "replica/tool.py"],
        required_test_files=["tests/test_tool.py"],
        source_replica_groups=[["src/tool.py", "replica/tool.py"]],
    )


def test_commit_candidate_uses_tree_blobs_and_external_task_digest(tmp_path):
    repo = _repo(tmp_path)
    task = _approved_task(tmp_path)

    result = _build(repo, task, "commit", "HEAD")

    assert result["manifest_valid"] is True
    assert result["manual_action_required"] is False
    assert result["candidate_tree_hash"] == _git(repo, "rev-parse", "HEAD^{tree}")
    evidence = result["release_manifest"]["task_authorization_evidence"]
    assert evidence[0]["task_id"] == "tool@v1@abcdef"
    assert ".agents/tasks" not in result["release_manifest"]["files"]


def test_staged_source_with_required_test_only_dirty_is_rejected(tmp_path):
    repo = _repo(tmp_path)
    task = _approved_task(tmp_path)
    (repo / "src" / "tool.py").write_text("VALUE = 2\n", encoding="utf-8")
    (repo / "replica" / "tool.py").write_text("VALUE = 2\n", encoding="utf-8")
    _git(repo, "add", "src/tool.py", "replica/tool.py")
    (repo / "tests" / "test_tool.py").write_text(
        "def test_tool():\n    assert 2 == 2\n", encoding="utf-8"
    )

    result = _build(repo, task, "staged_index", None)

    assert result["manifest_valid"] is False
    assert {
        (blocker["code"], blocker.get("path"))
        for blocker in result["blockers"]
    } >= {("required_test_not_in_candidate", "tests/test_tool.py")}


def test_replica_mismatch_is_rejected_from_candidate_tree(tmp_path):
    repo = _repo(tmp_path)
    task = _approved_task(tmp_path)
    (repo / "replica" / "tool.py").write_text("VALUE = 3\n", encoding="utf-8")
    _git(repo, "add", "replica/tool.py")

    result = _build(repo, task, "staged_index", None)

    assert result["manifest_valid"] is False
    assert any(
        blocker["code"] == "replica_hash_mismatch"
        for blocker in result["blockers"]
    )


def test_unapproved_task_is_rejected(tmp_path):
    repo = _repo(tmp_path)
    task = _approved_task(tmp_path)
    payload = json.loads(task.read_text(encoding="utf-8"))
    payload["status"] = "assigned"
    task.write_text(json.dumps(payload), encoding="utf-8")

    try:
        _build(repo, task, "commit", "HEAD")
    except MODULE.ManifestError as exc:
        assert "not approved" in str(exc)
    else:
        raise AssertionError("unapproved Task snapshot must fail closed")
