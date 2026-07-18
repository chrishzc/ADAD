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


def test_run_utf8_subprocess_success():
    from adad_cli.platform_io import run_utf8_subprocess
    import sys
    res = run_utf8_subprocess([sys.executable, "-c", "print('hello world')"])
    assert res["returncode"] == 0
    assert "hello world" in res["stdout"]
    assert res["timeout"] is False


def test_run_utf8_subprocess_timeout():
    from adad_cli.platform_io import run_utf8_subprocess
    import sys
    res = run_utf8_subprocess([sys.executable, "-c", "import time; time.sleep(2)"], timeout=0.1)
    assert res["returncode"] == -1
    assert res["timeout"] is True
    assert "[TIMEOUT]" in res["stderr"]


def test_run_utf8_subprocess_fallback_decode():
    from adad_cli.platform_io import run_utf8_subprocess
    import sys
    # \xa4\xa4 is CP950 for '中'. \xff\xfe is invalid UTF-8 byte
    code = "import sys; sys.stdout.buffer.write(b'\\xa4\\xa4\\xff\\xfe')"
    res = run_utf8_subprocess([sys.executable, "-c", code])
    assert res["returncode"] == 0
    assert len(res["stdout"]) > 0
