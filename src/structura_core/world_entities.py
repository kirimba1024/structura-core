from dataclasses import dataclass
from math import floor
from typing import Optional
from uuid import UUID

from amulet_nbt import CompoundTag, DoubleTag, IntTag, ListTag, StringTag

from .entity_positions import HANGING_ENTITIES, shift_entity
from .nbt_io import load_root
from .validation import vector


@dataclass(frozen=True)
class EntityLocation:
    dimension: str
    storage: str
    chunk: Optional[tuple] = None
    file: Optional[str] = None


def dimension_id(value):
    value = str(value)
    return {"0": "minecraft:overworld", "-1": "minecraft:the_nether", "1": "minecraft:the_end"}.get(value, value)


def player_entities(path, data, *, located=False):
    local_player = data.get("Player")
    if local_player is not None:
        payload = {**local_player, "id": StringTag("minecraft:player")}
        location = EntityLocation(dimension_id(payload.get("Dimension", "minecraft:overworld")), "player", file="level.dat")
        yield (payload, location) if located else payload
    for file in sorted([*(path / "players" / "data").glob("*.dat"), *(path / "playerdata").glob("*.dat")]):
        payload = {**load_root(file), "id": StringTag("minecraft:player")}
        location = EntityLocation(dimension_id(payload.get("Dimension", "minecraft:overworld")), "player", file=file.relative_to(path).as_posix())
        yield (payload, location) if located else payload


def singleplayer(path, data):
    if "Player" in data:
        return data["Player"]
    reference = data.get("singleplayer_uuid")
    if reference is None:
        return {}
    try:
        if isinstance(reference, StringTag):
            identity = UUID(str(reference))
        else:
            parts = tuple(int(part) for part in reference)
            if len(parts) != 4:
                return {}
            identity = UUID(int=sum((part & 0xffffffff) << (96 - index * 32) for index, part in enumerate(parts)))
    except (ValueError, TypeError):
        return {}
    for directory in (path / "players" / "data", path / "playerdata"):
        file = directory / f"{identity}.dat"
        if file.is_file():
            return load_root(file)
    return {}


def local_entities(payloads, dimension, origin, size, *, located=False):
    entities, notices, seen, locations = [], [], set(), []
    shift = tuple(-value for value in origin)
    for item in payloads:
        payload, location = item if located else (item, None)
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
        locations.append(location)
    result = entities, tuple(dict.fromkeys(notices))
    return (*result, tuple(locations)) if located else result
