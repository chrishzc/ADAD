# -*- coding: utf-8 -*-
import json

from conftest import run_script, write_yaml


def test_generate_task_creates_snapshot(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert "task_id" in data

    task_path = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    assert task_path.exists()
    task_data = json.loads(task_path.read_text(encoding="utf-8"))
    assert task_data["node_name"] == "sample_tool"
    assert task_data["status"] == "assigned"
    assert task_data["spec"]["target_node"]["name"] == "sample_tool"


def test_generate_task_blocks_when_state_not_editable(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "deployed"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["error"].startswith("[BLOCKED]")


def test_generate_task_blocks_duplicate_without_force(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    code1, data1, _, err1 = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code1 == 0, err1

    code2, data2, _, err2 = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code2 == 1
    assert data2["error"].startswith("[BLOCKED]")

    code3, data3, _, err3 = run_script(
        "generate_task.py", ["sample_tool", "--force"], cwd=project_dir
    )
    assert code3 == 0, err3
    assert data3["success"] is True


def test_generate_task_unknown_node(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, data, out, err = run_script("generate_task.py", ["ghost_node"], cwd=project_dir)
    assert code == 1
    assert "error" in data
