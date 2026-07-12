from adad_cli.sync_assets import SOURCE_ROOT, _copy_tree, _tree_files, managed_assets, sync_assets


def test_canonical_assets_are_complete():
    files, trees = managed_assets()

    assert SOURCE_ROOT.is_dir()
    assert all(source.exists() for source, _ in [*files, *trees])


def test_generated_assets_match_canonical_source():
    result = sync_assets(write=False)

    assert result == {"success": True, "mode": "check", "differences": []}


def test_cache_files_are_not_managed_or_copied(tmp_path):
    source = tmp_path / "source"
    target = tmp_path / "target"
    (source / "__pycache__").mkdir(parents=True)
    source.joinpath("managed.txt").write_text("canonical", encoding="utf-8")
    source.joinpath("__pycache__", "module.cpython-311.pyc").write_bytes(b"cache")
    (target / "__pycache__").mkdir(parents=True)
    target.joinpath("__pycache__", "stale.pyc").write_bytes(b"stale")

    assert _tree_files(source) == {"managed.txt": b"canonical"}

    _copy_tree(source, target)

    assert _tree_files(target) == {"managed.txt": b"canonical"}
    assert not target.joinpath("__pycache__").exists()
