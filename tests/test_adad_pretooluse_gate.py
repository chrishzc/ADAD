# -*- coding: utf-8 -*-
import json

from conftest import run_script, write_yaml


def _payload(project_dir, file_path, tool_name="Edit"):
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": {"file_path": file_path},
        "cwd": str(project_dir),
    })


def test_gate_ignores_non_edit_tools(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "sample_tool.py", tool_name="Bash"),
    )
    assert code == 0


def test_gate_ignores_untracked_file(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "not_a_registered_module.py"),
    )
    assert code == 0


def test_gate_blocks_direct_edit_of_compiled_yaml(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "system_map.yaml"),
    )
    assert code == 2
    assert "嚴禁直接編輯" in err


def test_gate_soft_warns_when_no_task_generated_yet(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "sample_tool.py"),
    )
    # 過渡期行為：還沒核發過 Task 只警告不阻擋
    assert code == 0
    assert "尚未核發過任何 Task" in err


def test_gate_allows_editing_when_task_assigned(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)
    run_script("generate_task.py", ["sample_tool"], cwd=project_dir)

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "sample_tool.py"),
    )
    assert code == 0


def test_gate_blocks_editing_when_task_submitted(project_dir, base_modules):
    src = project_dir / "sample_tool.py"
    src.write_text("def sample_tool(x):\n    return x\n", encoding="utf-8")
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    run_script("generate_task.py", ["sample_tool"], cwd=project_dir)
    run_script("adad_task.py", ["submit", "sample_tool"], cwd=project_dir)

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "sample_tool.py"),
    )
    assert code == 2
    assert "TASK GATE" in err
