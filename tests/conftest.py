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
