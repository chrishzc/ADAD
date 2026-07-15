# -*- coding: utf-8 -*-
import shutil

import yaml

from conftest import REPO_ROOT, make_module, run_script


def _module(name, sub_map=None):
    line = f"- Sub Map: {sub_map}\n" if sub_map is not None else ""
    return f"""##### Module: {name}
- Type: tool
- Description: {name} module
- Source: {name}.py
{line}- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: []
- Input:
  - x: int
- Output:
  - y: int
- TODO: []
- Checkpoint: []
"""


def _markdown(*modules):
    return """# ADAD Architecture Source

## Metadata
- Version: 3

## Environment
- State: not_required
- Services: []

### Domain: Test
- Description: Test

#### Subsystem: Core
- Description: Core

""" + "\n".join(modules)


def _write_yaml(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _setup(project_dir, markdown, root_modules=None, child_modules=None):
    (project_dir / "system_map.md").write_text(markdown, encoding="utf-8")
    shutil.copy(REPO_ROOT / "system_map.schema.json", project_dir / "system_map.schema.json")
    root = {
        "version": 2,
        "domains": {},
        "environment": {"state": "not_required", "services": []},
        "root_note": "preserve-root",
        "sub_maps": {"finance": "maps/finance.yaml"},
        "modules": root_modules or {},
    }
    child = {"child_note": "preserve-child", "modules": child_modules or {}}
    _write_yaml(project_dir / "system_map.yaml", root)
    _write_yaml(project_dir / "maps" / "finance.yaml", child)


def _read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_compile_preserves_owner_and_is_idempotent_without_root_inflation(project_dir):
    root_module = make_module(source="RootApi.py")
    child_module = make_module(source="FinanceImport.py", state="deployed")
    _setup(
        project_dir,
        _markdown(_module("RootApi"), _module("FinanceImport")),
        {"RootApi": root_module},
        {"FinanceImport": child_module},
    )

    first = run_script("compile_map.py", cwd=project_dir)
    second = run_script("compile_map.py", cwd=project_dir)

    assert first[0] == second[0] == 0, first[3] or second[3]
    root = _read(project_dir / "system_map.yaml")
    child = _read(project_dir / "maps" / "finance.yaml")
    assert set(root["modules"]) == {"RootApi"}
    assert set(child["modules"]) == {"FinanceImport"}
    assert child["modules"]["FinanceImport"]["state"] == "deployed"
    assert root["sub_maps"] == {"finance": "maps/finance.yaml"}
    assert root["root_note"] == "preserve-root"
    assert child["child_note"] == "preserve-child"
    assert first[1]["shard_module_counts"]["after"] == {"root": 1, "finance": 1}
    assert second[1]["shard_module_counts"] == {
        "before": {"root": 1, "finance": 1},
        "after": {"root": 1, "finance": 1},
    }


def test_compile_routes_new_modules_to_explicit_root_and_scope(project_dir):
    _setup(
        project_dir,
        _markdown(_module("RootNew", "root"), _module("FinanceNew", "finance")),
    )

    code, data, out, err = run_script("compile_map.py", cwd=project_dir)

    assert code == 0, err or out
    assert set(_read(project_dir / "system_map.yaml")["modules"]) == {"RootNew"}
    assert set(_read(project_dir / "maps" / "finance.yaml")["modules"]) == {"FinanceNew"}
    assert data["shard_module_counts"]["after"] == {"root": 1, "finance": 1}


def test_compile_rejects_unknown_or_unowned_new_module_without_writes(project_dir):
    for sub_map, expected in (("unknown", "不存在"), (None, "必須明確指定")):
        _setup(project_dir, _markdown(_module("NewModule", sub_map)))
        root_before = (project_dir / "system_map.yaml").read_bytes()
        child_before = (project_dir / "maps" / "finance.yaml").read_bytes()

        code, data, out, err = run_script("compile_map.py", cwd=project_dir)

        assert code == 1
        assert expected in data["error"]
        assert (project_dir / "system_map.yaml").read_bytes() == root_before
        assert (project_dir / "maps" / "finance.yaml").read_bytes() == child_before
