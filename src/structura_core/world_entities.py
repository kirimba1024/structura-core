from math import floor

from amulet_nbt import CompoundTag, DoubleTag, IntTag, ListTag, StringTag

from .entity_positions import HANGING_ENTITIES, shift_entity
from .nbt_io import load_root
from .validation import vector


def dimension_id(value):
    value = str(value)
    return {"0": "minecraft:overworld", "-1": "minecraft:the_nether", "1": "minecraft:the_end"}.get(value, value)


def player_entities(path, data):
    local_player = data.get("Player")
    if local_player is not None:
        yield {**local_player, "id": StringTag("minecraft:player")}
    for file in sorted((path / "playerdata").glob("*.dat")):
        yield {**load_root(file), "id": StringTag("minecraft:player")}


def local_entities(payloads, dimension, origin, size):
    entities, notices, seen = [], [], set()
    shift = tuple(-value for value in origin)
    for payload in payloads:
        if dimension_id(payload.get("Dimension", dimension)) != dimension:
            continue
        try:
            position = vector(payload.get("Pos"), "entity position", integer=False)
        except ValueError:
            notices.append("Entity without a valid position was skipped")
            continue
        if not all(0 <= value - offset < limit for value, offset, limit in zip(position, origin, size)):
            continue
        identity = payload.get("UUID")
        if identity is not None:
            identity = str(identity)
            if identity in seen:
                continue
            seen.add(identity)
        block = tuple(floor(value) for value in position)
        if str(payload.get("id", "")) in HANGING_ENTITIES and all(axis in payload for axis in ("TileX", "TileY", "TileZ")):
            block = vector((payload[axis] for axis in ("TileX", "TileY", "TileZ")), "entity anchor")
        record = CompoundTag({
            "pos": ListTag([DoubleTag(value) for value in position]),
            "blockPos": ListTag([IntTag(value) for value in vector(block, "entity block position")]),
            "nbt": CompoundTag(dict(payload)),
        })
        entities.append(shift_entity(record, shift))
    return entities, tuple(dict.fromkeys(notices))
