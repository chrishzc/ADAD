# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, read_yaml


def test_transit_state_allows_valid_transition(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script(
        "transit_state.py", ["sample_tool", "validated"], cwd=project_dir
    )
    assert code == 0, err
    assert data["success"] is True
    assert data["from_state"] == "planned"
    assert data["to_state"] == "validated"

    saved = read_yaml(project_dir)
    assert saved["modules"]["sample_tool"]["state"] == "validated"


def test_transit_state_blocks_illegal_transition(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    # planned 只能轉到 validated，直接跳 deployed 應該被硬擋
    code, data, out, err = run_script(
        "transit_state.py", ["sample_tool", "deployed"], cwd=project_dir
    )
    assert code == 1
    assert data["error"].startswith("[BLOCKED]")

    # 被擋下的轉移不該有任何副作用
    saved = read_yaml(project_dir)
    assert saved["modules"]["sample_tool"]["state"] == "planned"


def test_transit_state_unknown_node(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script(
        "transit_state.py", ["ghost_node", "validated"], cwd=project_dir
    )
    assert code == 1
    assert "error" in data


def test_transit_state_missing_args(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("transit_state.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert "error" in data
