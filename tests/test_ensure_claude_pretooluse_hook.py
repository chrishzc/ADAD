import os
import json
import pytest
from unittest.mock import patch
from adad_cli.core import _ensure_claude_pretooluse_hook, PRETOOLUSE_GATE_MATCHER

def test_ensure_claude_pretooluse_hook_creation(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"

    # Run first time - should create
    res = _ensure_claude_pretooluse_hook(str(settings_json))
    assert res["success"] is True
    assert res["status"] == "created"

    # Read settings and verify content
    with open(settings_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    pretooluse = data["hooks"]["PreToolUse"]
    assert len(pretooluse) == 1
    assert pretooluse[0]["matcher"] == PRETOOLUSE_GATE_MATCHER
    hooks = pretooluse[0]["hooks"]
    assert len(hooks) == 1
    assert hooks[0]["type"] == "command"
    assert "adad_pretooluse_gate.py" in hooks[0]["command"]
    assert str(tmp_path) not in hooks[0]["command"]
    assert hooks[0]["command"].startswith(".venv")

def test_ensure_claude_pretooluse_hook_unchanged_and_mtime(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"

    # Run first time - should create
    _ensure_claude_pretooluse_hook(str(settings_json))

    # Record mtime
    initial_mtime = os.path.getmtime(settings_json)

    # Run second time - should be unchanged
    res = _ensure_claude_pretooluse_hook(str(settings_json))
    assert res["success"] is True
    assert res["status"] == "unchanged"

    # Verify mtime is identical
    assert os.path.getmtime(settings_json) == initial_mtime

def test_ensure_claude_pretooluse_hook_update(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"
    os.makedirs(settings_json.parent, exist_ok=True)

    # Create with an outdated/different command
    initial_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": PRETOOLUSE_GATE_MATCHER,
                    "hooks": [
                        {"type": "command", "command": "python3 /old/path/adad_pretooluse_gate.py"}
                    ]
                }
            ]
        }
    }
    with open(settings_json, "w", encoding="utf-8") as f:
        json.dump(initial_settings, f)

    res = _ensure_claude_pretooluse_hook(str(settings_json))
    assert res["success"] is True
    assert res["status"] == "updated"

    with open(settings_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    pretooluse = data["hooks"]["PreToolUse"]
    assert len(pretooluse) == 1
    hooks = pretooluse[0]["hooks"]
    assert len(hooks) == 1
    assert "adad_pretooluse_gate.py" in hooks[0]["command"]
    assert str(tmp_path) not in hooks[0]["command"]
    assert hooks[0]["command"].startswith(".venv")
    assert "python3 /old/path/" not in hooks[0]["command"]

def test_ensure_claude_pretooluse_hook_skipped_on_invalid_json(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"
    os.makedirs(settings_json.parent, exist_ok=True)

    # Write invalid JSON
    invalid_content = "{invalid json"
    with open(settings_json, "w", encoding="utf-8") as f:
        f.write(invalid_content)

    initial_mtime = os.path.getmtime(settings_json)

    res = _ensure_claude_pretooluse_hook(str(settings_json))
    assert res["success"] is False
    assert res["status"] == "skipped_invalid_json"

    # File content must not be modified
    with open(settings_json, "r", encoding="utf-8") as f:
        assert f.read() == invalid_content

    # mtime must remain unchanged
    assert os.path.getmtime(settings_json) == initial_mtime

def test_ensure_claude_pretooluse_hook_preserves_other_hooks(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"
    os.makedirs(settings_json.parent, exist_ok=True)

    # Set up settings with other hooks and other matchers
    initial_settings = {
        "hooks": {
            "PreToolUse": [
                {
                    "matcher": "Bash",
                    "hooks": [{"type": "command", "command": "echo 'bash hook'"}]
                },
                {
                    "matcher": PRETOOLUSE_GATE_MATCHER,
                    "hooks": [{"type": "command", "command": "echo 'some other user hook'"}]
                }
            ]
        }
    }
    with open(settings_json, "w", encoding="utf-8") as f:
        json.dump(initial_settings, f)

    res = _ensure_claude_pretooluse_hook(str(settings_json))
    assert res["success"] is True

    with open(settings_json, "r", encoding="utf-8") as f:
        data = json.load(f)

    # Check that other matcher is preserved
    pretooluse = data["hooks"]["PreToolUse"]
    assert len(pretooluse) == 2

    bash_hook = next(h for h in pretooluse if h["matcher"] == "Bash")
    assert len(bash_hook["hooks"]) == 1
    assert bash_hook["hooks"][0]["command"] == "echo 'bash hook'"

    # Check that our matcher contains both the old user hook and the new adad hook
    adad_matcher_hook = next(h for h in pretooluse if h["matcher"] == PRETOOLUSE_GATE_MATCHER)
    assert len(adad_matcher_hook["hooks"]) == 2
    commands = [h["command"] for h in adad_matcher_hook["hooks"]]
    assert "echo 'some other user hook'" in commands
    assert any("adad_pretooluse_gate.py" in cmd for cmd in commands)

def test_ensure_claude_pretooluse_hook_cross_platform_mock(tmp_path):
    settings_json = tmp_path / ".claude" / "settings.json"

    # Test Windows platform family mapping
    with patch("os.name", "nt"), patch("adad_cli.core._project_venv_python", return_value="C:\\My Python Path\\python.exe"):
        res = _ensure_claude_pretooluse_hook(str(settings_json))
        assert res["success"] is True

        with open(settings_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        # Windows command rendering uses double quotes when spaces are present
        assert cmd.startswith('"')
        assert 'C:\\My Python Path\\python.exe' in cmd

    # Reset file
    os.remove(settings_json)

    # Test POSIX platform family mapping
    with patch("os.name", "posix"), patch("adad_cli.core._project_venv_python", return_value="/my python path/bin/python"):
        res = _ensure_claude_pretooluse_hook(str(settings_json))
        assert res["success"] is True

        with open(settings_json, "r", encoding="utf-8") as f:
            data = json.load(f)
        cmd = data["hooks"]["PreToolUse"][0]["hooks"][0]["command"]
        # POSIX command rendering uses shlex.quote, which adds single quotes for spaces
        assert cmd.startswith("'")
        assert 'adad_pretooluse_gate.py' in cmd

    # Reset file
    os.remove(settings_json)

    # Test Unsupported platform
    with patch("os.name", "unknown_os"):
        with pytest.raises(ValueError, match="Unsupported OS name"):
            _ensure_claude_pretooluse_hook(str(settings_json))
