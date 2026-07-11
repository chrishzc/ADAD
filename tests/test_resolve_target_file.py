# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml


def _base_domains():
    return {
        "version": 1,
        "modules": {},
        "domains": {
            "ExistingDomain": {
                "description": "已存在的 Domain",
                "map_file": "docs/domains/existing.md",
                "allowed_dependencies": [],
                "subsystems": {
                    "ExistingSub": {
                        "description": "已存在的 Subsystem",
                        "map_file": "docs/domains/existing_sub.md",
                    }
                },
            }
        },
    }


def test_resolve_target_file_unknown_domain(project_dir):
    write_yaml(project_dir, _base_domains())
    code, data, out, err = run_script(
        "resolve_target_file.py", ["BrandNewDomain"], cwd=project_dir
    )
    assert code == 0, err
    assert data["domain_exists"] is False
    assert data["target_file"] == "system_map.md"


def test_resolve_target_file_known_domain_no_subsystem(project_dir):
    write_yaml(project_dir, _base_domains())
    code, data, out, err = run_script(
        "resolve_target_file.py", ["ExistingDomain"], cwd=project_dir
    )
    assert code == 0, err
    assert data["domain_exists"] is True
    assert data["target_file"] == "docs/domains/existing.md"


def test_resolve_target_file_known_domain_and_subsystem(project_dir):
    write_yaml(project_dir, _base_domains())
    code, data, out, err = run_script(
        "resolve_target_file.py", ["ExistingDomain", "ExistingSub"], cwd=project_dir
    )
    assert code == 0, err
    assert data["domain_exists"] is True
    assert data["subsystem_exists"] is True
    assert data["target_file"] == "docs/domains/existing_sub.md"


def test_resolve_target_file_known_domain_unknown_subsystem(project_dir):
    write_yaml(project_dir, _base_domains())
    code, data, out, err = run_script(
        "resolve_target_file.py", ["ExistingDomain", "BrandNewSub"], cwd=project_dir
    )
    assert code == 0, err
    assert data["domain_exists"] is True
    assert data["subsystem_exists"] is False
    assert data["target_file"] == "docs/domains/existing.md"


def test_resolve_target_file_missing_args(project_dir):
    write_yaml(project_dir, _base_domains())
    code, data, out, err = run_script("resolve_target_file.py", [], cwd=project_dir)
    assert code == 1
    assert "error" in data
