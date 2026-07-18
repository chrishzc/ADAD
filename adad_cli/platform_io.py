# -*- coding: utf-8 -*-
import os
import subprocess
import shlex
from typing import List, Optional, Dict, Any

def run_utf8_subprocess(argv: List[str], cwd: Optional[str] = None, timeout: Optional[float] = None) -> Dict[str, Any]:
    """
    ponytail: stdlib subprocess.run with bytes capture and fallback decoding.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    try:
        p = subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            timeout=timeout,
            env=env
        )
        return {
            "returncode": p.returncode,
            "stdout": _safe_decode(p.stdout),
            "stderr": _safe_decode(p.stderr),
            "timeout": False
        }
    except subprocess.TimeoutExpired as exc:
        stdout = _safe_decode(exc.stdout)
        stderr = _safe_decode(exc.stderr)
        msg = f"[TIMEOUT] Command timed out after {timeout}s"
        return {
            "returncode": -1,
            "stdout": stdout,
            "stderr": f"{stderr}\n{msg}" if stderr else msg,
            "timeout": True
        }
    except Exception as e:
        return {
            "returncode": -1,
            "stdout": "",
            "stderr": f"[ERROR] Failed to execute command: {e}",
            "timeout": False
        }

def _safe_decode(b: Optional[bytes]) -> str:
    if not b:
        return ""
    try:
        return b.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        import locale
        pref = locale.getpreferredencoding()
        if pref and pref.lower() != "utf-8":
            return b.decode(pref, errors="replace")
    except Exception:
        pass
    return b.decode("utf-8", errors="replace")


def render_portable_python_hook_command(python_executable: str, script_path: str, platform_family: str) -> str:
    """
    ponytail: pure string formatting. POSIX gets shlex, Windows gets subprocess.list2cmdline.
    """
    if platform_family == "windows":
        return subprocess.list2cmdline([python_executable, script_path])
    elif platform_family == "posix":
        return f"{shlex.quote(python_executable)} {shlex.quote(script_path)}"
    else:
        raise ValueError(f"Unknown or unsupported platform family: {platform_family}")
