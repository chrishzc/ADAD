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
    assert any("Imported os" in v["detail"] for v in data["violations"])


def test_check_invariants_flags_denied_call(project_dir, base_modules):
    src = project_dir / "dangerous_tool.py"
    src.write_text("def sample_tool(x):\n    return eval(x)\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "dangerous_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_calls: [eval]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert any("Called eval" in v["detail"] for v in data["violations"])


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


def test_require_calls_passed(project_dir, base_modules):
    src = project_dir / "audit_tool.py"
    src.write_text("def sample_tool(x):\n    audit_log(x)\n    return x + 1\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "audit_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["require_calls: [audit_log]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 0
    assert data["success"] is True


def test_require_calls_failed(project_dir, base_modules):
    src = project_dir / "bad_audit_tool.py"
    src.write_text("def sample_tool(x):\n    return x + 1\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "bad_audit_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["require_calls: [audit_log]"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert any("require_calls" in v["rule"] for v in data["violations"])


def test_deny_env_read(project_dir, base_modules):
    src = project_dir / "env_tool.py"
    src.write_text("import os\ndef sample_tool(x):\n    a = os.environ['A']\n    b = os.getenv('B')\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "env_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_env_read"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert len(data["violations"]) == 2
    assert any("Access os.environ" in v["detail"] for v in data["violations"])
    assert any("Call os.getenv" in v["detail"] for v in data["violations"])


def test_deny_sys_exit(project_dir, base_modules):
    src = project_dir / "exit_tool.py"
    src.write_text("import sys\ndef sample_tool(x):\n    if x < 0:\n        raise SystemExit('error')\n    sys.exit(1)\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "exit_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_sys_exit"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert len(data["violations"]) == 2
    assert any("sys.exit" in v["detail"] for v in data["violations"])
    assert any("raise SystemExit" in v["detail"] for v in data["violations"])


def test_deny_bare_except(project_dir, base_modules):
    src = project_dir / "except_tool.py"
    src.write_text("def sample_tool(x):\n    try:\n        return x\n    except:\n        pass\n    try:\n        return x+1\n    except Exception:\n        ...\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "except_tool.py"
    base_modules["modules"]["sample_tool"]["invariants"] = ["deny_bare_except"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_invariants.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert len(data["violations"]) == 2
    assert all("deny_bare_except" in v["rule"] for v in data["violations"])
