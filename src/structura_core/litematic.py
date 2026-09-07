"""Native Litematic v5–v7 I/O; no Minecraft version translation.

Blocks and tile entities are relative to a region's minimum corner. Entity
positions are relative to its signed origin. Packed states use a continuous
bit stream (including entries crossing a 64-bit boundary), with X fastest.
"""

import math
from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .nbt import PathInput

from amulet_nbt import (
    CompoundTag,
    DoubleTag,
    IntTag,
    ListTag,
    LongArrayTag,
    LongTag,
    StringTag,
)

from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES
from .limits import check_volume as _check_volume
from .nbt import (
    AIR_NAMES,
    Structure,
    _integer,
    _validate_palette,
    _vector,
    load_root,
    parse_state,
    write_root,
)

_WORD_MASK = (1 << 64) - 1


def _xyz(tag, label):
    if not isinstance(tag, CompoundTag) or not {"x", "y", "z"} <= tag.keys():
        raise ValueError(f"{label} must be an x/y/z compound")
    return _vector((tag[axis] for axis in "xyz"), label)


def _position(values):
    return CompoundTag({axis: IntTag(value) for axis, value in zip("xyz", values)})


def _list(values, tag=IntTag):
    return ListTag([tag(value) for value in values])


def _compounds(tag, label):
    if not isinstance(tag, ListTag) or any(not isinstance(v, CompoundTag) for v in tag):
        raise ValueError(f"{label} must be a list of compounds")
    return tag


def _require_id(nbt, label):
    if not isinstance(nbt.get("id"), StringTag) or not str(nbt["id"]):
        raise ValueError(f"{label} needs a nonempty string id for Litematic export")


def _unpack(words, count, palette_size):
    bits = max(2, (palette_size - 1).bit_length())
    if not isinstance(words, LongArrayTag) or len(words) != (count * bits + 63) // 64:
        raise ValueError("invalid Litematic BlockStates length or tag type")
    mask = (1 << bits) - 1
    for index in range(count):
        word, offset = divmod(index * bits, 64)
        value = (int(words[word]) & _WORD_MASK) >> offset
        if offset + bits > 64:
            value |= (int(words[word + 1]) & _WORD_MASK) << (64 - offset)
        value &= mask
        if value >= palette_size:
            raise ValueError(f"invalid Litematic palette index {value} at cell {index}")
        yield value


