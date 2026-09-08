"""Native Sponge documents and normalized block/entity views."""

import math
from copy import deepcopy
from pathlib import Path
from typing import Optional, Tuple

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

from .blockstates import parse_state
from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES, check_volume
from .nbt_io import PathInput, load_root, write_root
from .structure import Structure
from .validation import compound, compound_list, int32, vector


class UnsupportedSchematicVersion(ValueError):
    def __init__(self, version):
        self.version = version
        super().__init__(f"unsupported Sponge version {version}; expected 1, 2 or 3")


class MissingSchematicDataVersion(ValueError):
    pass


def _palette(value, label):
    entries = compound(value, label)
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
        result = deepcopy(compound(record.get("Data", CompoundTag()), f"{label}.Data"))
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
        document = compound(self._document, "Schematic document")
        self.root = compound(document.get("Schematic", document), "Schematic")
        self.version = int32(self.root.get("Version"), "Schematic Version")
        if self.version not in (1, 2, 3):
            raise UnsupportedSchematicVersion(self.version)
        self.data_version = (None if self.version == 1 and "DataVersion" not in self.root else
                             int32(self.root.get("DataVersion"), "Schematic DataVersion"))
        sizes = [self.root.get(name) for name in ("Width", "Height", "Length")]
        if any(not isinstance(value, ShortTag) or int(value) == 0 for value in sizes):
            raise ValueError("Schematic dimensions must be nonzero unsigned shorts")
        self.size = tuple(int(value) & 65535 for value in sizes)
        offset = self.root.get("Offset", IntArrayTag([0, 0, 0]))
        if not isinstance(offset, IntArrayTag):
            raise ValueError("Schematic Offset must be an integer array")
        self.offset = vector(offset, "Schematic Offset")
        compound(self.root.get("Metadata", CompoundTag()), "Schematic Metadata")

    def save(self, path: PathInput) -> Path:
        """Save the native document atomically without cross-format data loss."""
        self._read_header()
        write_root(self._document, path, name="Schematic" if self.version < 3 and self.root is self._document else "")
        return Path(path)

    def to_structure(self, *, max_blocks: int = DEFAULT_MAX_BLOCKS,
                     data_version: Optional[int] = None) -> Structure:
        """Normalize local cells/entities; offset and biomes remain on this document."""
        self._read_header()
        if data_version is not None:
            data_version = int32(data_version, "source DataVersion")
            if self.data_version is not None and data_version != self.data_version:
                raise ValueError("source DataVersion disagrees with the document")
        else:
            data_version = self.data_version
        if data_version is None:
            raise MissingSchematicDataVersion("Sponge v1 has no DataVersion; supply the source data_version explicitly")
        volume = math.prod(self.size)
        check_volume(volume, max_blocks)
        blocks = self.root if self.version < 3 else self.root.get("Blocks")
        if blocks is not None:
            compound(blocks, "Blocks")
        palette = _palette(blocks.get("Palette"), "block Palette") if blocks is not None else {}
        remap = {index: i for i, index in enumerate(palette)}
        states = [parse_state(state if ":" in state.split("[", 1)[0] else f"minecraft:{state}")
                  for state in palette.values()]
        result = Structure.from_root(CompoundTag({
            "DataVersion": IntTag(data_version), "size": _list(self.size),
            "palette": ListTag(states), "blocks": ListTag(), "entities": ListTag(),
        }))
        sx, sy, sz = self.size
        if blocks is not None:
            data = blocks.get("BlockData" if self.version < 3 else "Data")
            for index, state in enumerate(_varints(data, volume, palette, "BlockData")):
                y, remainder = divmod(index, sx * sz)
                z, x = divmod(remainder, sx)
                result.present[(x, y, z)] = remap[state]
            entity_key = "TileEntities" if self.version == 1 else "BlockEntities"
            for record in compound_list(blocks.get(entity_key, ListTag()), entity_key):
                if not isinstance(record.get("Pos"), IntArrayTag):
                    raise ValueError("block entity Pos must be an integer array")
                pos = vector(record["Pos"], "block entity Pos")
                if pos not in result.present or pos in result.block_nbt:
                    raise ValueError(f"duplicate or out-of-bounds block entity at {pos}")
                nbt = _payload(record, self.version, "block entity")
                nbt.update({axis: IntTag(value) for axis, value in zip("xyz", pos)})
                result.block_nbt[pos] = nbt
        for record in compound_list(self.root.get("Entities", ListTag()), "Entities"):
            pos = vector(record.get("Pos"), "entity Pos", integer=False)
            nbt = _payload(record, self.version, "entity")
            nbt["Pos"] = _list(pos, DoubleTag)
            result.entities.append(CompoundTag({
                "pos": _list(pos, DoubleTag),
                "blockPos": _list(vector(tuple(math.floor(v) for v in pos), "entity block position")),
                "nbt": nbt,
            }))
        self._validate_biomes(volume)
        result.path = self.path
        result.source_origin = self.offset
        result.validate()
        return result

    def _validate_biomes(self, volume):
        if self.version < 3:
            if "BiomeData" not in self.root:
                return
            palette = _palette(self.root.get("BiomePalette"), "BiomePalette")
            data, count = self.root["BiomeData"], self.size[0] * self.size[2]
        else:
            if "Biomes" not in self.root:
                return
            biomes = compound(self.root["Biomes"], "Biomes")
            palette = _palette(biomes.get("Palette"), "Biome Palette")
            data, count = biomes.get("Data"), volume
        for value in palette.values():
            parse_state(value if ":" in value else f"minecraft:{value}")
        for _ in _varints(data, count, palette, "BiomeData"):
            pass
