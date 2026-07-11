# -*- coding: utf-8 -*-
import shutil

from conftest import run_script, read_yaml, REPO_ROOT

VALID_MD = """# ADAD Architecture Source

## Metadata
- Version: 1
- Status: planning

## Environment
- State: not_required
- Services: []

## Domains

### Domain: TestDomain
- Description: 測試用 Domain

#### Subsystem: TestSub
- Description: 測試用 Subsystem

##### Module: sample_tool
- Type: tool
- Description: 測試用範例模組
- Source: sample_tool.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - x: int
- Output:
  - y: int
- TODO: []
- Checkpoint: []
"""

MISSING_TYPE_MD = VALID_MD.replace("- Type: tool\n", "")

DUPLICATE_MODULE_MD = VALID_MD + """
##### Module: sample_tool
- Type: tool
- Description: 重複定義的同名模組
- Source: sample_tool2.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Dependencies: []
- Input:
  - x: int
- Output:
  - y: int
- TODO: []
- Checkpoint: []
"""


def _write_md(project_dir, content):
    (project_dir / "system_map.md").write_text(content, encoding="utf-8")
    shutil.copy(REPO_ROOT / "system_map.schema.json", project_dir / "system_map.schema.json")


def test_compile_map_produces_valid_yaml(project_dir):
    _write_md(project_dir, VALID_MD)
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 0, err
    assert data["success"] is True
    assert (project_dir / "system_map.yaml").exists()

    compiled = read_yaml(project_dir)
    assert "sample_tool" in compiled["modules"]
    assert compiled["modules"]["sample_tool"]["state"] == "planned"  # 全新模組預設 planned
    assert compiled["environment"] == {"state": "not_required", "services": []}


def test_compile_map_rejects_high_complexity_without_algorithm(project_dir):
    high_complexity = VALID_MD.replace(
        "- Preferred Pattern: none\n", "- Preferred Pattern: none\n- Complexity: high\n"
    )
    _write_md(project_dir, high_complexity)
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert "MISSING ALGORITHM" in data["error"]


def test_compile_map_preserves_state_when_structure_unchanged(project_dir):
    _write_md(project_dir, VALID_MD)
    run_script("compile_map.py", [], cwd=project_dir)

    # 手動把狀態推進到 deployed，模擬模組已經上線過
    compiled = read_yaml(project_dir)
    compiled["modules"]["sample_tool"]["state"] = "deployed"
    from conftest import write_yaml
    write_yaml(project_dir, compiled)

    # 重新編譯（Markdown 內容完全沒變，結構未動）
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 0, err
    recompiled = read_yaml(project_dir)
    assert recompiled["modules"]["sample_tool"]["state"] == "deployed"


def test_compile_map_resets_state_to_dirty_on_structural_change(project_dir):
    _write_md(project_dir, VALID_MD)
    run_script("compile_map.py", [], cwd=project_dir)

    compiled = read_yaml(project_dir)
    compiled["modules"]["sample_tool"]["state"] = "deployed"
    from conftest import write_yaml
    write_yaml(project_dir, compiled)

    # 改動 Input 介面（結構性變更），重新編譯後應該被標記 dirty
    changed_md = VALID_MD.replace("  - x: int", "  - x: int\n  - extra: str")
    _write_md(project_dir, changed_md)

    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 0, err
    recompiled = read_yaml(project_dir)
    assert recompiled["modules"]["sample_tool"]["state"] == "dirty"


def test_compile_map_fails_when_type_missing(project_dir):
    _write_md(project_dir, MISSING_TYPE_MD)
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert "Type" in data["error"]


def test_compile_map_fails_on_duplicate_module_name(project_dir):
    _write_md(project_dir, DUPLICATE_MODULE_MD)
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
    assert "重複" in data["error"]


def test_compile_map_missing_markdown_file(project_dir):
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 1
    assert data["success"] is False
