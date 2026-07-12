# -*- coding: utf-8 -*-
from conftest import run_script, write_yaml

MD = """# ADAD Architecture Source

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

##### Module: deployed_tool
- Type: tool
- Description: 已上線的模組
- Source: deployed_tool.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: []
- Input: {}
- Output: {}
- TODO:
  - [ ] 還沒做完的待辦
- Checkpoint:
  - [ ] CP-2-099 (pending)

##### Module: planned_tool
- Type: tool
- Description: 還在規劃中的模組
- Source: planned_tool.py
- Preferred Pattern: none
- Decisions: []
- Invariants: []
- Verification: []
- Observability: not_required
- Dependencies: []
- Input: {}
- Output: {}
- TODO: []
- Checkpoint: []
"""


def test_resume_analysis_reports_module_states(project_dir):
    (project_dir / "system_map.md").write_text(MD, encoding="utf-8")
    code, data, out, err = run_script("compile_map.py", [], cwd=project_dir)
    assert code == 0, err

    from conftest import read_yaml
    compiled = read_yaml(project_dir)
    compiled["modules"]["deployed_tool"]["state"] = "deployed"
    write_yaml(project_dir, compiled)

    code, data, out, err = run_script("resume_analysis.py", [], cwd=project_dir)
    assert code == 0, err
    assert "deployed_tool" in out
    assert "planned_tool" in out
    assert "已完成部署 (Deployed)**: 1/2" in out
    assert "還沒做完的待辦" in out
    assert "CP-2-099" in out


def test_resume_analysis_missing_system_map_md(project_dir):
    code, data, out, err = run_script("resume_analysis.py", [], cwd=project_dir)
    assert code == 1
    assert "找不到架構源檔案" in out
