"""Setuptools hooks that keep generated package resources free of bytecode."""

from __future__ import annotations

import shutil
from pathlib import Path

from setuptools.command.build_py import build_py as _BuildPy


def _purge_python_cache(root: Path) -> None:
    """Remove bytecode from an existing build output without touching sources."""
    if not root.is_dir():
        return
    for cache_dir in sorted(root.rglob("__pycache__"), reverse=True):
        if cache_dir.is_dir():
            shutil.rmtree(cache_dir)
    for bytecode in root.rglob("*.pyc"):
        if bytecode.is_file():
            bytecode.unlink()


class CleanResourceBuildPy(_BuildPy):
    """Prevent stale ``build/lib`` bytecode from leaking into package archives."""

    def _resources_output(self) -> Path:
        return Path(self.build_lib) / "adad_cli" / "resources"

    def run(self) -> None:
        _purge_python_cache(self._resources_output())
        super().run()
        _purge_python_cache(self._resources_output())
