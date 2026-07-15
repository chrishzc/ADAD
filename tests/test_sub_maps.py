# -*- coding: utf-8 -*-
import importlib.util
import os
import sys
from pathlib import Path

import pytest
import yaml

from conftest import SCRIPTS_DIR, make_module


def _core_class():
    spec = importlib.util.spec_from_file_location("test_sub_maps_core", SCRIPTS_DIR / "adad_core.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module.ADADCore


def _parse_markdown(markdown):
    spec = importlib.util.spec_from_file_location("test_sub_maps_parser", SCRIPTS_DIR / "adad_core.py")
    module = importlib.util.module_from_spec(spec)
    sys.path.insert(0, str(SCRIPTS_DIR))
    try:
        spec.loader.exec_module(module)
    finally:
        sys.path.pop(0)
    return module.parse_markdown(markdown)


def _write(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(yaml.safe_dump(data, allow_unicode=True, sort_keys=False), encoding="utf-8")


def _read(path):
    return yaml.safe_load(path.read_text(encoding="utf-8"))


def test_recursive_sub_maps_merge_modules_and_track_owner(tmp_path):
    root = tmp_path / "system_map.yaml"
    finance = tmp_path / "maps" / "finance.yaml"
    imports = tmp_path / "maps" / "imports.yaml"
    _write(root, {"version": 7, "modules": {"root_api": make_module()}, "sub_maps": {"finance": "maps/finance.yaml"}})
    _write(finance, {"owner_note": "preserve", "modules": {"finance_service": make_module()}, "sub_maps": {"imports": "maps/imports.yaml"}})
    _write(imports, {"modules": {"FinanceImport": make_module()}})

    core = _core_class()(root, check_validity=False, project_root=tmp_path)

    assert set(core.data["modules"]) == {"root_api", "finance_service", "FinanceImport"}
    assert core.module_owners == {
        "root_api": "root",
        "finance_service": "finance",
        "FinanceImport": "imports",
    }
    assert core.shard_documents["finance"]["owner_note"] == "preserve"


def test_owner_aware_save_preserves_shards_and_rejects_unknown_owner(tmp_path):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "maps" / "finance.yaml"
    _write(root, {"version": 2, "root_note": "root", "modules": {"root_api": make_module()}, "sub_maps": {"finance": "maps/finance.yaml"}})
    _write(child, {"child_note": "child", "modules": {"FinanceImport": make_module()}})
    core = _core_class()(root, check_validity=False, project_root=tmp_path)
    core.data["modules"]["FinanceImport"]["state"] = "dirty"
    core.save()

    root_doc = _read(root)
    child_doc = _read(child)
    assert set(root_doc["modules"]) == {"root_api"}
    assert set(child_doc["modules"]) == {"FinanceImport"}
    assert child_doc["modules"]["FinanceImport"]["state"] == "dirty"
    assert root_doc["sub_maps"] == {"finance": "maps/finance.yaml"}
    assert root_doc["root_note"] == "root"
    assert child_doc["child_note"] == "child"

    before_root = root.read_bytes()
    before_child = child.read_bytes()
    core.data["modules"]["unowned"] = make_module()
    with pytest.raises(ValueError, match="缺少 shard owner: unowned"):
        core.save()
    assert root.read_bytes() == before_root
    assert child.read_bytes() == before_child


@pytest.mark.parametrize(
    "sub_maps, error",
    [
        ({"finance": "missing.yaml"}, "找不到 sub_maps 檔案"),
        ({"finance": "../outside.yaml"}, "超出 project root"),
        ({"finance": "C:/outside.yaml"}, "禁止絕對路徑"),
    ],
)
def test_sub_maps_reject_missing_or_unsafe_paths(tmp_path, sub_maps, error):
    root = tmp_path / "system_map.yaml"
    _write(root, {"modules": {}, "sub_maps": sub_maps})
    with pytest.raises((ValueError, FileNotFoundError), match=error):
        _core_class()(root, check_validity=False, project_root=tmp_path)


def test_sub_maps_reject_cycle_and_duplicate_module(tmp_path):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "child.yaml"
    _write(root, {"modules": {"same": make_module()}, "sub_maps": {"child": "child.yaml"}})
    _write(child, {"modules": {"same": make_module()}, "sub_maps": {"again": "system_map.yaml"}})
    with pytest.raises(ValueError, match="模組名稱跨 shard 重複|sub_maps cycle"):
        _core_class()(root, check_validity=False, project_root=tmp_path)

    _write(child, {"modules": {"child_only": make_module()}, "sub_maps": {"again": "system_map.yaml"}})
    with pytest.raises(ValueError, match="sub_maps cycle"):
        _core_class()(root, check_validity=False, project_root=tmp_path)


def test_child_yaml_newer_than_root_invalidates_ir(tmp_path):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "child.yaml"
    md = tmp_path / "system_map.md"
    md.write_text("# map\n", encoding="utf-8")
    _write(root, {"modules": {}, "sub_maps": {"child": "child.yaml"}})
    _write(child, {"modules": {"FinanceImport": make_module()}})
    root_time = root.stat().st_mtime
    os.utime(child, (root_time + 5, root_time + 5))

    core = _core_class()(root, check_validity=False, project_root=tmp_path)
    validity = core.check_ir_validity()

    assert validity["valid"] is False
    assert "子架構 IR" in validity["error"]


def test_child_yaml_validity_does_not_depend_on_markdown_presence(tmp_path):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "child.yaml"
    _write(root, {"modules": {}, "sub_maps": {"child": "child.yaml"}})
    _write(child, {"modules": {"FinanceImport": make_module()}})
    root_time = root.stat().st_mtime
    os.utime(child, (root_time + 5, root_time + 5))

    core = _core_class()(root, check_validity=False, project_root=tmp_path)

    assert core.check_ir_validity()["valid"] is False


def test_parse_markdown_trims_sub_map_without_validating_scope():
    parsed = _parse_markdown(
        """# System Map
- Version: 1
### Domain: Finance
##### Module: FinanceImport
- Type: service
- Source: finance_import.py
- Sub Map:   future-finance-scope""" + "   \n"
    )

    assert parsed["modules"]["FinanceImport"]["sub_map"] == "future-finance-scope"


def test_parse_markdown_rejects_empty_sub_map():
    with pytest.raises(ValueError, match="Sub Map 不得為空"):
        _parse_markdown(
            """# System Map
- Version: 1
### Domain: Finance
##### Module: FinanceImport
- Type: service
- Source: finance_import.py
- Sub Map:
"""
        )


def test_loader_rejects_ghost_sub_map_scope(tmp_path):
    root = tmp_path / "system_map.yaml"
    ghost = make_module()
    ghost["sub_map"] = "ghost"
    _write(root, {"modules": {"GhostService": ghost}})

    with pytest.raises(ValueError, match="GhostService.*ghost.*root.*不一致"):
        _core_class()(root, check_validity=False, project_root=tmp_path)


@pytest.mark.parametrize(
    "root_owner, child_owner, expected_module, expected_physical_owner",
    [
        ("finance", "finance", "RootService", "root"),
        ("root", "root", "FinanceImport", "finance"),
    ],
)
def test_loader_rejects_root_or_child_owner_mismatch(
    tmp_path, root_owner, child_owner, expected_module, expected_physical_owner
):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "finance.yaml"
    root_module = make_module()
    root_module["sub_map"] = root_owner
    child_module = make_module()
    child_module["sub_map"] = child_owner
    _write(
        root,
        {
            "modules": {"RootService": root_module},
            "sub_maps": {"finance": "finance.yaml"},
        },
    )
    _write(child, {"modules": {"FinanceImport": child_module}})

    with pytest.raises(
        ValueError,
        match=rf"{expected_module}.*{expected_physical_owner}.*不一致",
    ):
        _core_class()(root, check_validity=False, project_root=tmp_path)


def test_loader_keeps_legacy_modules_without_sub_map_compatible(tmp_path):
    root = tmp_path / "system_map.yaml"
    child = tmp_path / "finance.yaml"
    _write(
        root,
        {
            "modules": {"RootService": make_module()},
            "sub_maps": {"finance": "finance.yaml"},
        },
    )
    _write(child, {"modules": {"FinanceImport": make_module()}})

    core = _core_class()(root, check_validity=False, project_root=tmp_path)

    assert set(core.data["modules"]) == {"RootService", "FinanceImport"}
    assert core.module_owners == {"RootService": "root", "FinanceImport": "finance"}
