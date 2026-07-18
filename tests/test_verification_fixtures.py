import os
import json
import pytest
from adad_cli.workflow.verification_fixtures import resolve_verification_fixture_inputs

def test_resolve_verification_fixture_inputs_no_fixtures():
    case = {
        "input": {"value": 1},
        "expect": 1
    }
    res = resolve_verification_fixture_inputs(case, ".")
    assert res == case
    assert res is not case  # Should be a copy

def test_resolve_verification_fixture_inputs_invalid_case_structure():
    with pytest.raises(ValueError, match="case must be a dict"):
        resolve_verification_fixture_inputs([], ".")

    with pytest.raises(ValueError, match="case\\['input'\\] must be a dict"):
        resolve_verification_fixture_inputs({"input": []}, ".")

def test_resolve_verification_fixture_inputs_explicit_null():
    case = {
        "input": {},
        "fixtures": None
    }
    with pytest.raises(ValueError, match="fixtures must not be null"):
        resolve_verification_fixture_inputs(case, ".")

def test_resolve_verification_fixture_inputs_absolute_path_posix():
    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "/outside.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="must not be an absolute path"):
        resolve_verification_fixture_inputs(case, ".")

def test_resolve_verification_fixture_inputs_absolute_path_windows():
    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "C:\\outside.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="must not be an absolute path"):
        resolve_verification_fixture_inputs(case, ".")

def test_resolve_verification_fixture_inputs_windows_drive_relative():
    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "C:outside.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="must not be a Windows drive or UNC path"):
        resolve_verification_fixture_inputs(case, ".")

def test_resolve_verification_fixture_inputs_unc_path():
    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "\\\\server\\share\\file.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="must not be (an absolute path|a Windows drive or UNC path)"):
        resolve_verification_fixture_inputs(case, ".")

    case2 = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "//server/share/file.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="must not be (an absolute path|a Windows drive or UNC path)"):
        resolve_verification_fixture_inputs(case2, ".")

def test_resolve_verification_fixture_inputs_path_traversal(tmp_path):
    # Setup project root and outside file
    project_root = tmp_path / "project"
    project_root.mkdir()
    outside_file = tmp_path / "outside.json"
    outside_file.write_text('{"a": 1}')

    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "../outside.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="is outside project root"):
        resolve_verification_fixture_inputs(case, str(project_root))

def test_resolve_verification_fixture_inputs_conflict():
    case = {
        "input": {
            "payload": {}
        },
        "fixtures": [
            {
                "input_key": "payload",
                "source": "tests/fixture.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="input_key conflict"):
        resolve_verification_fixture_inputs(case, ".")

def test_resolve_verification_fixture_inputs_success(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    fixture_file = project_root / "fixture.json"
    fixture_file.write_text('{"a": 42}', encoding="utf-8")

    case = {
        "input": {"x": 1},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "fixture.json"
            }
        ],
        "expect": 42
    }

    # Keep copy of original case to verify it does not change
    import copy
    original_case = copy.deepcopy(case)

    res = resolve_verification_fixture_inputs(case, str(project_root))

    # Verify original object is unmodified after successful injection
    assert case == original_case

    assert res["input"] == {"x": 1, "payload": {"a": 42}}
    assert res["expect"] == 42
    assert res["fixtures"] == case["fixtures"]

def test_resolve_verification_fixture_inputs_non_existent_file(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()

    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "non_existent.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="fixture source file not found"):
        resolve_verification_fixture_inputs(case, str(project_root))

def test_resolve_verification_fixture_inputs_duplicate_input_keys(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    fixture_file = project_root / "fixture.json"
    fixture_file.write_text('{"a": 42}', encoding="utf-8")

    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "fixture.json"
            },
            {
                "input_key": "payload",
                "source": "fixture.json"
            }
        ]
    }
    with pytest.raises(ValueError, match="duplicate input_key"):
        resolve_verification_fixture_inputs(case, str(project_root))

def test_resolve_verification_fixture_inputs_invalid_json(tmp_path):
    project_root = tmp_path / "project"
    project_root.mkdir()
    fixture_file = project_root / "invalid.json"
    fixture_file.write_text('{invalid json', encoding="utf-8")

    case = {
        "input": {},
        "fixtures": [
            {
                "input_key": "payload",
                "source": "invalid.json"
            }
        ]
    }
    # JSONDecodeError is a subclass of ValueError
    with pytest.raises(ValueError):
        resolve_verification_fixture_inputs(case, str(project_root))
