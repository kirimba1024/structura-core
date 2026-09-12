import hashlib
import struct
import zlib

import numpy as np
import pytest
from amulet_nbt import ByteTag, CompoundTag, IntTag, ListTag, LongArrayTag, NamedTag, from_snbt

from structura_core.nbt import parse_state, write_root
from structura_core.world import JavaWorld, read_chunk


def region_file(directory, cx, cz, root, *, external=False):
    directory.mkdir(parents=True, exist_ok=True)
    data = zlib.compress(NamedTag(root).save_to(compressed=False))
    payload = b"\x82" if external else b"\x02" + data
    record = struct.pack(">I", len(payload)) + payload
    count = (len(record) + 4095) // 4096
    header = bytearray(8192)
    offset = 4 * ((cx % 32) + 32 * (cz % 32))
    header[offset:offset + 4] = struct.pack(">I", (2 << 8) | count)
    path = directory / f"r.{cx // 32}.{cz // 32}.mca"
    path.write_bytes(header + record + b"\0" * (count * 4096 - len(record)))
    if external:
        (directory / f"c.{cx}.{cz}.mcc").write_bytes(data)
    return path


@pytest.fixture(params=[2230, 2586, 3955])
def world(tmp_path, request):
    pytest.importorskip("amulet")
    from amulet.utils.world_utils import encode_long_array

    version = request.param
    level = from_snbt('''{Data: {LevelName:"Test", SpawnX:-1, SpawnY:0, SpawnZ:-1,
        Player:{Pos:[-2.5d,0d,-2.5d], Rotation:[90f,0f], Dimension:0, UUID:[I;1,2,3,4]}}}''')
    level["Data"]["DataVersion"] = IntTag(version)
    write_root(level, tmp_path / "level.dat")
    indices = np.zeros(4096, dtype=np.uint16)
    indices[-1] = 1
    section = CompoundTag({"Y": ByteTag(-1), "block_states": CompoundTag({
        "palette": ListTag([parse_state("minecraft:air"), parse_state("minecraft:stone")]),
        "data": LongArrayTag(encode_long_array(indices, bits_per_entry=4, dense=version < 2529)),
    })})
    chunk = CompoundTag({"DataVersion": IntTag(version), "xPos": IntTag(-1), "zPos": IntTag(-1),
                         "sections": ListTag([section])})
    if version < 2844:
        states = section.pop("block_states")
        section["Palette"], section["BlockStates"] = states["palette"], states["data"]
        chunk["Sections"] = chunk.pop("sections")
        chunk = CompoundTag({"DataVersion": IntTag(version), "Level": chunk})
    region_file(tmp_path / "region", -1, -1, chunk)
    entities = from_snbt('''{DataVersion:3955, Position:[I;-1,-1], Entities:[
        {id:"minecraft:sheep",Pos:[-1.5d,0d,-1.5d],Rotation:[45f,0f],Color:4b,UUID:[I;4,3,2,1]},
        {id:"minecraft:pig",Pos:[-0.5d,0d,-0.5d],Age:-100,UUID:[I;7,8,9,0]}]}''')
    region_file(tmp_path / "entities", -1, -1, entities, external=True)
    return JavaWorld(tmp_path)


def test_world_reads_negative_sections_entities_and_player_without_writes(world):
    paths = list(world.path.rglob("*"))
    before = {p: hashlib.sha256(p.read_bytes()).digest() for p in paths if p.is_file()}
    region = world.read_region((-0.5, 0, -0.5), radius=0, vertical_radius=16)
    assert region.loaded == {(-1, -1)}
    assert not region.missing
    source = region.structure
    local = tuple(-1 - o for o in source.source_origin)
    assert source.name_at(local) == "minecraft:stone"
    assert len(source.present) == 1
    entities = {str(e["nbt"]["id"]): e for e in source.entities}
    assert set(entities) == {"minecraft:sheep", "minecraft:pig", "minecraft:player"}
    assert int(entities["minecraft:sheep"]["nbt"]["Color"]) == 4
    assert int(entities["minecraft:pig"]["nbt"]["Age"]) == -100
    assert tuple(float(v) for v in entities["minecraft:player"]["pos"]) == (13.5, 16, 13.5)
    assert all(entity["nbt"]["Pos"] == entity["pos"] for entity in source.entities)
    assert before == {p: hashlib.sha256(p.read_bytes()).digest() for p in before}


def test_world_refresh_reads_new_data_and_missing_is_explicit(world):
    region = world.read_region(radius=1, vertical_radius=16)
    assert len(region.loaded) == 1 and len(region.missing) == 8
    chunk = read_chunk(world.path / "region", -1, -1)
    body = chunk.get("Level", chunk)
    section = body.get("sections", body.get("Sections"))[0]
    palette = section["block_states"]["palette"] if "block_states" in section else section["Palette"]
    palette[1] = parse_state("minecraft:gold_block")
    region_file(world.path / "region", -1, -1, chunk)
    refreshed = world.read_region(radius=0, vertical_radius=16)
    assert "minecraft:gold_block" in refreshed.structure.palette
    assert "minecraft:gold_block" not in region.structure.palette
    assert not world.read_region(radius=0, vertical_radius=16, include_entities=False).structure.entities


