# -*- coding: utf-8 -*-
import json

from conftest import REPO_ROOT, run_script, write_yaml


SCHEMA_PATH = REPO_ROOT / "adad_source" / "templates" / "system_map.schema.json"


def _schema():
    return json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))


def _validate(project_dir, document):
    for module in document["modules"].values():
        module.setdefault("exceptions", [])
    write_yaml(project_dir, document)
    return run_script(
        "validate_schema.py", ["system_map.yaml", str(SCHEMA_PATH)], cwd=project_dir
    )


def test_schema_accepts_declared_sub_maps_and_module_ownership(project_dir, base_modules):
    document = base_modules
    document["sub_maps"] = {"finance": "maps/finance.yaml"}
    document["modules"]["sample_tool"]["sub_map"] = "finance"

    code, data, _, err = _validate(project_dir, document)

    assert code == 0, err
    assert data["success"] is True


def test_schema_rejects_sub_maps_array(project_dir, base_modules):
    document = base_modules
    document["sub_maps"] = ["maps/finance.yaml"]

    code, data, _, _ = _validate(project_dir, document)

    assert code == 1
    assert any(error["path"] == "sub_maps" for error in data["errors"])


def test_schema_rejects_empty_sub_map_contract_values():
    schema = _schema()
    sub_maps = schema["properties"]["sub_maps"]
    module_sub_map = schema["$defs"]["module"]["properties"]["sub_map"]

    assert sub_maps["minProperties"] == 1
    assert sub_maps["propertyNames"]["minLength"] == 1
    assert sub_maps["additionalProperties"]["minLength"] == 1
    assert module_sub_map["minLength"] == 1


def test_schema_keeps_existing_flat_ir_compatible(project_dir, base_modules):
    document = base_modules

    code, data, _, err = _validate(project_dir, document)

    assert code == 0, err
    assert data["success"] is True
    assert "sub_maps" not in document
    assert "sub_map" not in document["modules"]["sample_tool"]
