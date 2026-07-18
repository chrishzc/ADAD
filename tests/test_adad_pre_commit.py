# -*- coding: utf-8 -*-
import json
import hashlib
import importlib.util
import subprocess
from pathlib import Path

import pytest

from conftest import run_script, workflow_test_harness, write_yaml, make_module


def _load_pre_commit_module():
    source = (
        Path(__file__).parents[1]
        / "adad_source"
        / "agents"
        / "skills"
        / "adad-workflow"
        / "scripts"
        / "adad_pre_commit.py"
    )
    spec = importlib.util.spec_from_file_location("adad_pre_commit_under_test", source)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("ci", "base_ref", "expected_target"),
    [
        (None, None, ["--cached"]),
        ("true", None, ["HEAD~1", "HEAD"]),
        ("true", "", ["HEAD~1", "HEAD"]),
        ("true", "main", ["origin/main", "HEAD"]),
    ],
)
def test_get_staged_files_selects_expected_diff_target(
    monkeypatch, ci, base_ref, expected_target
):
    module = _load_pre_commit_module()
    if ci is None:
        monkeypatch.delenv("CI", raising=False)
    else:
        monkeypatch.setenv("CI", ci)
    if base_ref is None:
        monkeypatch.delenv("GITHUB_BASE_REF", raising=False)
    else:
        monkeypatch.setenv("GITHUB_BASE_REF", base_ref)

    calls = []

    def fake_run(argv, **kwargs):
        calls.append(argv)
        return subprocess.CompletedProcess(argv, 0, stdout="sample.py\n", stderr="")

    monkeypatch.setattr(module.subprocess, "run", fake_run)

    assert module.get_staged_files() == ["sample.py"]
    assert calls == [
        ["git", "diff", *expected_target, "--name-only", "--diff-filter=ACM"]
    ]


def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} 失敗: {result.stderr}"
    return result.stdout


def _write_task(git_repo, status, approved_hash=None):
    code, data, out, err = run_script(
        "generate_task.py", args=["sample_tool"], cwd=git_repo
    )
    assert code == 0, err or out
    task_path = git_repo / ".agents" / "tasks" / "sample_tool.task.json"
    task = json.loads(task_path.read_text(encoding="utf-8"))
    task["status"] = status
    if approved_hash is not None:
        task["implementation_hash"] = approved_hash
        task["approved_implementation_hash"] = approved_hash
    task_path.write_text(json.dumps(task, ensure_ascii=False, indent=2), encoding="utf-8")
    return task_path


@pytest.fixture
def git_repo(project_dir):
    _git(["init", "-q"], project_dir)
    _git(["config", "user.email", "test@example.com"], project_dir)
    _git(["config", "user.name", "ADAD Test"], project_dir)
    return project_dir


def test_no_staged_files_exits_clean(git_repo):
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 0


def test_workflow_test_harness_strips_outer_ci_event_context():
    child_environment = workflow_test_harness(
        {"CI": "true", "GITHUB_BASE_REF": "", "PATH": "bin"}
    )

    assert child_environment == {
        "PATH": "bin",
        "PYTHONIOENCODING": "utf-8",
    }


def test_workflow_test_harness_allows_explicit_ci_opt_in():
    child_environment = workflow_test_harness(
        {"CI": "true", "PATH": "bin"},
        {"CI": "true", "GITHUB_BASE_REF": "main"},
    )

    assert child_environment == {
        "CI": "true",
        "GITHUB_BASE_REF": "main",
        "PATH": "bin",
        "PYTHONIOENCODING": "utf-8",
    }


def test_run_script_ignores_outer_ci_context_in_fresh_repo(git_repo, monkeypatch):
    monkeypatch.setenv("CI", "true")
    monkeypatch.setenv("GITHUB_BASE_REF", "")

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 0, err or out


def test_blocks_editing_deployed_module_rule02(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "deployed"
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 1
    assert "RULE-02" in err


def test_allows_editing_planned_module(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text(
        "def sample_tool(x):\n    assert isinstance(x, int)\n    return x\n", encoding="utf-8"
    )

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 0, err


def test_blocks_denied_import_via_staged_content(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os]"]
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text(
        "import os\ndef sample_tool(x):\n    return os.getpid()\n", encoding="utf-8"
    )

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 1
    assert "INVARIANT" in err


def test_uses_staged_content_not_working_tree(git_repo, base_modules):
    """
    驗證『讀 git index 內容，不讀工作目錄』這個關鍵設計：
    staged 版本乾淨，之後又在工作目錄（未 add）動了手腳違反 invariants，
    pre-commit 檢查的應該還是 staged 版本，維持通過。
    """
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os]"]
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)

    # 工作目錄後來又被改壞，但沒有重新 git add
    (git_repo / "sample_tool.py").write_text(
        "import os\ndef sample_tool(x):\n    return os.getpid()\n", encoding="utf-8"
    )

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 0, err


