# -*- coding: utf-8 -*-
import sqlite3

from conftest import run_script, write_yaml


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
