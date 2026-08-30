#!/usr/bin/env python3
"""Export a vanilla Structure NBT to a Sponge Schematic v2 (.schem), for
flying around it in Amulet Map Editor -- amulet-core has no NBT structure
reader, only schem/construction/mcstructure, so it can't open our own
Structure NBT files directly."""
import argparse
from pathlib import Path

import numpy as np
from amulet.level.formats.sponge_schem.varint import encode_array
from amulet_nbt import (
    ByteArrayTag, CompoundTag, IntArrayTag, IntTag, ListTag, NamedTag,
    ShortTag, StringTag,
)

from .nbt import AIR_NAMES, Structure


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    args = parser.parse_args()

    src = Structure(args.src)
    sx, sy, sz = src.size

    def blockstate(entry):
        name = str(entry["Name"])
        if "Properties" not in entry:
            return name
        props = ",".join(
            f"{k}={v}" for k, v in sorted(entry["Properties"].items())
        )
        return f"{name}[{props}]"

    dedup_index = {}
    remap = []
    for entry in src.palette_raw:
        key = blockstate(entry)
        remap.append(dedup_index.setdefault(key, len(dedup_index)))

    air_key = "minecraft:air"
    air_index = dedup_index.setdefault(air_key, len(dedup_index))
    indices = np.full((sx, sy, sz), air_index, dtype=np.uint32)
    for pos, index in src.present.items():
        indices[pos] = remap[index]

    block_data = encode_array(
        int(v) for v in np.transpose(indices, (1, 2, 0)).ravel()
    )
    palette = CompoundTag({key: IntTag(i) for key, i in dedup_index.items()})

    block_entities = ListTag()
    for pos, nbt in src.block_nbt.items():
        if "id" not in nbt:
            continue
        extra = CompoundTag({k: v for k, v in nbt.items() if k != "id"})
        block_entities.append(CompoundTag({
            "Id": StringTag(str(nbt["id"])),
            "Pos": IntArrayTag(list(pos)),
            "Extra": extra,
        }))

    root = CompoundTag({
        "Version": IntTag(2),
        "DataVersion": IntTag(src.data_version),
        "Width": ShortTag(sx),
        "Height": ShortTag(sy),
        "Length": ShortTag(sz),
        "Offset": IntArrayTag([0, 0, 0]),
        "Palette": palette,
        "PaletteMax": IntTag(len(dedup_index)),
        "BlockData": ByteArrayTag(
            np.frombuffer(block_data, dtype=np.uint8).astype(np.int8)
        ),
        "BlockEntities": block_entities,
    })
    destination = Path(args.dst)
    destination.parent.mkdir(parents=True, exist_ok=True)
    NamedTag(CompoundTag({"Schematic": root}), "").save_to(str(destination))
    print(f"{args.dst} size={src.size} blocks={len(src.present)}")


if __name__ == "__main__":
    main()
