"""Optional cleanup that keeps one connected solid component."""
import argparse

import numpy as np
from scipy import ndimage

from .nbt import AIR_NAMES, Structure, save_structure


def keep_largest_component(blocks):
    """Keep the largest 26-connected (face+edge+corner) block component."""
    if not blocks:
        return blocks, 0

    positions = np.asarray([block[0] for block in blocks], dtype=np.int32)
    offset = positions.min(axis=0)
    local = positions - offset
    mask = np.zeros(tuple(local.max(axis=0) + 1), dtype=bool)
    mask[tuple(local.T)] = True

    labels, count = ndimage.label(
        mask, structure=ndimage.generate_binary_structure(3, 3),
    )
    if count <= 1:
        return blocks, 0

    sizes = np.bincount(labels.ravel())
    largest = int(np.argmax(sizes[1:]) + 1)
    keep = {
        tuple(position)
        for position in positions[labels[tuple(local.T)] == largest]
    }
    filtered = [block for block in blocks if block[0] in keep]
    return filtered, len(blocks) - len(filtered)


def clean_structure(src_path, dst_path, report_only=False):
    src = Structure(src_path)
    solids = [
        (pos, index) for pos, index in src.present.items()
        if src.palette[index] not in AIR_NAMES
    ]
    filtered, removed = keep_largest_component(solids)
    keep = {pos for pos, _ in filtered}
    removed_positions = [pos for pos, _ in solids if pos not in keep]
    names = sorted({src.name_at(pos) for pos in removed_positions})
    print(f"removed={removed} blocks={names}")
    if report_only:
        return
    src.present = {
        pos: index for pos, index in src.present.items()
        if src.palette[index] in AIR_NAMES or pos in keep
    }
    src.block_nbt = {
        pos: nbt for pos, nbt in src.block_nbt.items() if pos in src.present
    }
    save_structure(src, dst_path, src.size)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst", nargs="?")
    parser.add_argument(
        "--report-only", action="store_true",
        help="print what would be removed, write nothing",
    )
    args = parser.parse_args()
    if not args.report_only and not args.dst:
        parser.error("dst is required unless --report-only")
    clean_structure(args.src, args.dst, args.report_only)


if __name__ == "__main__":
    main()
