"""Export Structure NBT as Sponge Schematic v2, including entities."""

import argparse
from copy import deepcopy
from pathlib import Path

import numpy as np
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

from .nbt_io import PathInput, write_root
from .structure import Structure, state_key
from .validation import vector


def _encode_varints(values):
    data = bytearray()
    for value in values:
        value = int(value)
        while value > 127:
            data.append((value & 127) | 128)
            value >>= 7
        data.append(value)
    return bytes(data)


def schematic_root(src, *, offset=(0, 0, 0)):
    """Build a v2 payload using the selected palette; omitted cells become air.

    Sponge has one palette and a dense block array. Other Structure palettes
    and the distinction between omitted cells and air are not representable.
    """
    src.validate()
    sx, sy, sz = src.size
    if any(value > 65535 for value in src.size):
        raise ValueError("Sponge v2 dimensions must fit an unsigned short (1..65535)")

    dedup_index = {}
    remap = []
    for entry in src.palette_raw:
        key = state_key(entry)
        remap.append(dedup_index.setdefault(key, len(dedup_index)))

    air_index = dedup_index.setdefault("minecraft:air", len(dedup_index))
    indices = np.full((sx, sy, sz), air_index, dtype=np.uint32)
    for pos, index in src.present.items():
        indices[pos] = remap[index]
    # Sponge order is x + z * Width + y * Width * Length.
    block_data = _encode_varints(np.transpose(indices, (1, 2, 0)).ravel())

    block_entities = ListTag()
    for pos, nbt in src.block_nbt.items():
        if "id" not in nbt:
            raise ValueError(f"block entity at {pos} has no id for Sponge export")
        if not isinstance(nbt["id"], StringTag) or not str(nbt["id"]):
            raise ValueError(f"block entity at {pos} needs a non-empty string id for Sponge export")
        entry = deepcopy(nbt)
        entry["Id"] = StringTag(str(entry.pop("id")))
        entry["Pos"] = IntArrayTag(list(pos))
        block_entities.append(entry)

    entities = ListTag()
    for record in src.entities:
        entry = deepcopy(record["nbt"])
        if "id" not in entry:
            raise ValueError("entity has no id for Sponge export")
        if not isinstance(entry["id"], StringTag) or not str(entry["id"]):
            raise ValueError("entity needs a non-empty string id for Sponge export")
        entry["Id"] = StringTag(str(entry.pop("id")))
        entry["Pos"] = ListTag([DoubleTag(value.py_data) for value in record["pos"]])
        entities.append(entry)

    return CompoundTag({
        "Version": IntTag(2),
        "DataVersion": IntTag(src.data_version),
        "Width": ShortTag(sx if sx < 32768 else sx - 65536),
        "Height": ShortTag(sy if sy < 32768 else sy - 65536),
        "Length": ShortTag(sz if sz < 32768 else sz - 65536),
        "Offset": IntArrayTag(vector(offset, "Schematic offset")),
        "Palette": CompoundTag({key: IntTag(i) for key, i in dedup_index.items()}),
        "PaletteMax": IntTag(len(dedup_index)),
        "BlockData": ByteArrayTag(np.frombuffer(block_data, dtype=np.int8)),
        "BlockEntities": block_entities,
        "Entities": entities,
    })


def export_schematic(src: Structure, destination: PathInput, *, offset=(0, 0, 0)) -> Path:
    """Write a Sponge v2 file without requiring the legacy conversion extra."""
    destination = Path(destination)
    write_root(schematic_root(src, offset=offset), destination, name="Schematic")
    return destination


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--palette", type=int, default=0, help="Structure palette to export")
    args = parser.parse_args()

    src = Structure(args.src, palette_index=args.palette)
    export_schematic(src, args.dst)
    print(f"{args.dst} size={src.size} blocks={len(src.present)} entities={len(src.entities)}")


if __name__ == "__main__":
    main()
