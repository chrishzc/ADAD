# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, make_module


def test_check_source_binding_passes_unique_sources(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "src/sample_tool.py"
    base_modules["modules"]["helper"] = make_module(
        description="另一個綁定不同檔案的模組", source="src/helper.py"
    )
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["passed"] is True
    assert data["violations"] == []
    assert data["unbound"] == []


def test_check_source_binding_flags_duplicate_exact_source(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "src/shared.py"
    base_modules["modules"]["helper"] = make_module(
        description="跟 sample_tool 撞到同一個 Source 的模組", source="src/shared.py"
    )
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 1
    assert data["passed"] is False
    types = {v["type"] for v in data["violations"]}
    assert "duplicate_source" in types


def test_check_source_binding_flags_whole_file_vs_function_conflict(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "src/shared.py"
    base_modules["modules"]["helper"] = make_module(
        description="逐函式登記同一支檔案的模組", source="src/shared.py::helper_fn"
    )
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 1
    assert data["passed"] is False
    types = {v["type"] for v in data["violations"]}
    assert "whole_file_vs_function_conflict" in types


def test_check_source_binding_flags_duplicate_function_binding(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "src/shared.py::do_work"
    base_modules["modules"]["helper"] = make_module(
        description="跟 sample_tool 搶同一個函式名稱的模組", source="src/shared.py::do_work"
    )
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 1
    assert data["passed"] is False
    types = {v["type"] for v in data["violations"]}
    assert "duplicate_function_binding" in types


def test_check_source_binding_allows_distinct_functions_same_file(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = "src/shared.py::do_work"
    base_modules["modules"]["helper"] = make_module(
        description="同一支檔案但綁定不同函式，應該允許", source="src/shared.py::do_other_work"
    )
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["passed"] is True
    assert data["violations"] == []


def test_check_source_binding_reports_unbound_modules_without_blocking(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = ""
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_source_binding.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["passed"] is True
    assert data["unbound"] == ["sample_tool"]