def test_commit_gate_hashes_staged_bytes_not_working_tree(git_repo, base_modules):
    staged = b"def sample_tool(x):\n    return x\n"
    write_yaml(git_repo, base_modules)
    source = git_repo / "sample_tool.py"
    source.write_bytes(staged)
    approved_hash = hashlib.sha256(staged).hexdigest()
    _write_task(git_repo, "approved", approved_hash)
    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    source.write_text("def sample_tool(x):\n    return x + 1\n", encoding="utf-8")

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 0, err


def test_commit_gate_blocks_staged_hash_mismatch(git_repo, base_modules):
    write_yaml(git_repo, base_modules)
    source = git_repo / "sample_tool.py"
    source.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    _write_task(git_repo, "approved", hashlib.sha256(b"different").hexdigest())
    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 1
    assert "TASK GATE" in err
    assert "hash" in err.lower()


def test_commit_gate_blocks_assigned_task(git_repo, base_modules):
    write_yaml(git_repo, base_modules)
    source = git_repo / "sample_tool.py"
    source.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    _write_task(git_repo, "assigned")
    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 1
    assert "TASK GATE" in err
    assert "assigned" in err


def test_commit_gate_blocks_legacy_approved_task_without_hash(git_repo, base_modules):
    write_yaml(git_repo, base_modules)
    source = git_repo / "sample_tool.py"
    source.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    _write_task(git_repo, "approved")
    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 1
    assert "TASK GATE" in err
    assert "approved_implementation_hash" in err


def test_blocks_unregistered_function_rule04(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["source"] = "sample_tool.py::sample_tool"
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text(
        "def sample_tool(x):\n    return x\n\ndef sneaky_helper(y):\n    return y\n",
        encoding="utf-8",
    )

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 1
    assert "RULE-04" in err
    assert "sneaky_helper" in err


def test_blocks_dangling_dependency(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["dependencies"] = ["ghost_module"]
    write_yaml(git_repo, base_modules)
    _git(["add", "system_map.yaml"], git_repo)

    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 1
    assert "[SCHEMA]" in err
    assert "ghost_module" in err


def test_warns_on_multi_module_atomic_scope_rule03(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["second_tool"] = make_module(
        description="第二個模組", source="second_tool.py", state="planned"
    )
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    (git_repo / "second_tool.py").write_text("def second_tool(x):\n    return x\n", encoding="utf-8")

    _git(["add", "system_map.yaml", "sample_tool.py", "second_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    # RULE-03 只是 WARNING，不阻斷 commit
    assert code == 0, err
    assert "RULE-03" in err


def test_verification_uses_project_root_not_staged_map_temp_dir(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {
            "command": {
                "argv": [
                    "{project_python}",
                    "-c",
                    "from pathlib import Path; raise SystemExit(0 if Path('marker.txt').read_text() == 'ok' else 1)",
                ],
                "cwd": "project",
            }
        }
    ]
    write_yaml(git_repo, base_modules)
    (git_repo / "marker.txt").write_text("ok", encoding="utf-8")
    (git_repo / "sample_tool.py").write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 0, err


def test_verification_failure_reports_bounded_command_diagnostics(git_repo, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {
            "command": {
                "argv": [
                    "{project_python}",
                    "-c",
                    "import sys; print('x' * 2000); print('boom', file=sys.stderr); raise SystemExit(7)",
                ],
                "cwd": "project",
            }
        }
    ]
    write_yaml(git_repo, base_modules)
    (git_repo / "sample_tool.py").write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")

    _git(["add", "system_map.yaml", "sample_tool.py"], git_repo)
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)

    assert code == 1
    assert "VERIFICATION DIAGNOSTIC" in err
    diagnostic_line = next(
        line for line in err.splitlines() if "[VERIFICATION DIAGNOSTIC]" in line
    )
    diagnostic_payload = diagnostic_line.split("[VERIFICATION DIAGNOSTIC]", 1)[1]
    diagnostic = json.loads(diagnostic_payload[diagnostic_payload.index("{") :])
    assert Path(diagnostic["cwd"]).resolve() == git_repo.resolve()
    assert '\"returncode\":7' in err
    assert '\"encoding_valid\":true' in err
    assert '\"error\":\"command 結果不符合預期。\"' in err
    assert "boom" in err
    assert len(err) < 5000
