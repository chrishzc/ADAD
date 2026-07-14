from pathlib import Path

from adad_cli.core import upgrade_project
from adad_cli.resources import templates_dir


def _initialized_project(tmp_path: Path) -> Path:
    (tmp_path / ".agents" / "skills" / "adad-workflow").mkdir(parents=True)
    return tmp_path


def test_upgrade_replaces_root_schemas_and_keeps_backups(tmp_path):
    project = _initialized_project(tmp_path)
    for name in ("system_map.schema.json", "task_schema.json"):
        (project / name).write_text('{"old": true}', encoding="utf-8")

    result = upgrade_project(agents=["antigravity"], project_root=str(project))

    assert result["success"] is True
    for name in ("system_map.schema.json", "task_schema.json"):
        assert (project / name).read_bytes() == (templates_dir() / name).read_bytes()
        assert (project / f"{name}.bak").read_text(encoding="utf-8") == '{"old": true}'


def test_upgrade_adds_missing_root_schemas(tmp_path):
    project = _initialized_project(tmp_path)

    upgrade_project(agents=["antigravity"], project_root=str(project))

    assert (project / "system_map.schema.json").exists()
    assert (project / "task_schema.json").exists()
