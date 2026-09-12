from collections import Counter

import pytest
from amulet_nbt import ByteArrayTag, CompoundTag, DoubleTag, FloatTag, IntArrayTag, ListTag, LongArrayTag


@pytest.fixture
def nbt_snapshot():
    def snapshot(tag):
        if isinstance(tag, CompoundTag):
            value = tuple(sorted((key, snapshot(child)) for key, child in tag.items()))
        elif isinstance(tag, ListTag):
            value = tuple(snapshot(child) for child in tag)
        elif isinstance(tag, (ByteArrayTag, IntArrayTag, LongArrayTag)):
            value = tuple(int(item) for item in tag.np_array)
        elif isinstance(tag, (FloatTag, DoubleTag)):
            value = float(tag).hex()
        else:
            value = tag.py_data
        return tag.tag_id, value

    return snapshot


@pytest.fixture
def structure_snapshot(nbt_snapshot):
    def snapshot(src):
        states = [(str(entry["Name"]), tuple(sorted(
            (key, str(value)) for key, value in entry.get("Properties", {}).items()
        ))) for entry in src.palette_raw]
        return {
            "size": src.size,
            "data_version": src.data_version,
            "origin": getattr(src, "source_origin", (0, 0, 0)),
            "blocks": {pos: (states[index], nbt_snapshot(src.block_nbt[pos]) if pos in src.block_nbt else None)
                       for pos, index in src.present.items()},
            "entities": Counter(nbt_snapshot(record) for record in src.entities),
        }

    return snapshot


@pytest.fixture
def make_structure():
    from amulet_nbt import IntTag

    from structura_core import Structure, parse_state

    def make(blocks=(), *, size=(5, 3, 3), palette=("minecraft:stone", "minecraft:air")):
        return Structure.from_root(CompoundTag({
            "DataVersion": IntTag(3955),
            "size": ListTag([IntTag(value) for value in size]),
            "palette": ListTag([parse_state(state) for state in palette]),
            "blocks": ListTag([
                CompoundTag({"pos": ListTag([IntTag(value) for value in pos]), "state": IntTag(state)})
                for pos, state in blocks
            ]),
            "entities": ListTag(),
        }))

    return make


@pytest.fixture
def editable_world(tmp_path):
    from amulet_nbt import from_snbt
    from structura_core.nbt import write_root
    from structura_core.world import JavaWorld
    from test_world import region_file

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
