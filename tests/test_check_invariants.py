# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml


def test_check_invariants_passes_clean_file(project_dir, base_modules):
    src = project_dir / "clean_tool.py"
    src.write_text("def sample_tool(x):\n    return x + 1\n", encoding="utf-8")

    base_modules["modules"]["sample_tool"]["source"] = "clean_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os, sys]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "check_invariants.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True


def test_check_invariants_flags_denied_import(project_dir, base_modules):
    src = project_dir / "dirty_tool.py"
    src.write_text("import os\n\ndef sample_tool(x):\n    return os.getpid()\n", encoding="utf-8")

    base_modules["modules"]["sample_tool"]["source"] = "dirty_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "check_invariants.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    assert any(v["imported"] == "os" for v in data["violations"])


def test_check_invariants_flags_denied_call(project_dir, base_modules):
    src = project_dir / "dangerous_tool.py"
    src.write_text("def sample_tool(x):\n    return eval(x)\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "dangerous_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_calls: [eval]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert any(v["called"] == "eval" for v in data["violations"])


def test_check_invariants_no_invariants_defined_is_noop(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["invariants"] = []
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "check_invariants.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True


def test_check_invariants_missing_source_file(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "does_not_exist.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_imports: [os]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "check_invariants.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
