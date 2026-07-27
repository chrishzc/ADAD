import importlib.util
from pathlib import Path
import pytest
import copy
from conftest import write_yaml, read_yaml

_SOURCE = (
    Path(__file__).resolve().parents[1]
    / "adad_source"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
    / "adad_release_advance.py"
)
_SPEC = importlib.util.spec_from_file_location("adad_release_advance", _SOURCE)
assert _SPEC is not None and _SPEC.loader is not None
_MODULE = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(_MODULE)

run_release_advance = _MODULE.run_release_advance
STRUCTURAL_KEYS = {"dependencies", "domain", "type", "algorithm", "invariants", "verification", "sub_maps", "owner"}


def test_release_advance_non_existent_node(project_dir, base_modules):
    write_yaml(project_dir, base_modules)
    res = run_release_advance("non_existent_node_xyz", repo_root=project_dir)
    assert res["success"] is False
    assert res["result"] == "error"


def test_release_advance_unvalidated_node(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "planned"
    write_yaml(project_dir, base_modules)

    res = run_release_advance("sample_tool", repo_root=project_dir)
    assert res["success"] is False
    assert res["result"] == "blocked"
    assert res["stuck_at"] == "planned"


def test_release_advance_missing_snapshot_requires_review(project_dir, base_modules):
    # 欠缺 approved_snapshot 時安全偏向 requires_review
    base_modules["modules"]["sample_tool"]["state"] = "validated"
    write_yaml(project_dir, base_modules)

    res = run_release_advance("sample_tool", repo_root=project_dir)
    assert res["success"] is False
    assert res["result"] == "requires_review"
    assert res["stuck_at"] == "validated"


def test_release_advance_with_snapshot_advances_to_deployed(project_dir, base_modules):
    # 有相同 approved_snapshot 且無架構變更時可順利推進至 deployed
    sample = base_modules["modules"]["sample_tool"]
    sample["state"] = "validated"
    sample["approved_snapshot"] = {k: copy.deepcopy(sample[k]) for k in STRUCTURAL_KEYS if k in sample}
    write_yaml(project_dir, base_modules)

    res = run_release_advance("sample_tool", repo_root=project_dir)
    assert res["success"] is True
    assert res["result"] == "advanced"
    assert res["to_state"] == "deployed"
    assert "evidence_hash" in res

    saved = read_yaml(project_dir)
    assert saved["modules"]["sample_tool"]["state"] == "deployed"
    assert len(saved["modules"]["sample_tool"]["audit_history"]) == 2


def test_release_advance_hash_guard_caching(project_dir, base_modules):
    sample = base_modules["modules"]["sample_tool"]
    sample["state"] = "validated"
    sample["approved_snapshot"] = {k: copy.deepcopy(sample[k]) for k in STRUCTURAL_KEYS if k in sample}
    write_yaml(project_dir, base_modules)

    # 首次推進至 deployed
    res1 = run_release_advance("sample_tool", repo_root=project_dir)
    assert res1["success"] is True

    # 手動將狀態改回 validated 模擬第二次重跑相同 Source 測試 Hash-Guard
    saved = read_yaml(project_dir)
    saved["modules"]["sample_tool"]["state"] = "validated"
    write_yaml(project_dir, saved)

    res2 = run_release_advance("sample_tool", repo_root=project_dir)
    assert res2["success"] is True
    saved2 = read_yaml(project_dir)
    audit = saved2["modules"]["sample_tool"]["audit_history"]
    assert audit[-2]["cached"] is True


def test_release_advance_already_deployed(project_dir, base_modules):
    base_modules["modules"]["sample_tool"]["state"] = "deployed"
    write_yaml(project_dir, base_modules)

    res = run_release_advance("sample_tool", repo_root=project_dir)
    assert res["success"] is True
    assert res["result"] == "no_action"
    assert res["current_state"] == "deployed"
