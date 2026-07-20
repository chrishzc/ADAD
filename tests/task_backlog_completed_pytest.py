import os
import pathlib
import subprocess
import sys
import pytest

pytestmark = pytest.mark.regression_backlog


_BACKLOG_TESTS = {
    "#1": "tests/test_generate_task.py::test_generate_task_creates_snapshot",
    "#2": "tests/test_task_contract_schema.py::test_validate_structured_json",
    "#3": "tests/test_compile_map.py::test_compile_map_produces_valid_yaml",
    "#4": "tests/test_adad_task.py::test_submit_succeeds_when_checks_pass",
    "#5": "tests/test_adad_pre_commit.py::test_allows_editing_planned_module",
    "#6": "tests/test_adad_pretooluse_gate.py::test_gate_allows_editing_when_task_assigned",
    "#7": "tests/test_adad_task.py::test_submit_succeeds_when_checks_pass",
    "#9": "tests/test_read_context.py::test_read_context_returns_target_node_fields",
    "#10": "tests/test_generate_task.py::test_task_schema_accepts_complete_v3_snapshot",
    "#11": "tests/test_check_invariants.py::test_check_invariants_flags_denied_import",
    "#12": "tests/test_verify_implementation.py::test_verify_implementation_case_pass_and_fail",
    "#13": "tests/test_check_domain_boundary.py::test_check_domain_boundary_allows_declared_cross_domain_dependency",
    "#14": "tests/test_transit_state.py::test_transit_state_allows_valid_transition",
    "#15": "tests/test_task_contract_schema.py::test_validate_structured_json",
    "#16": "tests/test_generate_task.py::test_generate_task_blocks_required_observability_without_signals",
    "#17": "tests/test_adad_task.py::test_approval_lock_mismatch_rolls_back_task_map_and_checkpoint",
    "#18": "tests/test_adad_task.py::test_source_lock_blocks_parallel_tasks_and_releases_after_approval",
    "#19": "tests/test_task_contract_schema.py::test_semantic_contract_integration_generate",
    "#20": "tests/test_task_contract_schema.py::test_non_goals_integration_generate",
    "#21": "tests/test_task_contract_schema.py::test_verification_integration_execute",
    "#22": "tests/test_task_contract_schema.py::test_validate_task_input_schema_ok",
    "#23": "tests/test_task_contract_schema.py::test_validate_task_output_schema_ok",
    "#24": "tests/test_check_invariants.py::test_check_invariants_passes_clean_file",
    "#26": "tests/test_task_contract_schema.py::test_validate_structured_json",
    "#31": "tests/test_task_contract_schema.py::test_validate_structured_json",
    "#32": "tests/test_verify_implementation.py::test_verify_implementation_case_pass_and_fail",
    "#35": "tests/test_generate_task.py::test_task_schema_accepts_complete_v3_snapshot",
    "#36": "tests/test_verify_implementation.py::test_verify_implementation_command_can_opt_into_project_cwd",
    "#40": "tests/test_generate_task.py::test_generate_task_enforces_complexity_budget",
    "#41": "tests/test_compile_map.py::test_compile_map_rejects_high_complexity_without_algorithm",
    "#42": "tests/test_adad_task.py::test_approve_rejected_without_human_tty",
    "#43": "tests/test_generate_task.py::test_task_schema_accepts_complete_v3_snapshot",
    "#44": "tests/test_generate_task.py::test_task_schema_v3_rejects_missing_fidelity_field",
    "#46": "tests/test_generate_task.py::test_task_schema_accepts_complete_v3_snapshot",
    "#48": "tests/test_upgrade_project.py::test_upgrade_replaces_root_schemas_and_keeps_backups",
    "#49": "tests/test_task_complexity.py",
    "#50": "tests/test_sync_assets.py::test_sync_twice_is_idempotent",
    "#51": "tests/test_blocked_task_reporting.py",
    "#52": "tests/test_prepare_isolation.py::test_prepare_isolation",
    "#53": "tests/test_adad_task.py::test_reject_rejected_without_human_tty",
    "#54": "tests/test_generate_task.py::test_task_schema_accepts_complete_v3_snapshot",
    "#57": "tests/test_compile_map.py::test_normalize_markdown_source_code_fences",
    "#58": "tests/test_verify_implementation.py::test_verify_implementation_command_timeout_decodes_bytes",
    "#81": "tests/test_pytest_regression_lifecycle.py::test_temporary_lifecycle_state_has_exact_fixed_fields",
}


@pytest.mark.parametrize("task_id, test_node_id", sorted(_BACKLOG_TESTS.items(), key=lambda item: int(item[0][1:])))
def test_backlog_completed_pytest_case_passes(task_id: str, test_node_id: str) -> None:
    # 1. 驗證對應的測試檔確實存在
    assert "::" in test_node_id, f"{task_id} must have a precise pytest node ID (with '::')"
    file_path, test_name = test_node_id.split("::", 1)
    assert pathlib.Path(file_path).exists(), f"{task_id}: {file_path} 不存在"

    # 2. 執行具體測試案例，並驗證其確實通過
    cmd = [sys.executable, "-m", "pytest", test_node_id, "-v", "--no-header"]
    env = dict(os.environ)
    env["PYTHONPATH"] = "."
    res = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", env=env)
    assert res.returncode == 0, f"Task {task_id} target test {test_node_id} failed!\nSTDOUT:\n{res.stdout}\nSTDERR:\n{res.stderr}"
