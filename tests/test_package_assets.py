import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _build_archives(project: Path, output: Path) -> tuple[Path, Path]:
    script = (
        "from pathlib import Path; "
        "from setuptools import build_meta; "
        f"output = {str(output)!r}; "
        "Path(output).mkdir(parents=True, exist_ok=True); "
        "print(build_meta.build_wheel(output)); "
        "print(build_meta.build_sdist(output))"
    )
    subprocess.run(
        [sys.executable, "-c", script],
        cwd=project,
        check=True,
        capture_output=True,
        text=True,
        timeout=120,
    )
    return next(output.glob("*.whl")), next(output.glob("*.tar.gz"))


def _contains_python_cache(path: str) -> bool:
    parts = Path(path.replace("\\", "/")).parts
    return "__pycache__" in parts or path.endswith(".pyc")


def test_built_archives_exclude_python_cache(tmp_path):
    project = tmp_path / "project"
    output = tmp_path / "dist"
    project.mkdir()
    shutil.copy2(PROJECT_ROOT / "pyproject.toml", project / "pyproject.toml")
    shutil.copytree(PROJECT_ROOT / "adad_cli", project / "adad_cli")

    resources = project / "adad_cli" / "resources"
    cache_dir = resources / "nested" / "__pycache__"
    cache_dir.mkdir(parents=True)
    cache_dir.joinpath("cached.cpython-311.pyc").write_bytes(b"cache")
    resources.joinpath("nested", "loose.pyc").write_bytes(b"cache")

    wheel, sdist = _build_archives(project, output)

    with zipfile.ZipFile(wheel) as archive:
        wheel_names = archive.namelist()
    with tarfile.open(sdist, "r:gz") as archive:
        sdist_names = archive.getnames()

    assert any(name.endswith("resources/agents/AGENTS.md") for name in wheel_names)
    assert any(name.endswith("resources/agents/AGENTS.md") for name in sdist_names)
    assert not any(_contains_python_cache(name) for name in wheel_names)
    assert not any(_contains_python_cache(name) for name in sdist_names)
