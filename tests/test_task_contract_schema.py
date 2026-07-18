"""
File: test_task_contract_schema.py
Description: 測試 task_contract_schema.py 裡的所有驗證與升級邏輯。
"""

import pytest
from adad_cli.workflow.task_contract_schema import validate_semantic_contract, validate_non_goals, validate_verification_conditions, validate_assumptions, validate_task_input_schema, validate_task_output_schema

def test_validate_plain_text():
    # 測試普通的自然語言 description 能夠正確升級
    desc = "這是一個測試任務，需要將直譯器路徑正規化。"
    result = validate_semantic_contract(desc)
    assert result == {
        "summary": desc,
        "goals": [desc]
    }

def test_validate_structured_json():
    # 測試結構化的 JSON description 能夠正確解析與通過驗證
    desc = '{"summary": "直譯器正規化", "goals": ["確認 Windows scripts/python", "確認 Unix bin/python"]}'
    result = validate_semantic_contract(desc)
    assert result["summary"] == "直譯器正規化"
    assert result["goals"] == ["確認 Windows scripts/python", "確認 Unix bin/python"]

def test_validate_invalid_json():
    # 測試少 summary
    desc_missing_summary = '{"goals": ["test"]}'
    with pytest.raises(ValueError, match="Semantic Contract must contain a string 'summary'"):
        validate_semantic_contract(desc_missing_summary)

    # 測試少 goals
    desc_missing_goals = '{"summary": "test"}'
    with pytest.raises(ValueError, match="Semantic Contract must contain a non-empty list 'goals'"):
        validate_semantic_contract(desc_missing_goals)

    # 測試 goals 為空
    desc_empty_goals = '{"summary": "test", "goals": []}'
    with pytest.raises(ValueError, match="Semantic Contract must contain a non-empty list 'goals'"):
        validate_semantic_contract(desc_empty_goals)

    # 測試 goals 中包含非 string 元素
    desc_invalid_goals_items = '{"summary": "test", "goals": [123]}'
    with pytest.raises(ValueError, match="All items in 'goals' must be strings"):
        validate_semantic_contract(desc_invalid_goals_items)

def test_validate_empty_description():
    # 測試空描述會拋出例外
    with pytest.raises(ValueError, match="description cannot be empty"):
        validate_semantic_contract("")

def test_validate_non_goals_ok():
    # 測試合規 non_goals 列表
    non_goals = ["不要改動 cli.py", "不要新增外部依賴"]
    result = validate_non_goals(non_goals)
    assert result == non_goals

    # 測試空陣列（明確沒有 non_goals，應視為通過）
    assert validate_non_goals([]) == []

def test_validate_non_goals_invalid():
    # 測試傳入 None
    with pytest.raises(ValueError, match="non_goals contract must be explicitly provided"):
        validate_non_goals(None)

    # 測試型別錯誤（非 list）
    with pytest.raises(ValueError, match="non_goals must be a list"):
        validate_non_goals("not a list")

    # 測試清單內有非 string 元素
    with pytest.raises(ValueError, match="non_goals item at index 1 must be a string"):
        validate_non_goals(["ok", 123, "ok"])

def test_validate_verification_conditions_ok():
    # 測試合規的 verification cases (包含 expect 與 expect_exception)
    cases = [
        {"input": {"x": 1}, "expect": 2},
        {"input": {"x": -1}, "expect_exception": "ValueError"}
    ]
    result = validate_verification_conditions(cases)
    assert result == cases

    # 測試空清單，應視為通過
    assert validate_verification_conditions([]) == []

def test_validate_verification_conditions_invalid():
    # 測試傳入 None
    with pytest.raises(ValueError, match="verification_cases contract must be explicitly provided"):
        validate_verification_conditions(None)

    # 測試型別錯誤 (非 list)
    with pytest.raises(ValueError, match="verification_cases must be a list"):
        validate_verification_conditions("not a list")

    # 測試元素非 dict
    with pytest.raises(ValueError, match="verification_cases item at index 0 must be an object"):
        validate_verification_conditions(["not a dict"])

    # 測試缺少 input (Preconditions)
    with pytest.raises(ValueError, match="verification_cases item at index 0 must specify 'input'"):
        validate_verification_conditions([{"expect": 123}])

    # 測試缺少 expect 與 expect_exception (Postconditions)
    with pytest.raises(ValueError, match="verification_cases item at index 0 must specify either 'expect' or 'expect_exception'"):
        validate_verification_conditions([{"input": 123}])

    # 測試 expect_exception 型別非 string
    with pytest.raises(ValueError, match="expect_exception in verification_cases item at index 0 must be a string"):
        validate_verification_conditions([{"input": 123, "expect_exception": 123}])

    # 測試同時提供 expect 與 expect_exception
    with pytest.raises(ValueError, match="cannot specify both 'expect' and 'expect_exception'"):
        validate_verification_conditions([{"input": 123, "expect": 456, "expect_exception": "ValueError"}])

