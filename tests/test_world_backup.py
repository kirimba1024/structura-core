import json
from pathlib import Path, PureWindowsPath

import pytest

from structura_core.world_staging import StagedWorld, list_backups, restore_backup, verify_backup
from structura_core.world_backup import pending_backups


def stage(root, values, directory):
    staged = StagedWorld(root, directory)
    for name, value in values.items():
        path = staged.file(root / name)
        if value is None:
            path.unlink(missing_ok=True)
        else:
            path.write_text(value)
        staged.changed.add(Path(name))
    return staged


def test_restore_reverses_created_and_deleted_files(tmp_path):
    world = tmp_path / "world"
    world.mkdir()
    (world / "deleted.dat").write_text("original")
    saved = stage(world, {"created.dat": "new", "deleted.dat": None}, tmp_path / "stage").install()
    assert verify_backup(saved)
    result = restore_backup(world, saved)
    assert not (world / "created.dat").exists()
    assert (world / "deleted.dat").read_text() == "original"
    restore_backup(world, result["safety"])
    assert (world / "created.dat").read_text() == "new"
    assert not (world / "deleted.dat").exists()


def test_nested_manifest_paths_are_portable_and_restore_on_either_platform(tmp_path):
    from structura_core.world_backup import digest, install_staged, read_manifest

    world = tmp_path / "world"
    relative = PureWindowsPath("region") / "r.0.0.mca"
    original = world / relative.as_posix()
    original.parent.mkdir(parents=True)
    original.write_bytes(b"original")
    temporary = tmp_path / "stage"
    for name, data in (("before", b"original"), ("after", b"changed")):
        path = temporary / name / relative.as_posix()
        path.parent.mkdir(parents=True)
        path.write_bytes(data)
    backup = install_staged(world, temporary, {relative: digest(original)}, {relative})
    manifest = read_manifest(backup)
    assert list(manifest["files"]) == ["region/r.0.0.mca"]
    assert manifest["installed"] == ["region/r.0.0.mca"]
    assert original.read_bytes() == b"changed"
    restore_backup(world, backup)
    assert original.read_bytes() == b"original"


@pytest.mark.parametrize("fail_after_replace", [False, True])
def test_interrupted_manifest_is_recovered_from_real_hashes(tmp_path, monkeypatch, fail_after_replace):
    import structura_core.world_backup as backups

    world = tmp_path / "world"
    world.mkdir()
    for name in ("a.dat", "b.dat"):
        (world / name).write_text("old")
    staged = stage(world, {"a.dat": "new", "b.dat": "new"}, tmp_path / "stage")
    original_replace = backups.os.replace
    def failed(source, target):
        target = Path(target)
        if target == world / "b.dat":
            if fail_after_replace:
                original_replace(source, target)
            raise OSError("injected interruption")
        return original_replace(source, target)
    monkeypatch.setattr(backups.os, "replace", failed)
    with pytest.raises(OSError, match="interrupted"):
        staged.install()
    pending = pending_backups(world)
    assert len(pending) == 1
    record = json.loads((Path(pending[0]["path"]) / "manifest.json").read_text())
    assert record["installed"] == ["a.dat"]
    monkeypatch.setattr(backups.os, "replace", original_replace)
    restore_backup(world, pending[0]["path"])
    assert not pending_backups(world)
    assert all((world / name).read_text() == "old" for name in ("a.dat", "b.dat"))


def test_manifest_paths_cannot_escape_world(tmp_path):
    backup = tmp_path / ".structura" / "backups" / "malformed"
    backup.mkdir(parents=True)
    (backup / "manifest.json").write_text(json.dumps({"files": {"../outside": None}, "installed": []}))
    with pytest.raises(ValueError, match="Invalid path"):
        verify_backup(backup)
    assert list_backups(tmp_path)[0]["phase"] == "invalid"


def test_restore_detects_concurrent_write_and_retains_safety(tmp_path, monkeypatch):
    import structura_core.world_backup as backups

    world = tmp_path / "world"
    world.mkdir()
    (world / "a.dat").write_text("old")
    backup = stage(world, {"a.dat": "new"}, tmp_path / "stage").install()
    replace = backups.replace_file
    def concurrent(source, target, expected):
        target.write_text("external")
        return replace(source, target, expected)
    monkeypatch.setattr(backups, "replace_file", concurrent)
    with pytest.raises(OSError, match="World changed"):
        restore_backup(world, backup)
    assert (world / "a.dat").read_text() == "external"
    safety = pending_backups(world)[0]
    assert (Path(safety["path"]) / "a.dat").read_text() == "new"


@pytest.mark.parametrize('call', range(1, 7))
@pytest.mark.parametrize('after_write', [False, True])
def test_manifest_failure_at_each_phase_is_recoverable(tmp_path, monkeypatch, call, after_write):
    import structura_core.world_backup as backups

    world = tmp_path / 'world'
    world.mkdir()
    (world / 'a.dat').write_text('old')
    staged = stage(world, {'a.dat': 'new', 'b.dat': 'created'}, tmp_path / 'stage')
    original = backups.write_manifest
    count = 0
    def fail(path, record):
        nonlocal count
        count += 1
        if count == call:
            if after_write:
                original(path, record)
            raise OSError('injected manifest failure')
        original(path, record)
    monkeypatch.setattr(backups, 'write_manifest', fail)
    with pytest.raises(OSError, match='interrupted'):
        staged.install()
    monkeypatch.setattr(backups, 'write_manifest', original)
    records = list_backups(world)
    if records and verify_backup(records[0]['path']):
        restore_backup(world, records[0]['path'])
    assert (world / 'a.dat').read_text() == 'old'
    assert not (world / 'b.dat').exists()
    assert not pending_backups(world)


def test_restore_requires_same_files_that_user_reviewed(tmp_path):
    from structura_core.world_backup import inspect_restore

    world = tmp_path / 'world'
    world.mkdir()
    (world / 'a.dat').write_text('old')
    backup = stage(world, {'a.dat': 'new'}, tmp_path / 'stage').install()
    (world / 'a.dat').write_text('external')
    review = inspect_restore(world, backup)
    assert review['verified'] and review['conflicts'] == ['a.dat']
    (world / 'a.dat').write_text('another writer')
    with pytest.raises(ValueError, match='after the restore review'):
        restore_backup(world, backup, expected=review['current'])
    assert (world / 'a.dat').read_text() == 'another writer'


@pytest.mark.parametrize('relative', ['a.dat', 'created.dat'])
@pytest.mark.parametrize('after_mutation', [False, True])
def test_restore_failure_during_replace_or_delete_can_be_retried(tmp_path, monkeypatch, relative, after_mutation):
    import structura_core.world_backup as backups

    world = tmp_path / 'world'
    world.mkdir()
    (world / 'a.dat').write_text('old')
    backup = stage(world, {'a.dat': 'new', 'created.dat': 'new'}, tmp_path / 'stage').install()
    original = backups.replace_file
    def fail(source, target, expected):
        if target == world / relative:
            if after_mutation:
                original(source, target, expected)
            raise OSError('injected restore interruption')
        original(source, target, expected)
    monkeypatch.setattr(backups, 'replace_file', fail)
    with pytest.raises(OSError, match='interrupted'):
        restore_backup(world, backup)
    assert pending_backups(world) and verify_backup(backup)
    monkeypatch.setattr(backups, 'replace_file', original)
    restore_backup(world, backup)
    assert (world / 'a.dat').read_text() == 'old'
    assert not (world / 'created.dat').exists() and not pending_backups(world)
