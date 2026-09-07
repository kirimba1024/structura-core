"""Native Sponge Schematic v2/v3 documents and normalized block/entity views."""

import math
from copy import deepcopy
from pathlib import Path
from typing import Tuple

from .nbt import PathInput

from amulet_nbt import (
    ByteArrayTag,
    CompoundTag,
    DoubleTag,
    IntArrayTag,
    IntTag,
    ListTag,
    ShortTag,
    StringTag,
)

from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES, check_volume
from .nbt import Structure, _integer, _vector, load_root, parse_state, write_root


class UnsupportedSchematicVersion(ValueError):
    def __init__(self, version):
        self.version = version
        super().__init__(f"unsupported Sponge version {version}; expected 2 or 3")


def _compound(value, label):
    if not isinstance(value, CompoundTag):
        raise ValueError(f"{label} must be a compound")
    return value


def _records(value, label):
    if not isinstance(value, ListTag) or any(not isinstance(entry, CompoundTag) for entry in value):
        raise ValueError(f"{label} must be a list of compounds")
    return value


def _palette(value, label):
    entries = _compound(value, label)
    result = {}
    for state, tag in entries.items():
        if not isinstance(tag, IntTag) or int(tag) < 0 or int(tag) in result:
            raise ValueError(f"{label} needs unique nonnegative integer indices")
        result[int(tag)] = state
    if not result:
        raise ValueError(f"{label} must not be empty")
    return result


def _varints(data, count, palette, label):
    if not isinstance(data, ByteArrayTag):
        raise ValueError(f"{label} must be a byte array")
    value = shift = decoded = 0
    for raw in data:
        byte = int(raw) & 255
        if shift == 28 and byte > 7:
            raise ValueError(f"{label} contains an overflowing varint")
        value |= (byte & 127) << shift
        if byte & 128:
            shift += 7
            continue
        if decoded >= count:
            raise ValueError(f"{label} contains more than {count} cells")
        if value not in palette:
            raise ValueError(f"{label} references unknown palette index {value}")
        yield value
        decoded += 1
        value = shift = 0
    if shift or decoded != count:
        raise ValueError(f"{label} is truncated; expected {count} cells, got {decoded}")


def _payload(record, version, label):
    identifier = record.get("Id")
    if not isinstance(identifier, StringTag) or not str(identifier):
        raise ValueError(f"{label} requires a nonempty string Id")
    if version == 3:
        result = deepcopy(_compound(record.get("Data", CompoundTag()), f"{label}.Data"))
    else:
        result = deepcopy(record)
        result.pop("Id", None)
        result.pop("Pos", None)
    result["id"] = deepcopy(identifier)
    return result


def _list(values, tag=IntTag):
    return ListTag([tag(value) for value in values])


class Schematic:
    """Retain native NBT, including offset, biomes, metadata and unknown fields."""

    size: Tuple[int, int, int]
    offset: Tuple[int, int, int]

    def __init__(self, path: PathInput, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> None:
        self.path = Path(path)
        self._document = load_root(path, max_nbt_bytes=max_nbt_bytes)
        self._read_header()

    @classmethod
    def from_root(cls, root: CompoundTag) -> "Schematic":
        result = cls.__new__(cls)
        result.path = Path("<memory>")
        result._document = deepcopy(root)
        result._read_header()
        return result

    def _read_header(self):
        document = _compound(self._document, "Schematic document")
        self.root = _compound(document.get("Schematic", document), "Schematic")
        self.version = _integer(self.root.get("Version"), "Schematic Version")
        if self.version not in (2, 3):
            raise UnsupportedSchematicVersion(self.version)
        self.data_version = _integer(self.root.get("DataVersion"), "Schematic DataVersion")
        sizes = [self.root.get(name) for name in ("Width", "Height", "Length")]
        if any(not isinstance(value, ShortTag) or int(value) == 0 for value in sizes):
            raise ValueError("Schematic dimensions must be nonzero unsigned shorts")
        self.size = tuple(int(value) & 65535 for value in sizes)
        offset = self.root.get("Offset", IntArrayTag([0, 0, 0]))
        if not isinstance(offset, IntArrayTag):
            raise ValueError("Schematic Offset must be an integer array")
        self.offset = _vector(offset, "Schematic Offset")
        _compound(self.root.get("Metadata", CompoundTag()), "Schematic Metadata")

    def save(self, path: PathInput) -> Path:
        """Save the native document atomically without cross-format data loss."""
        self._read_header()
        write_root(self._document, path, name="Schematic" if self.version == 2 and self.root is self._document else "")
        return Path(path)

    def to_structure(self, *, max_blocks: int = DEFAULT_MAX_BLOCKS) -> Structure:
        """Normalize local cells/entities; offset and biomes remain on this document."""
        self._read_header()
        volume = math.prod(self.size)
        check_volume(volume, max_blocks)
        blocks = self.root if self.version == 2 else self.root.get("Blocks")
        if blocks is not None:
            _compound(blocks, "Blocks")
        palette = _palette(blocks.get("Palette"), "block Palette") if blocks is not None else {}
        remap = {index: i for i, index in enumerate(palette)}
        states = [parse_state(state if ":" in state.split("[", 1)[0] else f"minecraft:{state}")
                  for state in palette.values()]
        result = Structure.from_root(CompoundTag({
            "DataVersion": IntTag(self.data_version), "size": _list(self.size),
            "palette": ListTag(states), "blocks": ListTag(), "entities": ListTag(),
        }))
        sx, sy, sz = self.size
        if blocks is not None:
            data = blocks.get("BlockData" if self.version == 2 else "Data")
            for index, state in enumerate(_varints(data, volume, palette, "BlockData")):
                y, remainder = divmod(index, sx * sz)
                z, x = divmod(remainder, sx)
                result.present[(x, y, z)] = remap[state]
            for record in _records(blocks.get("BlockEntities", ListTag()), "BlockEntities"):
                if not isinstance(record.get("Pos"), IntArrayTag):
                    raise ValueError("block entity Pos must be an integer array")
                pos = _vector(record["Pos"], "block entity Pos")
                if pos not in result.present or pos in result.block_nbt:
                    raise ValueError(f"duplicate or out-of-bounds block entity at {pos}")
                nbt = _payload(record, self.version, "block entity")
                nbt.update({axis: IntTag(value) for axis, value in zip("xyz", pos)})
                result.block_nbt[pos] = nbt
        for record in _records(self.root.get("Entities", ListTag()), "Entities"):
            pos = _vector(record.get("Pos"), "entity Pos", integer=False)
            nbt = _payload(record, self.version, "entity")
            nbt["Pos"] = _list(pos, DoubleTag)
            result.entities.append(CompoundTag({
                "pos": _list(pos, DoubleTag),
                "blockPos": _list(_vector(tuple(math.floor(v) for v in pos), "entity block position")),
                "nbt": nbt,
            }))
        self._validate_biomes(volume)
        result.source_origin = self.offset
        result.validate()
        return result

    def _validate_biomes(self, volume):
        if self.version == 2:
            if "BiomeData" not in self.root:
                return
            palette = _palette(self.root.get("BiomePalette"), "BiomePalette")
            data, count = self.root["BiomeData"], self.size[0] * self.size[2]
        else:
            if "Biomes" not in self.root:
                return
            biomes = _compound(self.root["Biomes"], "Biomes")
            palette = _palette(biomes.get("Palette"), "Biome Palette")
            data, count = biomes.get("Data"), volume
        for value in palette.values():
            parse_state(value if ":" in value else f"minecraft:{value}")
        for _ in _varints(data, count, palette, "BiomeData"):
            pass
