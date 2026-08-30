"""Validated reader and writer for vanilla Java Structure NBT files."""

from pathlib import Path
from typing import Iterable, Mapping, Tuple, Union

from amulet_nbt import (
    CompoundTag,
    DoubleTag,
    IntTag,
    ListTag,
    NamedTag,
    StringTag,
    load as load_nbt,
)

AIR_NAMES = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})
Position = Tuple[int, int, int]
State = Union[int, str]


def state_key(entry: Mapping) -> str:
    """Return a stable ``namespace:block[prop=value,...]`` palette key."""
    name = str(entry["Name"])
    properties = entry.get("Properties")
    if not properties:
        return name
    values = ",".join(f"{key}={value}" for key, value in sorted(properties.items()))
    return f"{name}[{values}]"


def parse_state(value: str) -> CompoundTag:
    """Parse the compact state syntax accepted by generation helpers."""
    name, properties = value, None
    if "[" in value:
        if not value.endswith("]"):
            raise ValueError(f"invalid block state: {value!r}")
        name, raw = value[:-1].split("[", 1)
        parsed = {}
        for pair in raw.split(","):
            if not pair or "=" not in pair:
                raise ValueError(f"invalid block state property: {value!r}")
            key, item = pair.split("=", 1)
            if not key or not item or key in parsed:
                raise ValueError(f"invalid block state property: {value!r}")
            parsed[key] = StringTag(item)
        properties = CompoundTag(parsed)
    namespace, separator, block_name = name.partition(":")
    if not separator or not namespace or not block_name:
        raise ValueError(f"block state needs a namespace: {value!r}")
    entry = CompoundTag({"Name": StringTag(name)})
    if properties:
        entry["Properties"] = properties
    return entry


class Structure:
    """In-memory Structure NBT with eagerly checked structural invariants."""

    def __init__(self, path):
        self.path = Path(path)
        root = load_nbt(str(self.path), compressed=True).compound
        self.data_version = int(root["DataVersion"].py_data)
        self.size = tuple(int(value.py_data) for value in root["size"])
        self.palette_raw = list(root["palette"])
        self.palette = [str(entry["Name"]) for entry in self.palette_raw]
        self.entities = list(root.get("entities", []))
        self.present = {}
        self.block_nbt = {}
        for block in root["blocks"]:
            pos = tuple(int(value.py_data) for value in block["pos"])
            if pos in self.present:
                raise ValueError(f"duplicate block position {pos} in {self.path}")
            self.present[pos] = int(block["state"].py_data)
            if "nbt" in block:
                self.block_nbt[pos] = block["nbt"]
        self.validate()

    def validate(self):
        if len(self.size) != 3 or any(value <= 0 for value in self.size):
            raise ValueError(f"invalid structure size {self.size} in {self.path}")
        for pos, index in self.present.items():
            if len(pos) != 3 or not all(0 <= value < limit for value, limit in zip(pos, self.size)):
                raise ValueError(f"block {pos} is outside {self.size} in {self.path}")
            if not 0 <= index < len(self.palette):
                raise ValueError(f"palette index {index} is invalid in {self.path}")
        dangling = self.block_nbt.keys() - self.present.keys()
        if dangling:
            raise ValueError(f"block entities without blocks in {self.path}: {sorted(dangling)[:3]}")

    def name_at(self, pos):
        index = self.present.get(pos)
        return None if index is None else self.palette[index]

    def is_air(self, pos):
        return self.name_at(pos) in AIR_NAMES

    def solid_positions(self):
        return {pos for pos, index in self.present.items() if self.palette[index] not in AIR_NAMES}


def save_structure(
    src,
    dst,
    size,
    shift=(0, 0, 0),
    additions: Iterable[Tuple[Position, State]] = (),
    replacements: Iterable[Tuple[Position, State]] = (),
):
    """Save shifted source plus safe additions and explicit replacements."""
    size = tuple(int(value) for value in size)
    shift = tuple(int(value) for value in shift)
    if len(size) != 3 or any(value <= 0 for value in size):
        raise ValueError(f"invalid output size: {size}")

    palette = ListTag([CompoundTag(dict(item.items())) for item in src.palette_raw])
    palette_index = {state_key(entry): index for index, entry in enumerate(src.palette_raw)}

    def index_for(state):
        if isinstance(state, int):
            if not 0 <= state < len(palette):
                raise ValueError(f"palette index out of range: {state}")
            return state
        if state not in palette_index:
            palette_index[state] = len(palette)
            palette.append(parse_state(state))
        return palette_index[state]

    def collect(entries, label):
        result = {}
        for raw_pos, state in entries:
            pos = tuple(int(value) for value in raw_pos)
            if pos in result and result[pos] != state:
                raise ValueError(
                    f"conflicting {label} states at {pos}: "
                    f"{result[pos]!r} and {state!r}"
                )
            result.setdefault(pos, state)
        return result

    addition_map = collect(additions, "addition")
    replacement_map = collect(replacements, "replacement")
    for pos in addition_map.keys() & replacement_map.keys():
        if addition_map[pos] != replacement_map[pos]:
            raise ValueError(
                f"addition and replacement disagree at {pos}: "
                f"{addition_map[pos]!r} and {replacement_map[pos]!r}"
            )

    def require_bounds(pos):
        if len(pos) != 3 or not all(0 <= value < limit for value, limit in zip(pos, size)):
            raise ValueError(f"output block {pos} is outside {size}")

    blocks = ListTag()
    written = set()
    for pos, index in src.present.items():
        target = tuple(value + delta for value, delta in zip(pos, shift))
        require_bounds(target)
        if target in replacement_map or (
            target in addition_map and src.palette[index] in AIR_NAMES
        ):
            continue
        block = CompoundTag({
            "pos": ListTag([IntTag(value) for value in target]),
            "state": IntTag(index),
        })
        if pos in src.block_nbt:
            block["nbt"] = CompoundTag(dict(src.block_nbt[pos].items()))
        blocks.append(block)
        written.add(target)

    for pos, state in (*replacement_map.items(), *addition_map.items()):
        require_bounds(pos)
        if pos in written:
            continue
        blocks.append(CompoundTag({
            "pos": ListTag([IntTag(value) for value in pos]),
            "state": IntTag(index_for(state)),
        }))
        written.add(pos)

    entities = ListTag()
    for raw in src.entities:
        entity = CompoundTag(dict(raw.items()))
        if "blockPos" in entity:
            entity["blockPos"] = ListTag([
                IntTag(int(value.py_data) + delta)
                for value, delta in zip(entity["blockPos"], shift)
            ])
        if "pos" in entity:
            entity["pos"] = ListTag([
                DoubleTag(float(value.py_data) + delta)
                for value, delta in zip(entity["pos"], shift)
            ])
        entities.append(entity)

    root = CompoundTag({
        "DataVersion": IntTag(src.data_version),
        "size": ListTag([IntTag(value) for value in size]),
        "palette": palette,
        "blocks": blocks,
        "entities": entities,
    })
    destination = Path(dst)
    destination.parent.mkdir(parents=True, exist_ok=True)
    NamedTag(root, "").save_to(str(destination))
    return len(blocks)
