#!/usr/bin/env python3
"""Thin stone safety pad under an enveloped structure, for underground/glass-dome placement."""
import argparse
import itertools

import numpy as np

from .nbt import Structure, save_structure
from .terrain_pod import PATCH_CELL, base_footprint, ground_palette, hash3, patch_noise, pick_palette

FLOOR_TORCH_DENSITY = 0.06
TORCH_BUCKET = 3


def dome_floor_palette(ground):
    if ground:
        names, cumulative = ground
        weights = np.diff(np.concatenate(([0.0], cumulative))) * 0.7
        names = list(names) + ["minecraft:sand"]
        weights = np.concatenate([weights, [0.3]])
        return names, np.cumsum(weights / weights.sum())
    names = ["minecraft:grass_block", "minecraft:sand", "minecraft:dirt"]
    return names, np.cumsum([0.65, 0.25, 0.10])


def pad_blocks(pad, stone, dome=False, ground=None):
    top_y = pad.shape[1] - 1
    floor_palette = dome_floor_palette(ground) if dome else None
    subsurface = (
        (stone, "minecraft:dirt", "minecraft:gravel") if dome
        else (stone, "minecraft:cobblestone", "minecraft:andesite")
    )
    floor_noise = patch_noise((pad.shape[0], pad.shape[2]), PATCH_CELL, 7) if dome else None
    for x, y, z in np.argwhere(pad):
        if dome and y == top_y:
            material = pick_palette(*floor_palette, int(floor_noise[x, z] * 255))
        else:
            material = subsurface[hash3(x, y, z, 0) % len(subsurface)]
        yield (int(x), int(y), int(z)), material


def floor_torch_blocks(footprint, house_footprint, top_y, bucket=TORCH_BUCKET):
    free = footprint & ~house_footprint
    for bx in range(0, free.shape[0], bucket):
        for bz in range(0, free.shape[1], bucket):
            block = free[bx:bx + bucket, bz:bz + bucket]
            if not block.any() or hash3(bx, bz, 0, 8) >= int(FLOOR_TORCH_DENSITY * 255):
                continue
            xs, zs = np.nonzero(block)
            pick = hash3(bx, bz, 1, 8) % len(xs)
            x, z = bx + int(xs[pick]), bz + int(zs[pick])
            yield (x, top_y + 1, z), "minecraft:torch"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="enveloped Structure NBT")
    parser.add_argument("dst")
    parser.add_argument("--envelope-masks", required=True)
    parser.add_argument("--thickness", type=int, default=3)
    parser.add_argument("--stone", default="minecraft:stone")
    parser.add_argument(
        "--footprint", choices=("building", "dome"), default="building",
        help="'dome' seals the full glass-dome floor, not just the building's own base",
    )
    parser.add_argument(
        "--secret", action="store_true",
        help="skip decorative floor/wall torches -- a hidden structure meant to be found unlit",
    )
    parser.add_argument("--masks", help="optional compressed NumPy debug file")
    args = parser.parse_args()

    if args.thickness < 1:
        parser.error("--thickness must be at least 1")

    src = Structure(args.src)
    masks = np.load(args.envelope_masks)
    envelope = masks["envelope"]
    base_y = int(masks["base_y"])
    if envelope.shape != src.size:
        parser.error("envelope masks do not match the source NBT")

    if args.footprint == "dome":
        if "glass_dome" not in masks or not masks["glass_dome"].any():
            parser.error("--footprint dome needs an envelope built with --glass-dome")
        center = masks["bubble_center"]
        glass_thickness = float(masks["glass_thickness"]) if "glass_thickness" in masks else 0.0
        glass_layers = int(masks["glass_layers"]) if "glass_layers" in masks else 1
        glass_gap = int(masks["glass_gap"]) if "glass_gap" in masks else 0
        shell_extent = (
            glass_thickness if glass_layers == 1
            else glass_thickness * 2 + glass_gap
        )
        radii = np.maximum(masks["bubble_radii"], 0.5) + shell_extent
        power = float(masks["bubble_power"])
        shape2d = (envelope.shape[0], envelope.shape[2])
        x, z = np.ogrid[:shape2d[0], :shape2d[1]]
        dy = abs(base_y - center[1]) / radii[1]
        remaining = (1.0 - dy ** power) ** (1.0 / power) if dy < 1.0 else 0.0
        footprint = (
            (np.abs(x - center[0]) / radii[0]) ** power
            + (np.abs(z - center[2]) / radii[2]) ** power
            <= remaining ** power + 1e-9
        )
        pad = np.zeros((shape2d[0], base_y + args.thickness, shape2d[1]), dtype=bool)
        for layer in range(args.thickness):
            pad[:, base_y + args.thickness - 1 - layer, :] = footprint
    else:
        footprint = base_footprint(envelope, base_y)
        pad = np.zeros((footprint.shape[0], base_y + args.thickness, footprint.shape[1]), dtype=bool)
        for layer in range(args.thickness):
            pad[:, base_y + args.thickness - 1 - layer, :] = footprint

    dome = args.footprint == "dome"
    ground = None
    extras = ()
    if dome:
        house_footprint = base_footprint(envelope, base_y)
        ground = ground_palette(src, house_footprint, base_y)
        if not args.secret:
            top_y = pad.shape[1] - 1
            extras = floor_torch_blocks(footprint, house_footprint, top_y)

    shift = (0, args.thickness, 0)
    size = (pad.shape[0], src.size[1] + args.thickness, pad.shape[2])
    block_count = save_structure(
        src, args.dst, size, shift,
        itertools.chain(pad_blocks(pad, args.stone, dome, ground), extras),
    )

    if args.masks:
        with open(args.masks, "wb") as output:
            np.savez_compressed(output, pod=pad, shift=np.asarray(shift))

    print(f"size={size} blocks={block_count} pad={int(pad.sum())}")


if __name__ == "__main__":
    main()
