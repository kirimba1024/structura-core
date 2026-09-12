from copy import deepcopy

import pytest
from amulet_nbt import DoubleTag, ListTag, StringTag, from_snbt

from structura_core.nbt import load_root, write_root
from structura_core.world import JavaWorld, read_chunk
from structura_core.world_entities import EntityLocation
from structura_core.world_entity_write import EntityPatch
from structura_core.world_write import save_world_patch
from test_world import region_file

DIMENSION = "minecraft:overworld"


def payload(x=2):
    return from_snbt(f'''{{id:"mod:creature",Pos:[{x}d,5d,2d],UUID:[I;1,2,3,4],
                         Inventory:[{{id:"mod:gem",Count:2b,tag:{{quality:5L}}}}],mod:{{energy:123L}}}}''')


def put_entity(world, entity):
    region_file(world.path / "entities", 0, 0, from_snbt('{DataVersion:3955,Position:[I;0,0],Entities:[],custom:"preserve"}'))
    root = read_chunk(world.path / "entities", 0, 0)
    root["Entities"].append(entity)
    region_file(world.path / "entities", 0, 0, root)


def test_entity_inventory_move_between_chunks_and_idempotent_save(editable_world):
    world = editable_world
    before = payload()
    put_entity(world, before)
    other = deepcopy(read_chunk(world.path / "region", 0, 0))
    other["xPos"] = from_snbt("1")
    region_file(world.path / "region", 1, 0, other)
    after = deepcopy(before)
    after["Pos"][0] = DoubleTag(18)
    after["Inventory"][0]["Count"] = from_snbt("8b")
    change = EntityPatch(EntityLocation(DIMENSION, "entities", (0, 0)), before.to_snbt(),
                         EntityLocation(DIMENSION, "entities", (1, 0)), after.to_snbt())
    backup = save_world_patch(world.path, {}, entities=(change,))
    old = read_chunk(world.path / "entities", 0, 0)
    saved = read_chunk(world.path / "entities", 1, 0)
    assert not old["Entities"] and str(old["custom"]) == "preserve"
    assert saved["Entities"] == ListTag([after])
    assert (backup / "entities/r.0.0.mca").exists()
    assert save_world_patch(world.path, {}, entities=(change,)) is None


def test_entity_conflict_prevents_block_install(editable_world):
    world = editable_world
    before = payload()
    put_entity(world, before)
    changed = deepcopy(before)
    changed["Inventory"] = ListTag()
    location = EntityLocation(DIMENSION, "entities", (0, 0))
    path = world.path / "region/r.0.0.mca"
    original = path.read_bytes()
    blocks = {(DIMENSION, 0, 0, 0): (("minecraft:stone", None), ("minecraft:gold_block", None))}
    with pytest.raises(ValueError, match="World changed"):
        save_world_patch(world.path, blocks, entities=(EntityPatch(location, changed.to_snbt(), None, None),))
    assert path.read_bytes() == original


def test_player_inventory_updates_profile_and_level_without_chunk_player(editable_world):
    world = editable_world
    player = payload()
    player.pop("id")
    player["Dimension"] = StringTag(DIMENSION)
    root = load_root(world.path / "level.dat")
    root["Data"]["Player"] = player
    write_root(root, world.path / "level.dat")
    (world.path / "playerdata").mkdir()
    write_root(player, world.path / "playerdata/test.dat")
    loaded = JavaWorld(world.path).read_region((0, 8, 0), radius=0, vertical_radius=16)
    assert len(loaded.structure.entities) == 1 and loaded.entity_locations[0].file == "level.dat"
    before = deepcopy(player)
    before["id"] = StringTag("minecraft:player")
    after = deepcopy(before)
    after["Inventory"][0]["Count"] = from_snbt("9b")
    location = loaded.entity_locations[0]
    backup = save_world_patch(world.path, {}, entities=(EntityPatch(location, before.to_snbt(), location, after.to_snbt()),))
    saved = load_root(world.path / "level.dat")["Data"]["Player"]
    assert "id" not in saved and int(saved["Inventory"][0]["Count"]) == 9
    assert load_root(world.path / "playerdata/test.dat") == saved
    assert (backup / "level.dat").exists() and (backup / "playerdata/test.dat").exists()
    assert not (world.path / "entities").exists()
