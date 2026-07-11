# -*- coding: utf-8 -*-
"""
tests/conftest.py — 全套測試共用的 fixtures 與輔助函式。

設計原則（跟本專案「機械強制優於自律」一致）：
  - 每支腳本都是獨立的 CLI 工具（見 scripts/*.py），所以測試策略採黑箱方式：
    用 subprocess 實際呼叫腳本、餵真實參數/stdin，檢查 stdout/exit code，
    而不是 import 內部函式白箱測試。理由：這些腳本被設計成「不依賴任何
    特定平台呼叫方式」的獨立 CLI（見 規格總覽.md 1-3），黑箱測試才真正驗證
    使用者/agent 實際呼叫時會發生什麼事，而不是驗證 Python import 路徑通不通。
  - `adad_core.py` 本身已有內建的 run_self_test()（見 test_adad_core_selftest.py），
    覆蓋核心邏輯的細節分支；這裡的黑箱測試著重在每支 CLI 腳本的「輸入/輸出契約」
    與「錯誤路徑」，兩者互補，不重複造輪子。
  - 每個測試都在 tmp_path 底下的乾淨假專案跑，不會動到真正的
    system_map.md / system_map.yaml，也不需要 git 使用者身分等外部狀態
    （adad_pre_commit 測試除外，那支本質上就是 git hook，需要一個真的 tmp git repo）。
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

try:
    import yaml
except ImportError:  # pragma: no cover
    yaml = None

# tests/ 在 repo 根目錄底下，腳本則在 adad_cli/resources/.../scripts/ 底下。
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = (
    REPO_ROOT
    / "adad_cli"
    / "resources"
    / "agents"
    / "skills"
    / "adad-workflow"
    / "scripts"
)


def script_path(name):
    """回傳 scripts/ 目錄下某支腳本的絕對路徑，找不到就直接讓測試失敗並給出清楚訊息。"""
    p = SCRIPTS_DIR / name
    assert p.exists(), f"找不到腳本 {p}（SCRIPTS_DIR 設定是否正確？）"
    return str(p)


def run_script(name, args=None, cwd=None, input_text=None, env=None):
    """
    呼叫 <name> 這支 CLI 腳本。

    回傳 (returncode, parsed_json_or_None, stdout, stderr)：
      - parsed_json 在 stdout 不是合法 JSON 時為 None（例如 resume_analysis.py
        輸出的是 Markdown 報告，不是 JSON，呼叫端這種情況應該只看 stdout 原文）。
      - input_text 用於需要餵 stdin 的腳本（例如 adad_pretooluse_gate.py）；
        不帶 input_text 時 stdin 預設是空字串，等同非互動情境
        （這正好用來驗證 adad_task.py approve/reject 的「非 tty 一律拒絕」邏輯）。
    """
    cmd = [sys.executable, script_path(name)] + (args or [])
    proc = subprocess.run(
        cmd,
        cwd=cwd,
        capture_output=True,
        text=True,
        input=input_text if input_text is not None else "",
        env=env,
    )
    parsed = None
    try:
        parsed = json.loads(proc.stdout)
    except (json.JSONDecodeError, ValueError):
        parsed = None
    return proc.returncode, parsed, proc.stdout, proc.stderr


@pytest.fixture
def project_dir(tmp_path, monkeypatch):
    """
    一個乾淨的假 ADAD 專案目錄：把 cwd 切過去，讓腳本讀寫的
    system_map.yaml / .agents/tasks/ 等相對路徑都落在這裡，
    不會動到真正的 repo 或互相污染其他測試。
    """
    monkeypatch.chdir(tmp_path)
    return tmp_path


def write_yaml(project_dir, data):
    """把一份 dict 寫成 project_dir/system_map.yaml。"""
    assert yaml is not None, "此測試需要 PyYAML，請先 pip install pyyaml"
    with open(project_dir / "system_map.yaml", "w", encoding="utf-8") as f:
        yaml.safe_dump(data, f, allow_unicode=True, sort_keys=False)


def read_yaml(project_dir):
    assert yaml is not None, "此測試需要 PyYAML，請先 pip install pyyaml"
    with open(project_dir / "system_map.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def make_module(**overrides):
    """
    產生一份符合 system_map.schema.json 必要欄位的最小 module dict，
    可用 overrides 覆蓋任何欄位，避免每個測試都要重複寫滿全部必填欄位。
    """
    base = {
        "type": "tool",
        "description": "測試用範例模組",
        "source": "sample_tool.py",
        "domain": None,
        "subsystem": None,
        "map_file": "system_map.md",
        "dependencies": [],
        "input": {"x": "int"},
        "output": {"y": "int"},
        "invariants": [],
        "preferred_pattern": "none",
        "verification": [],
        "decisions": [],
        "todo": [],
        "checkpoint": [],
        "complexity": "low",
        "algorithm": [],
        "state": "planned",
    }
    base.update(overrides)
    return base


@pytest.fixture
def base_modules():
    """一份只有一個模組 `sample_tool` 的最小 system_map 資料，個別測試依需求覆蓋擴充。"""
    return {
        "version": 1,
        "modules": {
            "sample_tool": make_module(),
        },
        "domains": {},
    }