def test_validate_assumptions_ok():
    # 測試合規 assumptions 列表
    assumptions = ["OS 必須是 Windows", "必須預先安裝 git"]
    result = validate_assumptions(assumptions)
    assert result == assumptions

    # 測試空陣列（明確沒有 assumptions，應視為通過）
    assert validate_assumptions([]) == []

def test_validate_assumptions_invalid():
    # 測試傳入 None
    with pytest.raises(ValueError, match="assumptions contract must be explicitly provided"):
        validate_assumptions(None)

    # 測試型別錯誤（非 list）
    with pytest.raises(ValueError, match="assumptions must be a list"):
        validate_assumptions("not a list")

    # 測試清單內有非 string 元素
    with pytest.raises(ValueError, match="assumptions item at index 0 must be a string"):
        validate_assumptions([123, "git"])

def test_validate_task_input_schema_ok():
    # 測合規的簡單型別 schema
    s1 = {"type": "string"}
    assert validate_task_input_schema(s1) == s1

    # 測合規的 object schema (遞迴 properties、required、enum 等)
    s2 = {
        "type": "object",
        "properties": {
            "project_root": {"type": "string"},
            "env": {"type": "string", "enum": ["dev", "prod"]}
        },
        "required": ["project_root"]
    }
    assert validate_task_input_schema(s2) == s2

def test_validate_task_input_schema_invalid():
    # 測試 None
    with pytest.raises(ValueError, match="input_schema must be explicitly provided"):
        validate_task_input_schema(None)

    # 測試非 dict
    with pytest.raises(ValueError, match="input_schema must be a dict"):
        validate_task_input_schema("not a dict")

    # 測試不支援的進階關鍵字 (不屬於 validate_schema 支援子集)
    with pytest.raises(ValueError, match="Unsupported JSON Schema keyword 'patternProperties'"):
        validate_task_input_schema({"type": "object", "patternProperties": {}})

    # 測試 type 欄位非法
    with pytest.raises(ValueError, match="Invalid type 'invalid_type'"):
        validate_task_input_schema({"type": "invalid_type"})

    # 測試 properties 非 dict
    with pytest.raises(ValueError, match="properties must be a dict"):
        validate_task_input_schema({"type": "object", "properties": "not a dict"})

    # 測試 required 內有非 string
    with pytest.raises(ValueError, match="All items in 'required' must be strings"):
        validate_task_input_schema({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": [123]
        })

    # 測試 required 欄位提及 properties 內未定義之 key
    with pytest.raises(ValueError, match="Required property 'y' is not defined in 'properties'"):
        validate_task_input_schema({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["y"]
        })

def test_validate_task_output_schema_ok():
    s1 = {"type": "string"}
    assert validate_task_output_schema(s1) == s1

    s2 = {
        "type": "object",
        "properties": {
            "result": {"type": "string"}
        },
        "required": ["result"]
    }
    assert validate_task_output_schema(s2) == s2

def test_validate_task_output_schema_invalid():
    # 測試 None
    with pytest.raises(ValueError, match="output_schema must be explicitly provided"):
        validate_task_output_schema(None)

    # 測試非 dict
    with pytest.raises(ValueError, match="output_schema must be a dict"):
        validate_task_output_schema("not a dict")

    # 測試不支援的進階關鍵字
    with pytest.raises(ValueError, match="Unsupported JSON Schema keyword 'patternProperties'"):
        validate_task_output_schema({"type": "object", "patternProperties": {}})

    # 測試 type 欄位非法
    with pytest.raises(ValueError, match="Invalid type 'invalid_type' in output_schema"):
        validate_task_output_schema({"type": "invalid_type"})

    # 測試 properties 非 dict
    with pytest.raises(ValueError, match="properties must be a dict"):
        validate_task_output_schema({"type": "object", "properties": "not a dict"})

    # 測試 required 內有非 string
    with pytest.raises(ValueError, match="All items in 'required' must be strings"):
        validate_task_output_schema({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": [123]
        })

    # 測試 required 欄位提及 properties 內未定義之 key
    with pytest.raises(ValueError, match="Required property 'y' is not defined in 'properties'"):
        validate_task_output_schema({
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["y"]
        })


