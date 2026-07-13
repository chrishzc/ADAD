# -*- coding: utf-8 -*-
import os
import subprocess
import shlex
from typing import List, Optional, Dict, Any

def run_utf8_subprocess(argv: List[str], cwd: Optional[str] = None) -> Dict[str, Any]:
    """
    ponytail: stdlib subprocess already handles this if we just pass encoding='utf-8' and force env.
    """
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    p = subprocess.run(argv, cwd=cwd, capture_output=True, text=True, encoding="utf-8", env=env)
    return {"returncode": p.returncode, "stdout": p.stdout, "stderr": p.stderr}

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
