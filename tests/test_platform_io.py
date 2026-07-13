import pytest
from adad_cli.platform_io import render_portable_python_hook_command

def test_render_portable_python_hook_command_windows():
    cmd = render_portable_python_hook_command(
        "C:\\Program Files\\Python\\python.exe",
        "C:\\Project Space\\hook.py",
        "windows"
    )
    assert cmd == '"C:\\Program Files\\Python\\python.exe" "C:\\Project Space\\hook.py"'

def test_render_portable_python_hook_command_posix():
    cmd = render_portable_python_hook_command(
        "/opt/My Python/bin/python",
        "/work/My Project/hook.py",
        "posix"
    )
    assert cmd == "'/opt/My Python/bin/python' '/work/My Project/hook.py'"

def test_render_portable_python_hook_command_win32_rejected():
    with pytest.raises(ValueError, match="Unknown or unsupported platform family"):
        render_portable_python_hook_command("python", "hook.py", "win32")
