from copy import deepcopy

import pytest
from amulet_nbt import IntTag, StringTag, from_snbt

from structura_core.nbt import write_root
from structura_core.world import JavaWorld, read_chunk
from structura_core.world_write import save_world_patch
from test_world import region_file


@pytest.fixture
def editable_world(tmp_path):
    pytest.importorskip("amulet")
    write_root(from_snbt('{Data:{DataVersion:3955,LevelName:"Edit test"}}'), tmp_path / "level.dat")
    chunk = from_snbt('''{DataVersion:3955,xPos:0,zPos:0,Status:"minecraft:full",custom:{keep:42},
        sections:[{Y:0b,block_states:{palette:[{Name:"minecraft:stone"}]},
                   biomes:{palette:["minecraft:plains"]},BlockLight:[B;1b,2b,3b]}],
        Heightmaps:{custom:[L;1L,2L]},isLightOn:1b,
        block_entities:[{id:"minecraft:chest",x:1,y:1,z:1,Items:[{Slot:0b,id:"minecraft:diamond",count:3}]}],
        block_ticks:[{x:0,y:0,z:0,i:"minecraft:stone",t:4},{x:2,y:0,z:0,i:"minecraft:stone",t:4}]}''')
    region_file(tmp_path / "region", 0, 0, chunk)
    region_file(tmp_path / "poi", 0, 0, from_snbt('{Sections:{"0":{Valid:1b,Records:[]},"1":{Valid:1b,Records:[]}}}'))
    return JavaWorld(tmp_path)


def patch(position=(0, 0, 0), state="minecraft:gold_block"):
    return {("minecraft:overworld", *position): (("minecraft:stone", None), (state, None))}


def test_world_save_preserves_unrelated_data_and_keeps_restorable_backup(editable_world):
    world = editable_world
    path = world.path / "region/r.0.0.mca"
    original = path.read_bytes()
    before = read_chunk(world.path / "region", 0, 0)
    backup = save_world_patch(world.path, patch())
    root = read_chunk(world.path / "region", 0, 0)
    assert (backup / "region/r.0.0.mca").read_bytes() == original
    assert root["custom"] == before["custom"] and root["block_entities"] == before["block_entities"]
    assert root["sections"][0]["biomes"] == before["sections"][0]["biomes"]
    assert "Heightmaps" not in root and not root["isLightOn"] and "BlockLight" not in root["sections"][0]
    assert len(root["block_ticks"]) == 1 and int(root["block_ticks"][0]["x"]) == 2
    poi = read_chunk(world.path / "poi", 0, 0)
    assert not poi["Sections"]["0"]["Valid"] and poi["Sections"]["1"]["Valid"]
    source = world.read_region((0, 8, 0), radius=0, vertical_radius=16).structure
    assert source.name_at((0, -source.source_origin[1], 0)) == "minecraft:gold_block"
    assert save_world_patch(world.path, patch()) is None


def test_conflict_aborts_entire_save_before_install(editable_world):
    world = editable_world
    region = world.path / "region/r.0.0.mca"
    original = region.read_bytes()
    changes = patch()
    changes.update({("minecraft:overworld", 1, 0, 0): (("minecraft:dirt", None), ("minecraft:glass", None))})
    with pytest.raises(ValueError, match="World changed"):
        save_world_patch(world.path, changes)
    assert region.read_bytes() == original and not (world.path / ".structura/backups").exists()
    changes = patch((0, 32, 0))
    with pytest.raises(ValueError, match="section is absent"):
        save_world_patch(world.path, changes)
    assert region.read_bytes() == original


def test_external_chunk_and_detached_block_entity_roundtrip(editable_world):
    world = editable_world
    root = read_chunk(world.path / "region", 0, 0)
    region_file(world.path / "region", 0, 0, root, external=True)
    payload = deepcopy(root["block_entities"][0])
    for axis in "xyz":
        payload[axis] = IntTag(0)
    changes = patch()
    changes["minecraft:overworld", 0, 0, 0] = (("minecraft:stone", None), ("minecraft:chest", payload.to_snbt()))
    changes["minecraft:overworld", 1, 1, 1] = (("minecraft:stone", payload.to_snbt()), ("minecraft:air", None))
    backup = save_world_patch(world.path, changes)
    saved = read_chunk(world.path / "region", 0, 0)
    assert len(saved["block_entities"]) == 1
    entity = saved["block_entities"][0]
    assert tuple(int(entity[axis]) for axis in "xyz") == (0, 0, 0) and entity["Items"] == payload["Items"]
    assert (backup / "region/c.0.0.mcc").is_file()
    assert not (world.path / "region/c.0.0.mcc").exists()


