# -*- coding: utf-8 -*-
import hashlib
import sqlite3
import importlib.util
import os
import subprocess
import sys

from conftest import SCRIPTS_DIR, run_script, write_yaml


def _load_adad_core():
    spec = importlib.util.spec_from_file_location("test_adad_core", SCRIPTS_DIR / "adad_core.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module.ADADCore


def test_verify_implementation_must_have_assertions_pass(project_dir, base_modules):
    src = project_dir / "asserted_tool.py"
    src.write_text(
        "def sample_tool(x):\n    assert isinstance(x, int)\n    return x + 1\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "asserted_tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = ["must_have_assertions"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "verify_implementation.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True


def test_verify_implementation_must_have_assertions_fail(project_dir, base_modules):
    src = project_dir / "no_assert_tool.py"
    src.write_text("def sample_tool(x):\n    return x + 1\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "no_assert_tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = ["must_have_assertions"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "verify_implementation.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False


def test_verify_implementation_case_pass_and_fail(project_dir, base_modules):
    src = project_dir / "case_tool.py"
    src.write_text("def sample_tool(x):\n    return x * 2\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "case_tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"case": {"input": {"x": 3}, "expect": 6}},
        {"case": {"input": {"x": 3}, "expect": 999}},
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "verify_implementation.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
    results = data["case_results"]
    assert results[0]["passed"] is True and results[0]["actual"] == 6
    assert results[1]["passed"] is False and results[1]["actual"] == 6


def test_verify_implementation_accepts_expected_exception(project_dir, base_modules):
    src = project_dir / "exception_tool.py"
    src.write_text(
        "def sample_tool(x):\n    if x < 0:\n        raise ValueError('x must be positive')\n    return x\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "exception_tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"case": {"input": {"x": -1}, "expect_exception": "ValueError"}},
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["case_results"][0]["actual_exception"] == "ValueError"


def test_verify_implementation_no_verification_defined_is_noop(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["verification"] = []
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "verify_implementation.py", ["sample_tool"], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True


def test_verify_implementation_command_accepts_expected_nonzero(project_dir, base_modules):
    src = project_dir / "migration_cli.py"
    src.write_text(
        "import sys\nif __name__ == '__main__':\n    raise SystemExit(3 if '--check' in sys.argv else 0)\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "migration_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{python}", "{source}", "--check"], "expect_exit": "nonzero"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert data["command_results"][0]["returncode"] == 3


def test_verify_implementation_command_can_opt_into_project_cwd(project_dir, base_modules):
    src = project_dir / "read_schema.py"
    src.write_text(
        "from pathlib import Path\nraise SystemExit(0 if Path('db/schema.sql').read_text(encoding='utf-8') == 'ok' else 1)\n",
        encoding="utf-8",
    )
    schema = project_dir / "db" / "schema.sql"
    schema.parent.mkdir()
    schema.write_text("ok", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "read_schema.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{project_python}", "{source}"], "cwd": "project"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["command_results"][0]["cwd"] == str(project_dir)


def test_pytest_command_uses_project_local_basetemp_when_omitted(project_dir, base_modules):
    src = project_dir / "tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    (project_dir / "test_probe.py").write_text(
        "def test_probe():\n    assert True\n", encoding="utf-8"
    )
    base_modules["modules"]["sample_tool"]["source"] = "tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{project_python}", "-m", "pytest", "test_probe.py", "-q"], "cwd": "project"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 0, err
    argv = data["command_results"][0]["argv"]
    index = argv.index("--basetemp")
    assert argv[index + 1].startswith(str(project_dir / ".agents" / "workspaces"))


def test_pytest_command_preserves_explicit_basetemp(project_dir, base_modules):
    src = project_dir / "tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    (project_dir / "test_probe.py").write_text(
        "def test_probe():\n    assert True\n", encoding="utf-8"
    )
    base_modules["modules"]["sample_tool"]["source"] = "tool.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{project_python}", "-m", "pytest", "test_probe.py", "-q", "--basetemp", "custom-pytest"], "cwd": "project"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 0, err
    argv = data["command_results"][0]["argv"]
    assert argv.count("--basetemp") == 1
    assert argv[argv.index("--basetemp") + 1] == "custom-pytest"


def test_verification_command_ignores_outer_git_index_and_preserves_other_env(
    project_dir, base_modules, tmp_path, monkeypatch
):
    outer = tmp_path / "outer"
    outer.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=outer, check=True)
    (outer / "outer.txt").write_text("outer", encoding="utf-8")
    subprocess.run(["git", "add", "outer.txt"], cwd=outer, check=True)
    outer_index = outer / ".git" / "index"
    index_hash_before = hashlib.sha256(outer_index.read_bytes()).hexdigest()
    files_before = subprocess.run(
        ["git", "ls-files"], cwd=outer, check=True, capture_output=True, text=True
    ).stdout

    subprocess.run(["git", "init", "-q"], cwd=project_dir, check=True)
    probe = project_dir / "git_env_probe.py"
    probe.write_text(
        """import os
import subprocess
import sys
from pathlib import Path

blocked = {
    'GIT_DIR', 'GIT_WORK_TREE', 'GIT_INDEX_FILE', 'GIT_COMMON_DIR',
    'GIT_OBJECT_DIRECTORY', 'GIT_ALTERNATE_OBJECT_DIRECTORIES',
    'GIT_PREFIX', 'GIT_IMPLICIT_WORK_TREE',
}
if blocked.intersection(os.environ):
    raise SystemExit(2)
if os.environ.get('ADAD_VERIFICATION_ENV_MARKER') != 'preserved':
    raise SystemExit(3)
root = subprocess.run(
    ['git', 'rev-parse', '--show-toplevel'], check=True,
    capture_output=True, text=True,
).stdout.strip()
if Path(root).resolve() != Path(sys.argv[1]).resolve():
    raise SystemExit(4)
Path('inner.txt').write_text('inner', encoding='utf-8')
subprocess.run(['git', 'add', 'inner.txt'], check=True)
""",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "git_env_probe.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {
            "command": {
                "argv": ["{project_python}", "{source}", "{project}"],
                "cwd": "project",
            }
        }
    ]
    write_yaml(project_dir, base_modules)

    monkeypatch.setenv("GIT_INDEX_FILE", str(outer_index))
    monkeypatch.setenv("GIT_PREFIX", "outer-prefix/")
    monkeypatch.setenv("ADAD_VERIFICATION_ENV_MARKER", "preserved")
    core = _load_adad_core()(project_dir / "system_map.yaml", check_validity=False)
    result = core.verify_implementation("sample_tool", str(probe))

    assert result["success"] is True, result
    assert hashlib.sha256(outer_index.read_bytes()).hexdigest() == index_hash_before
    clean_env = core._verification_subprocess_environment()
    files_after = subprocess.run(
        ["git", "ls-files"],
        cwd=outer,
        check=True,
        capture_output=True,
        text=True,
        env=clean_env,
    ).stdout
    assert files_after == files_before
    inner_files = subprocess.run(
        ["git", "ls-files"],
        cwd=project_dir,
        check=True,
        capture_output=True,
        text=True,
        env=clean_env,
    ).stdout.splitlines()
    assert inner_files == ["inner.txt"]


def test_verify_implementation_explicit_project_root_is_independent_of_map_path(
    project_dir, base_modules, tmp_path
):
    src = project_dir / "read_marker.py"
    src.write_text(
        "from pathlib import Path\nraise SystemExit(0 if Path('marker.txt').read_text() == 'ok' else 1)\n",
        encoding="utf-8",
    )
    (project_dir / "marker.txt").write_text("ok", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = str(src)
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{project_python}", "{source}"], "cwd": "project"}}
    ]
    staged_map_dir = tmp_path / "staged-map"
    staged_map_dir.mkdir()
    write_yaml(staged_map_dir, base_modules)

    core = _load_adad_core()(
        staged_map_dir / "system_map.yaml",
        check_validity=False,
        project_root=project_dir,
    )
    result = core.verify_implementation("sample_tool", str(src))

    assert result["success"] is True
    assert result["command_results"][0]["cwd"] == str(project_dir.resolve())


def test_verify_implementation_command_rejects_non_utf8_output(project_dir, base_modules):
    src = project_dir / "non_utf8_cli.py"
    src.write_text(
        "import sys\nsys.stdout.buffer.write(b'\\xb7 OUTPUT_OK')\nsys.stderr.buffer.write(b'\\xb7')\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "non_utf8_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{python}", "{source}"], "expect_stdout_contains": "OUTPUT_OK"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 1
    result = data["command_results"][0]
    assert data["success"] is False
    assert result["returncode"] == 0
    assert result["encoding_valid"] is False
    assert result["encoding_error"]
    assert "OUTPUT_OK" in result["stdout"]
    assert result["passed"] is False


def test_verify_implementation_command_reports_valid_utf8(project_dir, base_modules):
    src = project_dir / "utf8_cli.py"
    src.write_text("print('輸出正常')\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "utf8_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{python}", "{source}"], "expect_stdout_contains": "輸出正常"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 0, err
    result = data["command_results"][0]
    assert result["encoding_valid"] is True
    assert result["encoding_error"] is None


def test_verify_implementation_command_rejects_unsupported_output_encoding(project_dir, base_modules):
    src = project_dir / "encoded_cli.py"
    src.write_text("print('OUTPUT_OK')\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "encoded_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{python}", "{source}"], "output_encoding": "big5"}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 1
    result = data["command_results"][0]
    assert result["returncode"] == 0
    assert result["encoding_valid"] is False
    assert "unsupported output_encoding" in result["encoding_error"]


def test_verify_implementation_command_timeout_decodes_bytes(project_dir, base_modules):
    src = project_dir / "timeout_cli.py"
    src.write_text(
        "import sys, time\nsys.stdout.buffer.write(b'\\xff PARTIAL')\nsys.stdout.flush()\ntime.sleep(5)\n",
        encoding="utf-8",
    )
    base_modules["modules"]["sample_tool"]["source"] = "timeout_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {"command": {"argv": ["{python}", "{source}"], "timeout": 1}}
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)

    assert code == 1
    result = data["command_results"][0]
    assert result["returncode"] is None
    assert "PARTIAL" in result["stdout"]
    assert result["encoding_valid"] is False
    assert result["encoding_error"]


def test_verify_implementation_migration_integration_isolated_and_idempotent(
    project_dir, base_modules
):
    migration = project_dir / "migration_cli.py"
    migration.write_text(
        """import argparse
import sqlite3

parser = argparse.ArgumentParser()
action = parser.add_mutually_exclusive_group(required=True)
action.add_argument('--check', action='store_true')
action.add_argument('--apply', action='store_true')
parser.add_argument('--db', required=True)
args = parser.parse_args()
db = sqlite3.connect(args.db)
columns = [row[1] for row in db.execute('PRAGMA table_info(items)')]
if args.check:
    raise SystemExit(1 if 'other_addition' in columns else 0)
if 'other_addition' in columns:
    db.execute('ALTER TABLE items DROP COLUMN other_addition')
    db.commit()
""",
        encoding="utf-8",
    )
    checker = project_dir / "check_db.py"
    checker.write_text(
        """import sqlite3
import sys

db = sqlite3.connect(sys.argv[1])
columns = [row[1] for row in db.execute('PRAGMA table_info(items)')]
rows = db.execute('SELECT id, payload FROM items ORDER BY id').fetchall()
raise SystemExit(0 if 'other_addition' not in columns and rows == [(1, 'alpha'), (2, 'beta')] else 1)
""",
        encoding="utf-8",
    )
    fixture = project_dir / "fixture.sqlite3"
    with sqlite3.connect(fixture) as db:
        db.execute("CREATE TABLE items (id INTEGER PRIMARY KEY, payload TEXT, other_addition TEXT)")
        db.executemany(
            "INSERT INTO items VALUES (?, ?, ?)",
            [(1, "alpha", "remove-a"), (2, "beta", "remove-b")],
        )

    base_modules["modules"]["sample_tool"]["source"] = "migration_cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {
            "integration_case": {
                "name": "remove_other_addition",
                "fixtures": [{"source": "fixture.sqlite3", "target": "db/test.sqlite3"}],
                "steps": [
                    {"argv": ["{python}", "{source}", "--check", "--db", "{workspace}/db/test.sqlite3"], "expect_exit": "nonzero"},
                    {"argv": ["{python}", "{source}", "--apply", "--db", "{workspace}/db/test.sqlite3"]},
                    {"argv": ["{python}", "{project}/check_db.py", "{workspace}/db/test.sqlite3"]},
                    {"argv": ["{python}", "{source}", "--apply", "--db", "{workspace}/db/test.sqlite3"]},
                    {"argv": ["{python}", "{project}/check_db.py", "{workspace}/db/test.sqlite3"]},
                ],
            }
        }
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert len(data["integration_results"][0]["step_results"]) == 5
    with sqlite3.connect(fixture) as db:
        columns = [row[1] for row in db.execute("PRAGMA table_info(items)")]
    assert "other_addition" in columns


def test_verify_implementation_rejects_fixture_path_traversal(project_dir, base_modules):
    src = project_dir / "cli.py"
    src.write_text("raise SystemExit(0)\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["source"] = "cli.py"
    base_modules["modules"]["sample_tool"]["verification"] = [
        {
            "integration_case": {
                "fixtures": [{"source": "../secret.txt", "target": "secret.txt"}],
                "steps": [{"argv": ["{python}", "{source}"]}],
            }
        }
    ]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("verify_implementation.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert "目錄穿越" in data["integration_results"][0]["error"]
