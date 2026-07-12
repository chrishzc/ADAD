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
    assert task_data["schema_version"] == 2
    assert task_data["rollback"]["strategy"] == "preserve_diff"
    assert task_data["node_name"] == "sample_tool"
    assert task_data["status"] == "assigned"
    assert task_data["spec"]["target_node"]["name"] == "sample_tool"


def test_generate_task_blocks_when_state_not_editable(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "deployed"
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["error"].startswith("[BLOCKED]")


def test_generate_task_blocks_incomplete_spec(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["source"] = ""
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["error"].startswith("[NOT READY]")
    assert any("source" in item for item in data["readiness_blockers"])


def test_generate_task_blocks_required_observability_without_signals(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["observability"] = {"mode": "required", "signals": []}
    write_yaml(project_dir, base_modules)

    code, data, out, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["error"].startswith("[NOT READY]")
    assert any("Observability" in item for item in data["readiness_blockers"])


def test_generate_task_enforces_complexity_budget(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["complexity"] = "medium"
    write_yaml(project_dir, base_modules)
    code, data, _, _ = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 1
    assert any("Complexity: medium" in item for item in data["readiness_blockers"])

    base_modules["modules"]["sample_tool"]["algorithm"] = ["validate input"]
    base_modules["modules"]["sample_tool"]["verification"] = [{"must_have_assertions": True}]
    write_yaml(project_dir, base_modules)
    code, data, _, err = run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    assert code == 0, err

    base_modules["modules"]["sample_tool"]["complexity"] = "high"
    write_yaml(project_dir, base_modules)
    code, data, _, _ = run_script("generate_task.py", ["sample_tool", "--force"], cwd=project_dir)
    assert code == 1
    assert any("Complexity: high" in item for item in data["readiness_blockers"])


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


def test_task_submit_rejects_malformed_snapshot(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    task_path = project_dir / ".agents" / "tasks" / "sample_tool.task.json"
    task_path.parent.mkdir(parents=True)
    task_path.write_text(json.dumps({"node_name": "sample_tool"}), encoding="utf-8")

    code, data, out, err = run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)
    assert code == 1
    assert data["error"].startswith("[INVALID TASK]")
