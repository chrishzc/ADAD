# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, make_module


def test_read_context_returns_target_node_fields(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("read_context.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["target_node"]["name"] == "sample_tool"
    assert data["target_node"]["input"] == {"x": "int"}
    assert data["target_node"]["output"] == {"y": "int"}
    assert data["dependency_interfaces"] == {}


def test_read_context_includes_dependency_interfaces(project_dir, base_modules):
    base_modules["modules"]["dep_tool"] = make_module(
        description="被依賴的模組",
        input={"a": "str"},
        output={"b": "str"},
        invariants=["deny_imports: [os]"],
    )
    base_modules["modules"]["sample_tool"]["dependencies"] = ["dep_tool"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("read_context.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert "dep_tool" in data["dependency_interfaces"]
    assert data["dependency_interfaces"]["dep_tool"]["input"] == {"a": "str"}
    assert data["dependency_interfaces"]["dep_tool"]["invariants"] == ["deny_imports: [os]"]


def test_read_context_unknown_node_returns_error(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("read_context.py", ["does_not_exist"], cwd=project_dir)
    assert code == 1
    assert "error" in data


def test_read_context_missing_node_name_arg(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("read_context.py", [], cwd=project_dir)
    assert code == 1
    assert "error" in data
