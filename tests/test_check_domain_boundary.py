# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, make_module


def test_check_domain_boundary_passes_same_domain(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["domain"] = "DomainA"
    base_modules["modules"]["helper"] = make_module(description="同 Domain 的輔助模組", domain="DomainA")
    base_modules["modules"]["sample_tool"]["dependencies"] = ["helper"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_domain_boundary.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["passed"] is True
    assert data["violations"] == []


def test_check_domain_boundary_flags_undeclared_cross_domain_dependency(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["domain"] = "DomainA"
    base_modules["modules"]["helper"] = make_module(description="另一個 Domain 的模組", domain="DomainB")
    base_modules["modules"]["sample_tool"]["dependencies"] = ["helper"]
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_domain_boundary.py", [], cwd=project_dir)
    assert code == 1
    assert data["passed"] is False
    assert data["violations"][0]["module"] == "sample_tool"
    assert data["violations"][0]["depends_on_domain"] == "DomainB"


def test_check_domain_boundary_allows_declared_cross_domain_dependency(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["domain"] = "DomainA"
    base_modules["modules"]["helper"] = make_module(description="被允許依賴的另一個 Domain 模組", domain="DomainB")
    base_modules["modules"]["sample_tool"]["dependencies"] = ["helper"]
    base_modules["domains"] = {
        "DomainA": {
            "description": "Domain A",
            "map_file": "system_map.md",
            "allowed_dependencies": ["DomainB"],
        }
    }
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("check_domain_boundary.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["passed"] is True
