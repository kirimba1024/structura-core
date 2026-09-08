from copy import deepcopy

from amulet_nbt import DoubleTag, IntTag, ListTag

from .validation import int32, vector

HANGING_ENTITIES = frozenset({
    "minecraft:painting", "minecraft:item_frame", "minecraft:glow_item_frame",
})


def block_entity_at(payload, position):
    result = deepcopy(payload)
    for axis, coordinate in zip("xyz", position):
        if axis in result:
            result[axis] = IntTag(int32(coordinate, f"block entity {axis}"))
    return result


def shift_entity(record, shift):
    result = deepcopy(record)
    position = vector(record["pos"], "entity position", integer=False)
    block = vector(record["blockPos"], "entity block position")
    result["pos"] = ListTag([DoubleTag(v + delta) for v, delta in zip(position, shift)])
    result["blockPos"] = ListTag([
        IntTag(int32(v + delta, "shifted entity block position")) for v, delta in zip(block, shift)
    ])
    if any(shift):
        nbt = result["nbt"]
        _shift_payload(nbt, shift)
        if "Pos" in nbt:
            nbt["Pos"] = deepcopy(result["pos"])
    return result


def _shift_payload(nbt, shift):
    if "Pos" in nbt:
        position = vector(nbt["Pos"], "entity position", integer=False)
        nbt["Pos"] = ListTag([DoubleTag(v + delta) for v, delta in zip(position, shift)])
    if str(nbt.get("id", "")) in HANGING_ENTITIES:
        for axis, delta in zip(("TileX", "TileY", "TileZ"), shift):
            if axis in nbt:
                nbt[axis] = IntTag(int32(int32(nbt[axis], axis) + delta, f"shifted entity {axis}"))
    for passenger in nbt.get("Passengers", ()):
        _shift_payload(passenger, shift)
