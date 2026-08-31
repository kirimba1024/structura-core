#!/usr/bin/env python3
"""Heuristically drop looted chests into a structure's enclosed rooms.

Runs on the pristine source, before envelope.py, so every downstream
variant (surface, sky, underwater) inherits the same chests.
"""
import argparse
import math

import numpy as np
from amulet_nbt import CompoundTag, StringTag
from scipy import ndimage

from .envelope import compute_masks
from .nbt import AIR_NAMES, Structure, save_structure

FACING_DELTA = {
    "north": (0, -1), "south": (0, 1), "west": (-1, 0), "east": (1, 0),
}


def find_chest_spots(interior_air, solid, max_chests):
    not_solid = ~solid
    ext_labels, _ = ndimage.label(not_solid)
    exterior = set(ext_labels[0].ravel()) | set(ext_labels[-1].ravel())
    exterior |= set(ext_labels[:, 0].ravel()) | set(ext_labels[:, -1].ravel())
    exterior |= set(ext_labels[:, :, 0].ravel()) | set(ext_labels[:, :, -1].ravel())
    exterior.discard(0)
    sealed_air = interior_air & ~np.isin(ext_labels, list(exterior))

    labels, room_count = ndimage.label(sealed_air, structure=np.ones((3, 3, 3)))
    floor_below = np.zeros_like(sealed_air)
    floor_below[:, 1:, :] = solid[:, :-1, :]
    headroom = np.zeros_like(sealed_air)
    headroom[:, :-1, :] = sealed_air[:, 1:, :]
    candidates = sealed_air & floor_below & headroom

    spots = []
    for label in range(1, room_count + 1):
        room = np.argwhere(candidates & (labels == label))
        if room.size == 0:
            continue
        for x, y, z in room:
            for facing, (dx, dz) in FACING_DELTA.items():
                nx, nz = x - dx, z - dz
                in_bounds = 0 <= nx < solid.shape[0] and 0 <= nz < solid.shape[2]
                if in_bounds and solid[nx, y, nz]:
                    spots.append(((int(x), int(y), int(z)), facing))
                    break
            else:
                continue
            break
        if len(spots) >= max_chests:
            break
    return spots


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--envelope-radius", type=float, default=1.5)
    parser.add_argument("--max-chests", type=int, default=3)
    parser.add_argument("--loot-table", default="structura:chests/default")
    args = parser.parse_args()

    src = Structure(args.src)
    solid = np.zeros(src.size, dtype=bool)
    for pos, idx in src.present.items():
        if src.palette[idx] not in AIR_NAMES:
            solid[pos] = True

    margin = math.ceil(args.envelope_radius) + 1
    _, _, interior_air, _, _ = compute_masks(
        np.pad(solid, margin), args.envelope_radius, 0.0, 0.0, 0,
    )
    interior_air = interior_air[margin:-margin, margin:-margin, margin:-margin]
    spots = find_chest_spots(interior_air, solid, args.max_chests)
    if not spots:
        print("no viable chest spots found")

    for pos, facing in spots:
        src.present[pos] = len(src.palette)
        src.palette.append("minecraft:chest")
        src.palette_raw.append(CompoundTag({
            "Name": StringTag("minecraft:chest"),
            "Properties": CompoundTag({"facing": StringTag(facing)}),
        }))
        src.block_nbt[pos] = CompoundTag({
            "id": StringTag("minecraft:chest"),
            "LootTable": StringTag(args.loot_table),
        })

    block_count = save_structure(src, args.dst, src.size, (0, 0, 0))
    print(f"blocks={block_count} chests={len(spots)} at {[p for p, _ in spots]}")


if __name__ == "__main__":
    main()
