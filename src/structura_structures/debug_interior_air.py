#!/usr/bin/env python3
"""Render the interior_air cavern alone as solid lapis blocks, for visual debugging."""
import argparse
import math

import numpy as np

from .envelope import adaptive_cavern_radius, compute_masks
from .nbt import AIR_NAMES, Structure, save_structure


class BlankSource:
    def __init__(self, src):
        self.data_version = src.data_version
        self.palette_raw = []
        self.palette = []
        self.present = {}
        self.block_nbt = {}
        self.entities = []


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--envelope-radius", type=float, default=1.5)
    parser.add_argument("--block", default="minecraft:lapis_block")
    parser.add_argument(
        "--target", choices=("interior_air", "envelope"), default="interior_air",
    )
    args = parser.parse_args()

    src = Structure(args.src)
    solid = np.zeros(src.size, dtype=bool)
    for pos, idx in src.present.items():
        if src.palette[idx] not in AIR_NAMES:
            solid[pos] = True

    cavern_radius = adaptive_cavern_radius(solid)
    margin = math.ceil(args.envelope_radius + cavern_radius) + 1
    solid = np.pad(solid, margin)
    base_y = int(np.flatnonzero(solid.any(axis=(0, 2)))[0])

    envelope, _, interior_air, _, _ = compute_masks(
        solid, args.envelope_radius, 0.0, 0.0, base_y,
    )
    target = envelope if args.target == "envelope" else interior_air

    shift = (margin, 0, margin)
    block_count = save_structure(
        BlankSource(src), args.dst, target.shape, shift,
        ((pos, args.block) for pos in np.argwhere(target)),
    )
    print(f"size={target.shape} lapis_blocks={block_count}")


if __name__ == "__main__":
    main()
