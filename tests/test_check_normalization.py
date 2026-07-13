# -*- coding: utf-8 -*-
import json

from conftest import run_script, write_yaml, make_module


def test_check_normalization_passes_when_no_overlap(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    proposal = json.dumps({
        "name": "totally_unrelated_tool",
        "input": {"z": "float"},
        "output": {"w": "float"},
        "description": "跟現有模組完全無關的全新功能",
    })
    code, data, out, err = run_script("check_normalization.py", cwd=project_dir, input_text=proposal)
    assert code == 0, err
    assert data["passed"] is True
    assert data["duplicates"] == []


def test_check_normalization_flags_identical_interface(project_dir, base_modules):
    # Rule 1: 介面簽章完全一致的模組要有 2 個以上才會觸發 Rule of Two
    base_modules["modules"]["another_tool"] = make_module(description="另一個功能")
    base_modules["modules"]["yet_another_tool"] = make_module(description="又一個功能")
    write_yaml(project_dir, base_modules)

    proposal = json.dumps({
        "name": "duplicate_tool",
        "input": {"x": "int"},
        "output": {"y": "int"},
        "description": "跟前面幾個介面完全一樣的新提案",
    })
    code, data, out, err = run_script("check_normalization.py", cwd=project_dir, input_text=proposal)
    assert code == 0, err
    assert data["passed"] is False
    assert len(data["duplicates"]) >= 2


def test_check_normalization_requires_name_field(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    proposal = json.dumps({"input": {}, "output": {}})
    code, data, out, err = run_script("check_normalization.py", cwd=project_dir, input_text=proposal)
    assert code == 1
    assert "error" in data


def test_check_normalization_rejects_invalid_json(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("check_normalization.py", cwd=project_dir, input_text="not-json")
    assert code == 1
    assert "error" in data


def test_check_normalization_rejects_non_object_json(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("check_normalization.py", cwd=project_dir, input_text="[1,2,3]")
    # 對應原始碼裡的 assert isinstance(data, dict)：非物件會觸發 AssertionError，
    # Python 對未捕捉例外預設 exit code 是 1。
    assert code == 1
