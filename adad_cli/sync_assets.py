"""Synchronize generated ADAD workflow assets from the canonical source tree."""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parent.parent
SOURCE_ROOT = REPOSITORY_ROOT / "adad_source"


def _tree_files(root: Path) -> dict[str, bytes]:
    """Return a stable relative-path-to-content view of a directory tree."""
    assert root.is_dir(), f"Missing source directory: {root}"
    return {
        path.relative_to(root).as_posix(): path.read_bytes()
        for path in sorted(root.rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.relative_to(root).parts
        and path.suffix != ".pyc"
    }


def _compare_file(source: Path, target: Path, target_root: Path) -> list[str]:
    if not target.is_file() or source.read_bytes() != target.read_bytes():
        return [str(target.relative_to(target_root))]
    return []


def _compare_tree(source: Path, target: Path, target_root: Path) -> list[str]:
    source_files = _tree_files(source)
    if not target.is_dir():
        return [str(target.relative_to(target_root))]

    target_files = _tree_files(target)
    return [
        str(target.relative_to(target_root) / relative_path)
        for relative_path in sorted(set(source_files) | set(target_files))
        if source_files.get(relative_path) != target_files.get(relative_path)
    ]


def _copy_file(source: Path, target: Path) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source, target)


def _copy_tree(source: Path, target: Path) -> None:
    if target.exists():
        shutil.rmtree(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(source, target, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))


def managed_assets(
    target_root: Path = REPOSITORY_ROOT,
) -> tuple[list[tuple[Path, Path]], list[tuple[Path, Path]]]:
    """Return canonical file and directory mappings without touching project state."""
    agents = SOURCE_ROOT / "agents"
    resources = target_root / "adad_cli" / "resources"
    files = [
        (agents / "AGENTS.md", target_root / ".agents" / "AGENTS.md"),
        (agents / "AGENTS.md", resources / "agents" / "AGENTS.md"),
    ]
    trees = [
        (agents / "skills" / "adad-workflow", target_root / ".agents" / "skills" / "adad-workflow"),
        (agents / "skills" / "adad-workflow", resources / "agents" / "skills" / "adad-workflow"),
        (SOURCE_ROOT / "templates", resources / "templates"),
    ]
    return files, trees


def sync_assets(
    write: bool,
    target_root: Path | None = None,
) -> dict[str, object]:
    """Synchronize or verify the managed asset outputs from ``adad_source``."""
    target_root = REPOSITORY_ROOT if target_root is None else Path(target_root)
    files, trees = managed_assets(target_root)
    for source, _ in [*files, *trees]:
        assert source.exists(), f"Missing canonical asset: {source}"

    if write:
        for source, target in files:
            _copy_file(source, target)
        for source, target in trees:
            _copy_tree(source, target)

    differences = [
        difference
        for source, target in files
        for difference in _compare_file(source, target, target_root)
    ] + [
        difference
        for source, target in trees
        for difference in _compare_tree(source, target, target_root)
    ]
    return {"success": not differences, "mode": "write" if write else "check", "differences": differences}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true", help="regenerate managed asset outputs")
    mode.add_argument("--check", action="store_true", help="verify managed outputs match adad_source")
    args = parser.parse_args()

    result = sync_assets(write=args.write)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["success"] else 1


if __name__ == "__main__":
    sys.exit(main())
