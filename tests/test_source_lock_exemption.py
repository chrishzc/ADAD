# -*- coding: utf-8 -*-
"""
tests/test_source_lock_exemption.py
#85 MVP — 風險分級豁免矩陣測試。

Case A: root README.md → Level 0 放行 (exit 0)
Case B: docs/specifications/* → Level 2 阻斷 (exit 2)
Case C: 未登記 .py 新檔 → Level 1 阻斷 (exit 2)
Case D: Rename src=README.md dst=AGENTS.md → dst Level 2 阻斷 (exit 2)
Case E: exit 2 stderr 結構包含 rule_id / level / path / next_action

ponytail: 只用 conftest 已有的 run_script / write_yaml / project_dir，不新增 fixture。
"""
import json
import pytest

from conftest import run_script, write_yaml


def _payload(project_dir, file_path, tool_name="Edit", destination=None):
    inp = {"file_path": file_path}
    if destination is not None:
        inp["destination"] = destination
    return json.dumps({
        "tool_name": tool_name,
        "tool_input": inp,
        "cwd": str(project_dir),
    })


# --- Case A: root README.md 放行 ---

def test_exempt_readme_at_root(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    readme = project_dir / "README.md"
    readme.write_text("# test\n", encoding="utf-8")
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(readme)),
    )
    assert code == 0, f"README.md 應放行 (exit 0)，got exit {code}\nstderr: {err}"


# --- Case B: docs/specifications/* 阻斷 (Level 2) ---

def test_blocks_governance_spec_doc(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    spec_dir = project_dir / "docs" / "specifications"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "05_task_backlog.md"
    spec_file.write_text("# backlog\n", encoding="utf-8")
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(spec_file)),
    )
    assert code == 2, f"docs/specifications/* 應阻斷 (exit 2)，got exit {code}\nstderr: {err}"


# --- Case C: 未登記 .py 新檔 阻斷 (Level 1) ---

def test_blocks_unregistered_py_file(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    new_py = project_dir / "src" / "brand_new_tool.py"
    new_py.parent.mkdir(parents=True, exist_ok=True)
    new_py.write_text("def foo(): pass\n", encoding="utf-8")
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(new_py)),
    )
    # 未登記 .py 不在 src_map，但 is_exempt_file 對 .py 一律回 False
    # → 進入後續 task gate 邏輯（soft_warn 或 exit 2）
    # 至少不能放行 (exit 0) 而完全略過
    assert code != 0 or "尚未核發" in err, (
        f"未登記 .py 不應靜默放行 exit 0 且無警告，got exit {code}\nstderr: {err}"
    )


# --- Case D: Rename destination 為 Level 2 治理檔 ---

def test_blocks_rename_to_governance_file(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    readme = project_dir / "README.md"
    readme.write_text("# hi\n", encoding="utf-8")
    agents_md = project_dir / "AGENTS.md"
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(
            project_dir,
            str(readme),
            tool_name="Rename",
            destination=str(agents_md),
        ),
    )
    assert code == 2, (
        f"Rename dst=AGENTS.md 應阻斷 (exit 2)，got exit {code}\nstderr: {err}"
    )


# --- Case E: exit 2 stderr 包含結構化診斷欄位 ---

def test_exit2_has_structured_diagnostic(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    spec_dir = project_dir / "docs" / "specifications"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "05_task_backlog.md"
    spec_file.write_text("# backlog\n", encoding="utf-8")
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(spec_file)),
    )
    assert code == 2
    assert "rule_id=" in err, f"stderr 缺少 rule_id=\nstderr: {err}"
    assert "level=" in err or "Level" in err, f"stderr 缺少 level 欄位\nstderr: {err}"
    assert "next_action" in err, f"stderr 缺少 next_action\nstderr: {err}"


# --- Case F: 異質 Tool Name 與 Key 解析 (P0) ---

def test_heterogeneous_tool_name_and_schema_support(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    spec_dir = project_dir / "docs" / "specifications"
    spec_dir.mkdir(parents=True, exist_ok=True)
    spec_file = spec_dir / "spec.md"
    spec_file.write_text("# spec\n", encoding="utf-8")

    # 傳入 replace_file_content 搭配 TargetFile 鍵名
    payload = json.dumps({
        "tool_name": "replace_file_content",
        "tool_input": {"TargetFile": str(spec_file)},
        "cwd": str(project_dir),
    })
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=payload,
    )
    assert code == 2, f"replace_file_content + TargetFile 應正確識別並阻斷，got {code}\nstderr: {err}"


# --- Case G: 無目標檔案 Key 阻斷 (P0) ---

def test_missing_target_file_schema_blocked(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    payload = json.dumps({
        "tool_name": "replace_file_content",
        "tool_input": {"InvalidKey": "foo.py"},
        "cwd": str(project_dir),
    })
    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=payload,
    )
    assert code == 2
    assert "L2-SCHEMA" in err, f"缺少目標檔案 key 應輸出 L2-SCHEMA 阻斷，stderr: {err}"


# --- Case H: YAML 壞檔/損毀 Fail-Closed (P0) ---

def test_corrupted_yaml_fail_closed(project_dir, base_modules):
    yaml_path = project_dir / "system_map.yaml"
    yaml_path.write_text("invalid_yaml: [unclosed_bracket", encoding="utf-8")

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, "some_file.py"),
    )
    assert code == 2
    assert "L2-CORRUPT" in err, f"YAML 損毀應觸發 L2-CORRUPT Fail-Closed 阻斷，stderr: {err}"


# --- Case I: 雙副檔名偽裝拒絕豁免 (P1) ---

def test_disguised_py_extension_blocked(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    fake_md = docs_dir / "config.py.md"
    fake_md.write_text("print('fake')\n", encoding="utf-8")

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(fake_md)),
    )
    # 不得直接放行 exit 0
    assert code != 0 or "尚未核發" in err, (
        f"docs/config.py.md 偽裝檔不應被 Level 0 無條件放行 exit 0，stderr: {err}"
    )


# --- Case J: 深度巢狀治理檔阻斷 (P2) ---

def test_deeply_nested_governance_blocked(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    deep_dir = project_dir / "docs" / "specifications" / "deep" / "nested" / "sub"
    deep_dir.mkdir(parents=True, exist_ok=True)
    deep_file = deep_dir / "spec.md"
    deep_file.write_text("# deep spec\n", encoding="utf-8")

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(deep_file)),
    )
    assert code == 2, f"深層治理檔應觸發 Level 2 阻斷 (exit 2)，got {code}\nstderr: {err}"


# --- Case K: Symlink 指向治理檔阻斷 (P1) ---

def test_symlink_governance_escape_blocked(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    docs_dir = project_dir / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    symlink_file = docs_dir / "link_to_map.md"
    target_file = project_dir / "system_map.yaml"

    try:
        symlink_file.symlink_to(target_file)
    except (OSError, NotImplementedError):
        pytest.skip("作業系統或權限不支援建立 symlink")

    code, _, out, err = run_script(
        "adad_pretooluse_gate.py",
        cwd=project_dir,
        input_text=_payload(project_dir, str(symlink_file)),
    )
    assert code == 2, f"指向治理檔之 Symlink 應遭判定並阻斷 (exit 2)，got {code}\nstderr: {err}"