def test_concurrent_writer_is_detected_after_preparation(editable_world, monkeypatch):
    from structura_core.world_staging import StagedWorld

    world = editable_world
    original_write = StagedWorld.write
    def write(self, *args):
        original_write(self, *args)
        chunk = read_chunk(world.path / "region", 0, 0)
        chunk["custom"]["outside"] = StringTag("keep concurrent edit")
        region_file(world.path / "region", 0, 0, chunk)
    monkeypatch.setattr(StagedWorld, "write", write)
    with pytest.raises(ValueError, match="World changed while saving"):
        save_world_patch(world.path, patch())
    root = read_chunk(world.path / "region", 0, 0)
    assert str(root["custom"]["outside"]) == "keep concurrent edit"
    assert len(root["sections"][0]["block_states"]["palette"]) == 1


def test_partial_install_keeps_backups_and_can_be_retried(editable_world, monkeypatch):
    import json
    from structura_core import world_staging

    world = editable_world
    target = world.path / "region/r.0.0.mca"
    before = target.read_bytes()
    replace = world_staging.os.replace
    def fail(source, destination):
        if destination == target:
            raise OSError("test disk failure")
        replace(source, destination)
    monkeypatch.setattr(world_staging.os, "replace", fail)
    with pytest.raises(OSError, match="Backup:"):
        save_world_patch(world.path, patch())
    backup = next((world.path / ".structura/backups").iterdir())
    assert (backup / "region/r.0.0.mca").read_bytes() == before and target.read_bytes() == before
    manifest = json.loads((backup / "manifest.json").read_text())
    assert manifest["installed"] == ["poi/r.0.0.mca"]
    monkeypatch.setattr(world_staging.os, "replace", replace)
    assert save_world_patch(world.path, patch()).is_dir()


def test_world_conflicts_lists_only_changed_positions(editable_world):
    from structura_core.world_write import world_conflicts

    world = editable_world
    changes = patch()
    changes.update({("minecraft:overworld", 1, 0, 0): (("minecraft:dirt", None), ("minecraft:glass", None))})
    conflicts = world_conflicts(world.path, changes)
    assert conflicts == [((1, 0, 0), "minecraft:dirt", "minecraft:stone", "minecraft:glass")]


def test_force_write_overwrites_conflicting_disk_state(editable_world):
    from structura_core.world_write import world_conflicts

    world = editable_world
    changes = patch()
    changes.update({("minecraft:overworld", 1, 0, 0): (("minecraft:dirt", None), ("minecraft:glass", None))})
    assert len(world_conflicts(world.path, changes)) == 1
    save_world_patch(world.path, changes, force=True)
    source = world.read_region((0, 8, 0), radius=0, vertical_radius=16).structure
    assert source.name_at((0, -source.source_origin[1], 0)) == "minecraft:gold_block"
    assert source.name_at((1, -source.source_origin[1], 0)) == "minecraft:glass"


def test_backup_listing_verify_and_restore(editable_world):
    from structura_core.world_staging import list_backups, restore_backup, verify_backup

    world = editable_world
    target = world.path / "region/r.0.0.mca"
    original = target.read_bytes()
    save_world_patch(world.path, patch())
    modified = target.read_bytes()
    assert modified != original
    backups = list_backups(world.path)
    assert len(backups) == 1 and backups[0]["files"]
    backup = backups[0]["path"]
    assert verify_backup(backup)
    result = restore_backup(world.path, backup)
    assert result["restored"] == len(backups[0]["files"])
    assert target.read_bytes() == original
    safety = list_backups(world.path)[0]
    assert safety["name"].endswith(result["safety"].split("/")[-1]) or "restore" in safety["name"]
    assert restore_backup(world.path, backup)["restored"] >= 1
