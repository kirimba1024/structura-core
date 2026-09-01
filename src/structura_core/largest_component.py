"""Optional cleanup that keeps one connected solid component, or drops
only confidently-tiny debris while leaving everything else untouched."""
import argparse
from collections import Counter

import numpy as np
from scipy import ndimage

from .nbt import AIR_NAMES, Structure, save_structure


def _label_components(blocks):
    """26-connected (face+edge+corner) component labels for a solid-block
    list. Returns (positions, block_labels, sizes, count); sizes[0] is
    unused padding (ndimage.label reserves label 0 for background)."""
    positions = np.asarray([block[0] for block in blocks], dtype=np.int32)
    offset = positions.min(axis=0)
    local = positions - offset
    mask = np.zeros(tuple(local.max(axis=0) + 1), dtype=bool)
    mask[tuple(local.T)] = True
    labels, count = ndimage.label(
        mask, structure=ndimage.generate_binary_structure(3, 3),
    )
    sizes = np.bincount(labels.ravel())
    block_labels = labels[tuple(local.T)]
    return positions, block_labels, sizes, count


def keep_largest_component(blocks):
    """Keep only the single largest component, drop every other one --
    a blunt tool: a legitimate second wing or an intentionally detached
    shed is discarded exactly like real debris. Never auto-applied
    archive-wide; see info.txt CURATION."""
    if not blocks:
        return blocks, 0
    positions, block_labels, sizes, count = _label_components(blocks)
    if count <= 1:
        return blocks, 0
    largest = int(np.argmax(sizes[1:]) + 1)
    keep = {tuple(p) for p, label in zip(positions, block_labels) if label == largest}
    filtered = [block for block in blocks if block[0] in keep]
    return filtered, len(blocks) - len(filtered)


def drop_tiny_components(blocks, max_size):
    """Drop every component at or below max_size blocks, keep every other
    component (including a legitimate second wing) untouched. A fragment
    this small -- a stray leaf, a lone vine block, a single misplaced
    stone -- is confidently noise rather than an artistic choice, unlike
    a whole detached structure, so this is safe to auto-apply.

    The single largest component always survives regardless of its own
    size. Without that floor, a source file fragmented enough that every
    component is individually <= max_size (never seen in the archive so
    far, but this runs unattended on every batch conversion with no
    review) would empty out entirely -- this is meant to drop confident
    noise, never the whole structure."""
    if not blocks:
        return blocks, 0
    positions, block_labels, sizes, count = _label_components(blocks)
    if count <= 1:
        return blocks, 0
    largest = int(np.argmax(sizes[1:]) + 1)
    keep_labels = {label for label in range(1, count + 1) if sizes[label] > max_size}
    keep_labels.add(largest)
    keep = {tuple(p) for p, label in zip(positions, block_labels) if label in keep_labels}
    filtered = [block for block in blocks if block[0] in keep]
    return filtered, len(blocks) - len(filtered)


def clean_structure(src_path, dst_path, mode="largest", max_size=6, report_only=False):
    src = Structure(src_path)
    solids = [
        (pos, index) for pos, index in src.present.items()
        if src.palette[index] not in AIR_NAMES
    ]
    if mode == "tiny":
        filtered, removed = drop_tiny_components(solids, max_size)
    else:
        filtered, removed = keep_largest_component(solids)
    keep = {pos for pos, _ in filtered}
    removed_positions = [pos for pos, _ in solids if pos not in keep]
    tally = Counter(src.name_at(pos) for pos in removed_positions)
    blocks = ", ".join(f"{name} x{n}" for name, n in sorted(tally.items()))
    print(f"mode={mode} removed={removed} blocks=[{blocks}]")
    if report_only:
        return
    src.present = {
        pos: index for pos, index in src.present.items()
        if src.palette[index] in AIR_NAMES or pos in keep
    }
    src.block_nbt = {
        pos: nbt for pos, nbt in src.block_nbt.items() if pos in src.present
    }
    if src.present:
        xs, ys, zs = zip(*src.present)
        ox, oy, oz = min(xs), min(ys), min(zs)
        new_size = (max(xs) - ox + 1, max(ys) - oy + 1, max(zs) - oz + 1)
    else:
        ox, oy, oz = 0, 0, 0
        new_size = src.size
    save_structure(src, dst_path, new_size, shift=(-ox, -oy, -oz))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst", nargs="?")
    parser.add_argument(
        "--mode", choices=("largest", "tiny"), default="largest",
        help="'largest': keep only the single biggest component (blunt, "
             "human-reviewed use only). 'tiny': drop only components at "
             "or below --max-size, keep everything else (safe to automate).",
    )
    parser.add_argument(
        "--max-size", type=int, default=6,
        help="mode=tiny: components at or below this many blocks are dropped",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="print what would be removed, write nothing",
    )
    args = parser.parse_args()
    if not args.report_only and not args.dst:
        parser.error("dst is required unless --report-only")
    clean_structure(args.src, args.dst, args.mode, args.max_size, args.report_only)


if __name__ == "__main__":
    main()