# Integration tests for Task 3: #19 Semantic Contract, Task 4: #20 Non-goals, and Task 5: #21 Verification
import importlib.util
from pathlib import Path
import sys

CANONICAL_CORE_PATH = Path(__file__).parents[1] / "adad_source" / "agents" / "skills" / "adad-workflow" / "scripts" / "adad_core.py"
sys.path.insert(0, str(CANONICAL_CORE_PATH.parent))
_spec = importlib.util.spec_from_file_location("canonical_adad_core_integration", CANONICAL_CORE_PATH)
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
CanonicalADADCore = _module.ADADCore

def test_semantic_contract_integration_readiness(tmp_path):
    # Test valid description
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "description": "this is a normal plain text description",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []}
            }
        }
    }

    # 1. Valid plain text
    import yaml
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)

    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is True

    # 2. Valid structured JSON description
    base_map["modules"]["test_node"]["description"] = '{"summary": "Summary text", "goals": ["Goal 1", "Goal 2"]}'
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)
    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is True

    # 3. Invalid description (goals contains non-string)
    base_map["modules"]["test_node"]["description"] = '{"summary": "Summary text", "goals": [123]}'
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)
    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is False
    assert any("Semantic Contract validation failed" in b for b in res["blockers"])


def test_semantic_contract_integration_generate(tmp_path):
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "state": "planned",
                "description": "this is a normal plain text description",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []}
            }
        }
    }
    # Create required directory structure inside tmp_path
    (tmp_path / ".agents" / "tasks" / ".source_locks").mkdir(parents=True, exist_ok=True)

    # 1. Valid description
    import yaml
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)

    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.generate_task("test_node", force=True)
    assert res["success"] is True
    task_path = Path(res["path"]).resolve()
    assert task_path.relative_to(tmp_path.resolve()) == Path(".agents/tasks/test_node.task.json")

    # 2. Invalid description (goals contains non-string)
    # Validate task snapshot directly to verify validate_task_snapshot integration
    task_data = {
        "schema_version": 3,
        "task_id": "test_node@v1@abcd",
        "node_name": "test_node",
        "exported_at": "2026-07-18T12:00:00Z",
        "system_map_version": 1,
        "source_hash": "hash123",
        "status": "assigned",
        "source_lock": {"source_path": "test_node.py", "node_name": "test_node", "task_id": "test_node@v1@abcd", "acquired_at": "now"},
        "rollback": None,
        "history": [],
        "spec": {
            "target_node": {
                "name": "test_node",
                "type": "tool",
                "state": "planned",
                "source": "test_node.py",
                "description": '{"summary": "Summary text", "goals": [123]}',
                "map_file": "system_map.yaml",
                "dependencies": [],
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "preferred_pattern": "none",
                "decisions": [],
                "idempotency": {"level": "unknown", "side_effects": []},
                "retry_budget": 0,
                "required_context": [],
                "forbidden_context": [],
                "context_priority": {}
            },
            "dependency_interfaces": {}
        }
    }
    validation_res = core.validate_task_snapshot(task_data, "test_node")
    assert validation_res["valid"] is False
    assert any("Semantic Contract validation failed" in err for err in validation_res["errors"])


def test_non_goals_integration_readiness(tmp_path):
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "description": "desc",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "non_goals": ["do not edit main.py"]
            }
        }
    }
    # 1. Valid non_goals list
    import yaml
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)
    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is True

    # 2. Invalid non_goals list (contains non-string)
    base_map["modules"]["test_node"]["non_goals"] = ["ok", 123]
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)
    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is False
    assert any("Non-goals validation failed" in b for b in res["blockers"])


