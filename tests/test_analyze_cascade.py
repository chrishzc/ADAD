# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml, make_module, read_yaml


def test_analyze_cascade_marks_upstream_dependents_dirty(project_dir, base_modules):
    # base -> sample_tool；改動 base_lib 應該讓 sample_tool 也被染成 dirty
    base_modules["modules"]["base_lib"] = make_module(
        description="被依賴的底層模組", state="deployed"
    )
    base_modules["modules"]["sample_tool"]["dependencies"] = ["base_lib"]
    base_modules["modules"]["sample_tool"]["state"] = "deployed"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("analyze_cascade.py", ["base_lib"], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert data["changed_node"] == "base_lib"
    assert set(data["dirty_nodes"]) == {"base_lib", "sample_tool"}

    # 副作用：state 真的被寫回 system_map.yaml，不是只印出來而已
    saved = read_yaml(project_dir)
    assert saved["modules"]["base_lib"]["state"] == "dirty"
    assert saved["modules"]["sample_tool"]["state"] == "dirty"


def test_analyze_cascade_unknown_node_errors(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("analyze_cascade.py", ["ghost_node"], cwd=project_dir)
    assert code == 1
    assert "error" in data
