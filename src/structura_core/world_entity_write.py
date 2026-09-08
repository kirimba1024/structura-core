from copy import deepcopy
from dataclasses import dataclass
from math import floor
from pathlib import Path
from typing import Optional

from amulet_nbt import CompoundTag, IntArrayTag, IntTag, ListTag, StringTag, from_snbt

from .nbt_io import load_root
from .world_entities import EntityLocation
from .world_io import read_chunk


@dataclass(frozen=True)
class EntityPatch:
    before_location: Optional[EntityLocation]
    before: Optional[str]
    after_location: Optional[EntityLocation]
    after: Optional[str]


def _identity(payload):
    if "UUID" in payload:
        return payload["UUID"]
    if "UUIDMost" in payload and "UUIDLeast" in payload:
        return payload["UUIDMost"], payload["UUIDLeast"]
    return None


def _matching(records, payload):
    identity = _identity(payload)
    return [index for index, record in enumerate(records)
            if (_identity(record) == identity if identity is not None else record == payload)]


def _player_path(world, location):
    path = Path(location.file or "")
    if str(path) != "level.dat" and not (len(path.parts) == 2 and path.parts[0] == "playerdata" and path.suffix == ".dat"):
        raise ValueError("Invalid player file location")
    target = (world.path / path).resolve()
    if world.path not in target.parents:
        raise ValueError("Player file is outside the world")
    return target


def _write_player(world, stage, change):
    if change.before is None or change.after is None or change.before_location != change.after_location:
        raise ValueError("Player profiles cannot be created, deleted or moved between files")
    path = _player_path(world, change.before_location)
    staged = stage.file(path)
    root = load_root(staged)
    owner = root["Data"] if path.name == "level.dat" else None
    current = owner["Player"] if owner is not None else root
    before, after = from_snbt(change.before), from_snbt(change.after)
    normalized = deepcopy(current)
    normalized["id"] = StringTag("minecraft:player")
    if normalized == after:
        return
    if normalized != before:
        raise ValueError(f"World changed: player inventory or data in {path.name}")
    if "id" not in current:
        after.pop("id", None)
    if owner is not None:
        owner["Player"] = after
    else:
        root = after
    stage.write_file(path, root)
    identity = _identity(before)
    if path.name == "level.dat" and identity is not None:
        for player_file in (world.path / "playerdata").glob("*.dat"):
            other = load_root(player_file)
            if _identity(other) != identity:
                continue
            other["id"] = StringTag("minecraft:player")
            if other != before:
                raise ValueError("Local player and playerdata disagree; reload the world before editing this player")
            _write_player(world, stage, EntityPatch(EntityLocation(change.before_location.dimension, "player", file=str(player_file.relative_to(world.path))),
                                                  change.before,
                                                  EntityLocation(change.after_location.dimension, "player", file=str(player_file.relative_to(world.path))),
                                                  change.after))


def stage_entity_changes(world, stage, changes):
    chunks = {}
    dirty = set()

    def records(location, *, create=False):
        if location.dimension not in world.dimensions or location.storage not in ("region", "entities") or location.chunk is None:
            raise ValueError("Invalid entity chunk location")
        key = location.dimension, location.storage, location.chunk
        if key not in chunks:
            cx, cz = location.chunk
            directory = world.dimensions[location.dimension]
            if create and read_chunk(directory / "region", cx, cz) is None:
                raise ValueError(f"Entity destination chunk is absent at {cx}, {cz}")
            staged = stage.region(directory / location.storage, cx, cz)
            root = read_chunk(staged, cx, cz)
            if root is None:
                if not create or location.storage != "entities":
                    raise ValueError(f"World changed: entity chunk is absent at {cx}, {cz}")
                root = CompoundTag({"DataVersion": IntTag(world.data_version), "Position": IntArrayTag([cx, cz]), "Entities": ListTag()})
            body = root.get("Level", root) if location.storage == "region" else root
            body.setdefault("Entities", ListTag())
            chunks[key] = staged, root, body["Entities"]
        return key, chunks[key][2]

    parsed = []
    for change in changes:
        if (change.before_location or change.after_location).storage == "player":
            _write_player(world, stage, change)
            continue
        before = from_snbt(change.before) if change.before is not None else None
        after = from_snbt(change.after) if change.after is not None else None
        if after is not None:
            position = after.get("Pos")
            if position is None or len(position) != 3:
                raise ValueError("A world entity needs a Pos list")
            if change.after_location.chunk != (floor(float(position[0]) / 16), floor(float(position[2]) / 16)):
                raise ValueError("Entity position does not match its destination chunk")
        before_rows = records(change.before_location)[1] if before is not None else ()
        after_rows = records(change.after_location, create=True)[1] if after is not None else ()
        if before is not None:
            matches = _matching(before_rows, before)
            if not matches:
                if after is None or (len(_matching(after_rows, after)) == 1 and after_rows[_matching(after_rows, after)[0]] == after):
                    continue
                raise ValueError("World changed: selected entity is missing")
            if len(matches) != 1 or before_rows[matches[0]] != before:
                if change.before_location == change.after_location and len(matches) == 1 and before_rows[matches[0]] == after:
                    continue
                raise ValueError("World changed: selected entity data no longer matches")
        elif after is not None:
            matches = _matching(after_rows, after)
            if matches:
                if len(matches) == 1 and after_rows[matches[0]] == after:
                    continue
                raise ValueError("An entity with this UUID already exists at the destination")
        parsed.append((change, before, after))
    for change, before, after in parsed:
        if before is not None:
            key, rows = records(change.before_location)
            del rows[_matching(rows, before)[0]]
            dirty.add(key)
    for change, before, after in parsed:
        if after is not None:
            key, rows = records(change.after_location, create=True)
            if _matching(rows, after):
                raise ValueError("Duplicate entity at the destination")
            rows.append(after)
            dirty.add(key)
    for key in dirty:
        staged, root, _ = chunks[key]
        stage.write(staged, *key[2], root)
