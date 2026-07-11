# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, REPO_ROOT

SCHEMA_PATH = str(REPO_ROOT / "system_map.schema.json")


def test_validate_schema_passes_conformant_yaml(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script(
        "validate_schema.py", ["system_map.yaml", SCHEMA_PATH], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True


def test_validate_schema_flags_missing_required_field(project_dir, base_modules):
    # 拿掉必要欄位 `source`
    del base_modules["modules"]["sample_tool"]["source"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "validate_schema.py", ["system_map.yaml", SCHEMA_PATH], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False


def test_validate_schema_flags_wrong_type(project_dir, base_modules):
    # version 必須是 integer，這裡故意塞字串
    base_modules["version"] = "not-a-number"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "validate_schema.py", ["system_map.yaml", SCHEMA_PATH], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False


def test_validate_schema_missing_yaml_file(project_dir):
    code, data, out, err = run_script(
        "validate_schema.py", ["does_not_exist.yaml", SCHEMA_PATH], cwd=project_dir
    )
    assert code == 1
    assert data["success"] is False