def test_full_columns_include_saved_top_and_bottom_independent_of_camera_height(world):
    from copy import deepcopy

    root = read_chunk(world.path / "region", -1, -1)
    body = root.get("Level", root)
    sections = body.get("sections", body.get("Sections"))
    for height in (-4, 19):
        section = deepcopy(sections[0])
        section["Y"] = ByteTag(height)
        sections.append(section)
    region_file(world.path / "region", -1, -1, root)
    for camera_y in (-200, 500):
        source = world.read_region((-1, camera_y, -1), radius=0, vertical_radius=None).structure
        assert source.source_origin == (-16, -64, -16)
        assert source.size == (16, 384, 16)
        assert {position for position in source.present} == {(15, 15, 15), (15, 63, 15), (15, 383, 15)}
    with pytest.raises(ValueError, match="volume"):
        world.read_region(radius=0, vertical_radius=None, max_cells=32_768)


def test_world_rejects_invalid_ranges_and_truncated_chunks(world):
    with pytest.raises(ValueError, match="Radius"):
        world.read_region(radius=True)
    with pytest.raises(ValueError, match="volume"):
        world.read_region(radius=8, vertical_radius=192)
    with pytest.raises(ValueError, match="dimension"):
        world.read_region(dimension="../../outside")
    path = world.path / "region/r.-1.-1.mca"
    path.write_bytes(path.read_bytes()[:8200])
    with pytest.raises(ValueError, match="Truncated"):
        world.read_region(radius=0, vertical_radius=16)


@pytest.mark.parametrize("kwargs", [
    {"max_blocks": True}, {"max_blocks": 0}, {"max_blocks": -1}, {"max_blocks": 1.5},
    {"center": (True, 0, 0)}, {"center": ("0", 0, 0)}, {"center": (0, float("nan"), 0)},
    {"center": (1e100, 0, 0)},
])
def test_invalid_world_selection_arguments_fail_explicitly(world, kwargs):
    with pytest.raises(ValueError):
        world.read_region(radius=0, vertical_radius=16, **kwargs)


def test_hanging_entities_keep_local_positions_when_saved(world, tmp_path):
    from structura_core import Structure, save_structure

    entities = from_snbt('''{Entities:[{id:"minecraft:item_frame",Pos:[-1.5d,0d,-1.5d],
        TileX:-2,TileY:0,TileZ:-2,Item:{id:"minecraft:stone",Count:1b}}]}''')
    region_file(world.path / "entities", -1, -1, entities)
    source = world.read_region(radius=0, vertical_radius=16).structure
    output = tmp_path / "export.nbt"
    save_structure(source, output, source.size)
    frame = next(entity for entity in Structure(output).entities if str(entity["nbt"]["id"]) == "minecraft:item_frame")

    assert tuple(float(value) for value in frame["pos"]) == (14.5, 16, 14.5)
    assert frame["nbt"]["Pos"] == frame["pos"]
    assert tuple(int(frame["nbt"][axis]) for axis in ("TileX", "TileY", "TileZ")) == (14, 16, 14)
    assert frame["nbt"]["Item"] == entities["Entities"][0]["Item"]


def test_duplicate_sections_are_rejected_instead_of_silently_overwriting(world):
    from copy import deepcopy

    root = read_chunk(world.path / "region", -1, -1)
    body = root.get("Level", root)
    sections = body.get("sections", body.get("Sections"))
    sections.append(deepcopy(sections[0]))
    region_file(world.path / "region", -1, -1, root)

    with pytest.raises(ValueError, match="Duplicate section"):
        world.read_region(radius=0, vertical_radius=16)


def test_world_filters_dimensions_deduplicates_players_and_reports_invalid_entities(world):
    player_path = world.path / "playerdata"
    player_path.mkdir()
    write_root(world.data["Player"], player_path / "same-player.dat")
    entities = from_snbt('''{Entities:[
        {id:"minecraft:pig",Dimension:-1,Pos:[-1d,0d,-1d]},
        {id:"minecraft:sheep"},{id:"minecraft:sheep",Pos:[0d]},
        {id:"minecraft:pig",Pos:[1000d,0d,1000d]}]}''')
    region_file(world.path / "entities", -1, -1, entities)
    region = world.read_region(radius=0, vertical_radius=16)

    assert [str(entity["nbt"]["id"]) for entity in region.structure.entities] == ["minecraft:player"]
    assert len(region.notices) == 1 and "position" in region.notices[0]