def test_non_goals_integration_generate(tmp_path):
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "state": "planned",
                "description": "desc",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "non_goals": ["limit scope"]
            }
        }
    }
    # Create required directory structure inside tmp_path
    (tmp_path / ".agents" / "tasks" / ".source_locks").mkdir(parents=True, exist_ok=True)

    import yaml
    import json
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)

    core = CanonicalADADCore(map_file, check_validity=False)

    # 1. Generate task snapshot with valid non_goals
    res = core.generate_task("test_node", force=True)
    assert res["success"] is True

    # Load and verify snapshot has non_goals preserved with correct order and type
    with open(res["path"], "r", encoding="utf-8") as f:
        snapshot = json.load(f)
    assert snapshot["spec"]["target_node"]["non_goals"] == ["limit scope"]

    # 2. Schema version 3 requires non_goals. Verify validation fails if non_goals is None or missing
    task_data = {
        "schema_version": 3,
        "task_id": "test_node@v1@abcd",
        "node_name": "test_node",
        "exported_at": "2026-07-18T12:00:00Z",
        "system_map_version": 1,
        "source_hash": "hash123",
        "status": "assigned",
        "source_lock": {"source_path": "test_node.py", "node_name": "test_node", "task_id": "test_node@v1@abcd", "acquired_at": "now"},
        "rollback": None,
        "history": [],
        "spec": {
            "target_node": {
                "name": "test_node",
                "type": "tool",
                "state": "planned",
                "source": "test_node.py",
                "description": "desc",
                "map_file": "system_map.yaml",
                "dependencies": [],
                "input": {},
                "output": {},
                "verification": [],
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "preferred_pattern": "none",
                "decisions": [],
                "idempotency": {"level": "unknown", "side_effects": []},
                "retry_budget": 0,
                "required_context": [],
                "forbidden_context": [],
                "context_priority": {}
                # non_goals missing
            },
            "dependency_interfaces": {}
        }
    }
    validation_res = core.validate_task_snapshot(task_data, "test_node")
    assert validation_res["valid"] is False
    assert any("non_goals" in err for err in validation_res["errors"])


def test_verification_integration_readiness(tmp_path):
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "description": "desc",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "non_goals": [],
                "verification": [
                    {"case": {"input": {"x": 1}, "expect": 2, "expect_exception": "ValueError"}}
                ]
            }
        }
    }
    # Invalid: both expect and expect_exception are present
    import yaml
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)
    core = CanonicalADADCore(map_file, check_validity=False)
    res = core.check_task_readiness("test_node")
    assert res["ready"] is False
    assert any("Verification conditions validation failed" in b for b in res["blockers"])


def test_verification_integration_execute(tmp_path):
    base_map = {
        "version": 1,
        "environment": {"state": "not_required", "services": []},
        "modules": {
            "test_node": {
                "type": "tool",
                "state": "planned",
                "description": "desc",
                "source": "test_node.py",
                "domain": None,
                "subsystem": None,
                "input": {},
                "output": {},
                "invariants": [],
                "algorithm": [],
                "complexity": "low",
                "observability": {"mode": "not_required", "signals": []},
                "non_goals": [],
                "verification": [
                    {"case": {"input": {"x": 1}, "expect": 2}},
                    {"case": {"input": {"x": -1}, "expect_exception": "ValueError"}}
                ]
            }
        }
    }
    import yaml
    map_file = tmp_path / "system_map.yaml"
    with open(map_file, "w", encoding="utf-8") as f:
        yaml.dump(base_map, f)

    core = CanonicalADADCore(map_file, check_validity=False)

    # Write target implementation function test_node.py
    impl_file = tmp_path / "test_node.py"
    with open(impl_file, "w", encoding="utf-8") as f:
        f.write('''def test_node(x):
    if x < 0:
        raise ValueError("negative")
    return x + 1
''')

    # Run verification - should pass!
    res = core.verify_implementation("test_node", file_path=str(impl_file))
    assert res["success"] is True

    # Now make the implementation return wrong value - verification should fail!
    with open(impl_file, "w", encoding="utf-8") as f:
        f.write('''def test_node(x):
    return 999
''')
    res = core.verify_implementation("test_node", file_path=str(impl_file))
    assert res["success"] is False

    # Now make the implementation not raise ValueError - verification should fail!
    with open(impl_file, "w", encoding="utf-8") as f:
        f.write('''def test_node(x):
    return 2
''')
    res = core.verify_implementation("test_node", file_path=str(impl_file))
    assert res["success"] is False
