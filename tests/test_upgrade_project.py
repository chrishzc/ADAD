from pathlib import Path

import adad_cli.core as core
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


def test_upgrade_excludes_python_cache_from_agent_outputs_and_report(tmp_path, monkeypatch):
    project = _initialized_project(tmp_path / "project")
    source_agents = tmp_path / "source" / "agents"
    source_skill = source_agents / "skills" / "adad-workflow"
    source_skill.joinpath("nested", "__pycache__").mkdir(parents=True)
    source_skill.joinpath("nested", "managed.py").write_text("managed", encoding="utf-8")
    source_skill.joinpath("added.txt").write_text("added", encoding="utf-8")
    source_skill.joinpath("loose.pyc").write_bytes(b"cache")
    source_skill.joinpath("nested", "__pycache__", "managed.cpython-311.pyc").write_bytes(b"cache")
    source_agents.joinpath("AGENTS.md").write_text("rules", encoding="utf-8")

    local_skill = project / ".agents" / "skills" / "adad-workflow"
    local_skill.joinpath("nested").mkdir(parents=True)
    local_skill.joinpath("nested", "managed.py").write_text("old", encoding="utf-8")
    local_skill.joinpath("unchanged.txt").write_text("same", encoding="utf-8")
    source_skill.joinpath("unchanged.txt").write_text("same", encoding="utf-8")

    monkeypatch.setattr(core, "agents_dir", lambda: source_agents)

    result = upgrade_project(
        agents=["antigravity", "claude"],
        project_root=str(project),
    )

    for skill_root in (
        project / ".agents" / "skills" / "adad-workflow",
        project / ".claude" / "skills" / "adad-workflow",
    ):
        assert skill_root.joinpath("nested", "managed.py").read_text(encoding="utf-8") == "managed"
        assert skill_root.joinpath("added.txt").read_text(encoding="utf-8") == "added"
        assert not any(
            "__pycache__" in path.relative_to(skill_root).parts or path.suffix == ".pyc"
            for path in skill_root.rglob("*")
        )

    for status in ("added", "updated", "unchanged"):
        assert not any(
            "__pycache__" in Path(path).parts or Path(path).suffix == ".pyc"
            for path in result["report"][status]
        )

    assert str(local_skill / "added.txt") in result["report"]["added"]
    assert str(local_skill / "nested" / "managed.py") in result["report"]["updated"]
    assert str(local_skill / "unchanged.txt") in result["report"]["unchanged"]
