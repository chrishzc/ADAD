# -*- coding: utf-8 -*-
import subprocess

import pytest

from conftest import run_script, write_yaml, make_module


def _git(args, cwd):
    result = subprocess.run(["git"] + args, cwd=cwd, capture_output=True, text=True)
    assert result.returncode == 0, f"git {args} 失敗: {result.stderr}"
    return result.stdout


@pytest.fixture
def git_repo(project_dir):
    _git(["init", "-q"], project_dir)
    _git(["config", "user.email", "test@example.com"], project_dir)
    _git(["config", "user.name", "ADAD Test"], project_dir)
    return project_dir


def test_no_staged_files_exits_clean(git_repo):
    code, data, out, err = run_script("adad_pre_commit.py", cwd=git_repo)
    assert code == 0


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
