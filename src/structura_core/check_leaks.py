#!/usr/bin/env python3
"""Find omitted Structure-NBT cells that are enclosed rather than exterior."""

import argparse

import numpy as np
from scipy import ndimage

from .nbt import Structure


def enclosed_pockets(structure):
    missing = np.ones(structure.size, dtype=bool)
    for pos in structure.present:
        missing[pos] = False

    labels, count = ndimage.label(
        missing, structure=ndimage.generate_binary_structure(3, 1),
    )
    if count == 0:
        return []
    exterior = set()
    for face in (
        labels[0], labels[-1], labels[:, 0], labels[:, -1],
        labels[:, :, 0], labels[:, :, -1],
    ):
        exterior.update(int(value) for value in np.unique(face) if value)

    sizes = np.bincount(labels.ravel())
    result = []
    for label in range(1, count + 1):
        if label in exterior or not sizes[label]:
            continue
        points = np.argwhere(labels == label)
        result.append((int(sizes[label]), points.min(axis=0), points.max(axis=0), points[0]))
    result.sort(key=lambda item: item[0], reverse=True)
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("path")
    parser.add_argument("--limit", type=int, default=15)
    args = parser.parse_args()
    if args.limit < 0:
        parser.error("--limit must be non-negative")

    structure = Structure(args.path)
    pockets = enclosed_pockets(structure)
    print(f"enclosed omitted-air pockets: {len(pockets)}")
    for size, low, high, sample in pockets[:args.limit]:
        print(
            f"  size={size:4d}  bbox x[{low[0]},{high[0]}] "
            f"y[{low[1]},{high[1]}] z[{low[2]},{high[2]}] "
            f"sample={tuple(int(value) for value in sample)}"
        )


if __name__ == "__main__":
    main()
