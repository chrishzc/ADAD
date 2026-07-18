# -*- coding: utf-8 -*-
import json
import importlib.util
import sys
from pathlib import Path

from conftest import REPO_ROOT, run_script, write_yaml


TASK_SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "templates"
    / "task_schema.json"
)
VALIDATE_SCHEMA_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "validate_schema.py"
)
CANONICAL_CORE_PATH = (
    Path(__file__).parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_core.py"
)

sys.path.insert(0, str(CANONICAL_CORE_PATH.parent))
_core_spec = importlib.util.spec_from_file_location(
    "canonical_adad_core_generate_task", CANONICAL_CORE_PATH
)
_core_module = importlib.util.module_from_spec(_core_spec)
_core_spec.loader.exec_module(_core_module)
CanonicalADADCore = _core_module.ADADCore


def _load_minimal_validator():
    spec = importlib.util.spec_from_file_location("adad_validate_schema", VALIDATE_SCHEMA_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module._MinimalValidator


def _task_snapshot(schema_version):
    target_node = {
        "name": "sample_tool",
        "type": "tool",
        "state": "planned",
        "source": "sample_tool.py",
        "input": {"x": "int"},
        "output": {"y": "int"},
        "exceptions": [],
        "invariants": [],
        "verification": [],
        "observability": {"mode": "not_required", "signals": []},
    }
    if schema_version == 3:
        target_node.update(
            {
                "description": "測試用範例模組",
                "map_file": "system_map.md",
                "dependencies": [],
                "preferred_pattern": "none",
                "decisions": [],
                "complexity": "low",
                "algorithm": [],
                "idempotency": {},
                "retry_budget": 0,
                "required_context": [],
                "forbidden_context": [],
                "context_priority": {},
                "non_goals": [],
            }
        )
    return {
        "schema_version": schema_version,
        "task_id": "sample_tool@v1@test",
        "node_name": "sample_tool",
        "exported_at": "2026-07-14T00:00:00+00:00",
        "system_map_version": 1,
        "source_hash": "test-hash",
        "status": "assigned",
        "source_lock": {
            "source_path": "sample_tool.py",
            "node_name": "sample_tool",
            "task_id": "sample_tool@v1@test",
            "acquired_at": "2026-07-14T00:00:00+00:00",
        },
        "rollback": {
            "strategy": "preserve_diff",
            "source_path": "sample_tool.py",
            "baseline_file_hash": None,
            "instruction": "preserve diff",
        },
        "history": [],
        "spec": {"target_node": target_node, "dependency_interfaces": {}},
    }


def _task_schema_validator():
    schema = json.loads(TASK_SCHEMA_PATH.read_text(encoding="utf-8"))
    return _load_minimal_validator()(schema)


def test_task_schema_keeps_v2_compatible():
    assert list(_task_schema_validator().iter_errors(_task_snapshot(2))) == []


def test_task_schema_accepts_complete_v3_snapshot():
    assert list(_task_schema_validator().iter_errors(_task_snapshot(3))) == []


def test_task_schema_v3_rejects_missing_fidelity_field():
    required_v3_fields = (
        "description",
        "map_file",
        "dependencies",
        "preferred_pattern",
        "decisions",
        "complexity",
        "algorithm",
        "idempotency",
        "retry_budget",
        "required_context",
        "forbidden_context",
        "context_priority",
        "non_goals",
    )
    validator = _task_schema_validator()
    for field in required_v3_fields:
        snapshot = _task_snapshot(3)
        del snapshot["spec"]["target_node"][field]
        assert list(validator.iter_errors(snapshot)), field


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
    assert task_data["schema_version"] == 3
    assert task_data["rollback"]["strategy"] == "preserve_diff"
    assert task_data["node_name"] == "sample_tool"
    assert task_data["status"] == "assigned"
    assert task_data["spec"]["target_node"]["name"] == "sample_tool"


def test_generate_task_uses_instance_project_root(tmp_path, base_modules, monkeypatch):
    """Task artifacts belong to the ADADCore map instance, not the caller cwd."""
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(tmp_path, base_modules)
    monkeypatch.chdir(REPO_ROOT)

    result = CanonicalADADCore(
        tmp_path / "system_map.yaml", check_validity=False
    ).generate_task("sample_tool")

    expected_path = (tmp_path / ".agents" / "tasks" / "sample_tool.task.json").resolve()
    assert result["success"] is True
    assert Path(result["path"]).resolve() == expected_path
    assert expected_path.is_file()


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