def _pack(values, count, palette_size):
    bits = max(2, (palette_size - 1).bit_length())
    words = [0] * ((count * bits + 63) // 64)
    for index, value in enumerate(values):
        word, offset = divmod(index * bits, 64)
        words[word] |= (value << offset) & _WORD_MASK
        if offset + bits > 64:
            words[word + 1] |= value >> (64 - offset)
    return LongArrayTag([v if v < (1 << 63) else v - (1 << 64) for v in words])


@dataclass(frozen=True)
class _Region:
    name: str
    nbt: CompoundTag
    position: tuple
    size: tuple
    minimum: tuple

    @classmethod
    def read(cls, name, nbt):
        if not isinstance(nbt, CompoundTag):
            raise ValueError(f"invalid Litematic region {name!r}")
        position = _xyz(nbt.get("Position"), "region Position")
        signed = _xyz(nbt.get("Size"), "region Size")
        if any(v == 0 for v in signed):
            raise ValueError("Litematic region dimensions must be nonzero")
        size = tuple(abs(v) for v in signed)
        minimum = tuple(p + min(0, s + 1) for p, s in zip(position, signed))
        return cls(name, nbt, position, size, minimum)


def _merge_region(result, region, origin, palette_lookup):
    palette = _compounds(region.nbt.get("BlockStatePalette"), "BlockStatePalette")
    if not palette:
        raise ValueError(f"empty Litematic palette in region {region.name!r}")
    _validate_palette(palette, region.name)
    remap = []
    for block in palette:
        key = block.to_snbt()
        if key not in palette_lookup:
            palette_lookup[key] = len(result.palette_raw)
            result.palette_raw.append(deepcopy(block))
        remap.append(palette_lookup[key])
    delta = tuple(v - o for v, o in zip(region.minimum, origin))
    sx, sy, sz = region.size
    for index, state in enumerate(_unpack(region.nbt.get("BlockStates"), sx * sy * sz, len(palette))):
        y, rem = divmod(index, sx * sz)
        z, x = divmod(rem, sx)
        pos = tuple(v + d for v, d in zip((x, y, z), delta))
        if pos in result.present:
            raise ValueError(f"overlapping Litematic regions at {pos}; choose a named region")
        result.present[pos] = remap[state]
    for raw in _compounds(region.nbt.get("TileEntities", ListTag()), "TileEntities"):
        local = _xyz(raw, "tile entity position")
        if any(not 0 <= v < s for v, s in zip(local, region.size)):
            raise ValueError(f"tile entity outside Litematic region {region.name!r}")
        pos = tuple(v + d for v, d in zip(local, delta))
        if pos in result.block_nbt:
            raise ValueError(f"duplicate Litematic tile entity at {pos}")
        nbt = deepcopy(raw)
        nbt.update(_position(pos))
        result.block_nbt[pos] = nbt
    for raw in _compounds(region.nbt.get("Entities", ListTag()), "Entities"):
        local = _vector(raw.get("Pos"), "Litematic entity Pos", integer=False)
        pos = tuple(v + p - o for v, p, o in zip(local, region.position, origin))
        nbt = deepcopy(raw)
        nbt["Pos"] = _list(pos, DoubleTag)
        result.entities.append(CompoundTag({
            "pos": _list(pos, DoubleTag),
            "blockPos": _list(_vector(tuple(math.floor(v) for v in pos), "entity block position")),
            "nbt": nbt,
        }))


class Litematic:
    """A native document retaining metadata, regions, ticks and unknown NBT.

    ``save`` retains the native document. ``to_structure`` creates a normalized
    block/entity view for rendering or conversion; it does not modify the file.
    """

    def __init__(self, path: PathInput, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> None:
        self.path = Path(path)
        self.root = load_root(path, max_nbt_bytes=max_nbt_bytes)
        self._validate_header()

    @classmethod
    def from_root(cls, root: CompoundTag) -> "Litematic":
        result = cls.__new__(cls)
        result.path = Path("<memory>")
        result.root = deepcopy(root)
        result._validate_header()
        return result

    def _validate_header(self):
        if not isinstance(self.root, CompoundTag):
            raise ValueError("Litematic root must be a compound")
        version = _integer(self.root.get("Version"), "Litematic Version")
        if version not in (5, 6, 7):
            raise ValueError(f"unsupported Litematic version {version}; expected 5, 6 or 7")
        self.data_version = _integer(self.root.get("MinecraftDataVersion"), "MinecraftDataVersion")
        regions = self.root.get("Regions")
        if not isinstance(regions, CompoundTag) or not regions:
            raise ValueError("Litematic must contain named Regions")
        if not isinstance(self.root.get("Metadata", CompoundTag()), CompoundTag):
            raise ValueError("Litematic Metadata must be a compound")

    @property
    def region_names(self) -> Tuple[str, ...]:
        return tuple(self.root["Regions"])

    def save(self, path: PathInput) -> Path:
        """Atomically save all native NBT, including fields unused by rendering."""
        self._validate_header()
        write_root(self.root, path)
        return Path(path)

    def to_structure(self, *, region: Optional[str] = None, max_blocks: int = DEFAULT_MAX_BLOCKS) -> Structure:
        """Read one named region or all disjoint regions into local coordinates.

        Overlapping regions are ambiguous and rejected, including air overlaps.
        ``source_origin`` on the result maps local coordinates back to the file.
        Region layout, ticks and metadata remain available on this document;
        Structure NBT has no corresponding fields for them.
        """
        self._validate_header()
        names = self.region_names if region is None else (region,)
        prepared, volume = [], 0
        for name in names:
            if name not in self.root["Regions"]:
                raise ValueError(f"unknown Litematic region {name!r}; available: {self.region_names}")
            item = _Region.read(name, self.root["Regions"][name])
            volume += math.prod(item.size)
            _check_volume(volume, max_blocks)
            prepared.append(item)
        origin = tuple(min(item.minimum[axis] for item in prepared) for axis in range(3))
        size = tuple(
            max(item.minimum[axis] + item.size[axis] for item in prepared) - origin[axis]
            for axis in range(3)
        )
        root = CompoundTag({
            "DataVersion": IntTag(self.data_version), "size": _list(_vector(size, "combined size")),
            "palette": ListTag(), "blocks": ListTag(), "entities": ListTag(),
        })
        result = Structure.from_root(root)
        result.path = self.path
        palette_lookup = {}
        for item in prepared:
            _merge_region(result, item, origin, palette_lookup)
        result.validate()
        result.source_origin = origin
        return result


def export_litematic(src: Structure, destination: PathInput, *, name: Optional[str] = None,
                     author: str = "", max_blocks: int = DEFAULT_MAX_BLOCKS) -> Path:
    """Write the selected Structure palette as one Litematic region at (0,0,0).

    Missing cells become structure_void (Minecraft's no-placement marker).
    Block/entity NBT and DataVersion are retained; arbitrary Structure metadata
    and alternative palettes have no equivalent in this single-region export.
    """
    src.validate()
    count = math.prod(src.size)
    _check_volume(count, max_blocks)
    _integer(count, "Litematic TotalVolume")
    palette = [parse_state("minecraft:air")]
    lookup = {palette[0].to_snbt(): 0}
    remap = []
    for entry in src.palette_raw:
        key = entry.to_snbt()
        if key not in lookup:
            lookup[key] = len(palette)
            palette.append(deepcopy(entry))
        remap.append(lookup[key])
    missing = 0
    if len(src.present) < count:
        entry = parse_state("minecraft:structure_void")
        key = entry.to_snbt()
        if key not in lookup:
            lookup[key] = len(palette)
            palette.append(entry)
        missing = lookup[key]
    sx, sy, sz = src.size
    values = (
        remap[src.present[x, y, z]] if (x, y, z) in src.present else missing
        for y in range(sy) for z in range(sz) for x in range(sx)
    )
    tiles = ListTag()
    for pos, raw in src.block_nbt.items():
        _require_id(raw, f"block entity at {pos}")
        nbt = deepcopy(raw)
        nbt.update(_position(pos))
        tiles.append(nbt)
    entities = ListTag()
    for record in src.entities:
        _require_id(record["nbt"], "entity")
        nbt = deepcopy(record["nbt"])
        nbt["Pos"] = _list(_vector(record["pos"], "entity position", integer=False), DoubleTag)
        entities.append(nbt)
    region_name = name if name is not None else Path(destination).stem
    if not isinstance(region_name, str) or not region_name or not isinstance(author, str):
        raise ValueError("Litematic name must be nonempty and author must be a string")
    region = CompoundTag({
        "Position": _position((0, 0, 0)), "Size": _position(src.size),
        "BlockStatePalette": ListTag(palette), "BlockStates": _pack(values, count, len(palette)),
        "TileEntities": tiles, "Entities": entities,
        "PendingBlockTicks": ListTag(), "PendingFluidTicks": ListTag(),
    })
    total = sum(src.palette[i] not in AIR_NAMES for i in src.present.values()) + count - len(src.present)
    root = CompoundTag({
        "Version": IntTag(5 if src.data_version <= 3700 else 7), "SubVersion": IntTag(1),
        "MinecraftDataVersion": IntTag(src.data_version),
        "Metadata": CompoundTag({
            "Name": StringTag(region_name), "Author": StringTag(author),
            "Description": StringTag(""), "RegionCount": IntTag(1),
            "EnclosingSize": _position(src.size), "TotalVolume": IntTag(count),
            "TotalBlocks": IntTag(total), "TimeCreated": LongTag(0), "TimeModified": LongTag(0),
        }),
        "Regions": CompoundTag({region_name: region}),
    })
    write_root(root, destination)
    return Path(destination)
