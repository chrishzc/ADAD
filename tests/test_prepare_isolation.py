import os
import json
import shutil
import pytest
import subprocess
import sys

def test_prepare_isolation(tmp_path, monkeypatch):
    # Setup mock workspace
    orig_cwd = os.getcwd()
    monkeypatch.chdir(tmp_path)

    # Create fake tasks
    os.makedirs(".agents/tasks", exist_ok=True)
    task_data = {"status": "assigned"}
    with open(".agents/tasks/test_node.task.json", "w", encoding="utf-8") as f:
        json.dump(task_data, f)

    script_path = os.path.join(orig_cwd, "adad_source", "agents", "skills", "adad-workflow", "scripts", "prepare_isolation.py")

    # Test missing task
    res = subprocess.run([sys.executable, script_path, "missing_node"], capture_output=True, text=True)
    assert res.returncode == 1
    out = json.loads(res.stdout)
    assert not out["success"]
    assert "不存在" in out["error"]

    # Test unknown artifact type
    res2 = subprocess.run([sys.executable, script_path, "test_node", "unknown"], capture_output=True, text=True)
    assert res2.returncode == 1
    out2 = json.loads(res2.stdout)
    assert not out2["success"]
    assert "未知" in out2["error"]
