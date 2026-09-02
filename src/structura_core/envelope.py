#!/usr/bin/env python3
"""Build a tight envelope and write its protected air to Structure NBT."""
import argparse
from itertools import chain
import math

import numpy as np
from scipy import ndimage

from .nbt import AIR_NAMES, Structure, save_structure
from .voxel import closing, dilation, erosion


def layered_hull(solid, envelope_radius):
    result = np.zeros_like(solid)
    for y in range(solid.shape[1]):
        layer = solid[:, y, :]
        if not layer.any():
            continue
        closed_layer = closing(layer, envelope_radius) | layer
        result[:, y, :] = ndimage.binary_fill_holes(closed_layer)
    return result


def compute_masks(solid, envelope_radius, aura_radius, cavern_radius, base_y):
    closed = closing(solid, envelope_radius) | solid
    envelope = ndimage.binary_fill_holes(closed) | layered_hull(solid, envelope_radius)
    surface = envelope & ~erosion(envelope, 1.0)
    interior_air = envelope & ~solid
    aura_volume = dilation(envelope, aura_radius)
    aura = aura_volume & ~envelope
    cavern_aura = (
        dilation(envelope, cavern_radius) & ~aura_volume
        if cavern_radius > 0 else np.zeros_like(envelope)
    )
    aura[:, :base_y, :] = False
    cavern_aura[:, :base_y, :] = False
    return envelope, surface, interior_air, aura, cavern_aura


GROUND_MARKERS = frozenset({
    "minecraft:grass_block", "minecraft:dirt_path", "minecraft:coarse_dirt",
    "minecraft:farmland", "minecraft:podzol", "minecraft:mycelium",
    "minecraft:sand", "minecraft:red_sand", "minecraft:gravel",
    "minecraft:snow_block",
})


def _topmost_per_column(src, keep):
    by_column = {}
    for (x, y, z), index in src.present.items():
        if not keep(src.palette[index]):
            continue
        col = (x, z)
        if col not in by_column or y > by_column[col]:
            by_column[col] = y
    return by_column


def _bottommost_per_column(src, keep):
    by_column = {}
    for (x, y, z), index in src.present.items():
        if not keep(src.palette[index]):
            continue
        col = (x, z)
        if col not in by_column or y < by_column[col]:
            by_column[col] = y
    return by_column


def _extend_through_plinth(solid, base_y, high=0.85, low=0.5, window=15):
    footprint = solid.any(axis=1)
    area = int(footprint.sum())
    if area == 0:
        return base_y
    coverage = solid.sum(axis=(0, 2)) / area
    saw_dip = False
    extended = base_y
    for y in range(base_y, min(solid.shape[1], base_y + window + 1)):
        if coverage[y] < low:
            saw_dip = True
        elif coverage[y] >= high and saw_dip:
            extended = y
    return extended


def detect_base_y(src, solid, margin):
    """The structure's own ground/yard level, as one Y. Everything below
    it counts as "already underground": aura/cavern_aura stop there, and
    terrain_pod's pod sits below it with its own top layer picking up
    right where this leaves off -- getting this Y right is what makes the
    pod blend instead of either burying the porch or leaving a gap.

    The lowest solid block anywhere is NOT that level: a doorstep, a
    lamp-post foundation, or a single low decoration pulls it down below
    the building's real floor. Per-column, then median across columns, so
    a handful of outlier columns (a planter, one terraced step, a
    captured slope) can't skew the result the way either a single global
    min or a raw block-count mode can:

    1. Preferred: GROUND_MARKERS -- the material builders actually walk
       on (grass/path/farmland/sand/snow/...), not walls. Topmost marker
       per (x, z) column, median Y across every column that has one.
    2. Fallback, only when the build has none of those (all-stone, or an
       interior-only cutaway): lowest solid block per column, same median.
    3. A full-footprint plinth (a raised stone platform, steps) can sit
       above that median, with a narrower band in between -- extend
       upward through any such dip-then-recover run, so a house that
       "starts above those stones" (see notes/[AManofKent]
       NiceVillageTrain) gets base_y at the plinth's own top, not its
       bottom edge.
    """
    by_column = _topmost_per_column(src, lambda name: name in GROUND_MARKERS)
    if not by_column:
        by_column = _bottommost_per_column(src, lambda name: name not in AIR_NAMES)
    if by_column:
        base_y = int(round(float(np.median(list(by_column.values()))))) + margin
    else:
        base_y = int(np.flatnonzero(solid.any(axis=(0, 2)))[0])
    return _extend_through_plinth(solid, base_y)


def adaptive_cavern_radius(solid, minimum=3.0, maximum=6.5):
    y = np.argwhere(solid)[:, 1]
    low, high = np.quantile(y, (0.05, 0.95))
    height = max(1.0, high - low + 1.0)
    area = float(solid.any(axis=1).sum())
    equivalent_radius = math.sqrt(area / math.pi)
    scale = math.sqrt(equivalent_radius * height)
    radius = 2.5 + 1.2 * math.log1p(scale / 6.0)
    return round(np.clip(radius, minimum, maximum) * 2.0) / 2.0


def bubble_geometry(protected_volume, base_y, shape, glass_thickness):
    points = np.argwhere(protected_volume)
    low = points.min(axis=0).astype(float)
    high = points.max(axis=0).astype(float)
    center = (low + high) / 2.0
    center[1] = base_y if shape == "hemisphere" else (base_y + high[1]) / 2.0
    above_ground = points[points[:, 1] >= base_y]
    sizing_points = above_ground if len(above_ground) else points
    offsets = np.abs(sizing_points - center)
    if shape == "fitted":
        power = 4.0
        radii = np.maximum(offsets.max(axis=0), 0.5)
        scale = float(((offsets / radii) ** power).sum(axis=1).max()) ** (1 / power)
        radii *= scale
    else:
        power = 2.0
        radius = float(np.sqrt((offsets ** 2).sum(axis=1).max()))
        radii = np.full(3, radius)

    outer_radii = radii + glass_thickness
    lower = np.floor(center - outer_radii).astype(int)
    upper = np.ceil(center + outer_radii).astype(int)
    before = np.maximum(0, -lower)
    before[1] = 0
    after = np.maximum(0, upper - (np.asarray(protected_volume.shape) - 1))
    padding = tuple((int(a), int(b)) for a, b in zip(before, after))
    return padding, center + before, radii, power


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--envelope-radius", type=float, default=1.5)
    parser.add_argument("--aura-radius", type=float, default=1.0)
    parser.add_argument("--cavern-aura-radius", type=float)
    parser.add_argument("--glass-dome", action="store_true")
    parser.add_argument("--glass-block", default="minecraft:glass")
    parser.add_argument("--glass-thickness", type=int, choices=(1, 2), default=1)
    parser.add_argument("--glass-layers", type=int, choices=(1, 2), default=1)
    parser.add_argument("--glass-gap", type=int, default=1)
    parser.add_argument(
        "--dome-shape",
        choices=("fitted", "sphere", "hemisphere"),
        default="fitted",
    )
    parser.add_argument(
        "--dome-fit", choices=("envelope", "cavern"), default="envelope",
    )
    parser.add_argument(
        "--base-y", type=int, default=None,
        help="override detect_base_y with an exact ground-level Y, in the "
             "source structure's own coordinates (0 = its bottom layer) -- "
             "for the rare structure autodetection guesses wrong on (no "
             "reliable GROUND_MARKERS, an ambiguous plinth): read the Y off "
             "a render or region_report.py and pass it directly instead of "
             "fighting the heuristic",
    )
    parser.add_argument("--masks", help="optional compressed NumPy debug file")
    args = parser.parse_args()
    radii = [args.envelope_radius, args.aura_radius]
    if args.cavern_aura_radius is not None:
        radii.append(args.cavern_aura_radius)
    if min(radii) < 0:
        parser.error("radii must be non-negative")
    if args.glass_gap < 0:
        parser.error("--glass-gap must be non-negative")
    if (
        args.cavern_aura_radius is not None
        and 0 < args.cavern_aura_radius < args.aura_radius
    ):
        parser.error("cavern aura must be disabled or at least as wide as aura")

    src = Structure(args.src)
    if args.base_y is not None and not 0 <= args.base_y < src.size[1]:
        parser.error("--base-y must be within the structure's own Y range")
    solid = np.zeros(src.size, dtype=bool)
    explicit_air = np.zeros(src.size, dtype=bool)
    for pos, idx in src.present.items():
        if src.palette[idx] in AIR_NAMES:
            explicit_air[pos] = True
        else:
            solid[pos] = True
    if not solid.any():
        parser.error("source structure has no solid blocks")

    if args.cavern_aura_radius is not None:
        cavern_radius = args.cavern_aura_radius
    elif args.aura_radius <= 0:
        cavern_radius = 0.0
    else:
        cavern_radius = max(args.aura_radius, adaptive_cavern_radius(solid))
    outer_radius = max(args.aura_radius, cavern_radius)
    margin = math.ceil(args.envelope_radius + outer_radius) + 1
    padding = ((margin, margin), (margin, margin), (margin, margin))
    solid = np.pad(solid, padding)
    explicit_air = np.pad(explicit_air, padding)
    if args.base_y is not None:
        base_y = args.base_y + margin
    else:
        base_y = detect_base_y(src, solid, margin)

    envelope, surface, interior_air, aura, cavern_aura = compute_masks(
        solid, args.envelope_radius, args.aura_radius,
        cavern_radius, base_y,
    )
    bubble_aura = np.zeros_like(envelope)
    glass_gap_air = np.zeros_like(envelope)
    glass_dome = np.zeros_like(envelope)
    bubble_center = np.zeros(3, dtype=float)
    bubble_radii = np.zeros(3, dtype=float)
    bubble_power = 2.0
    if args.glass_dome:
        bubble_target = envelope | explicit_air
        if args.dome_fit == "cavern":
            bubble_target |= aura | cavern_aura
        shell_extent = (
            args.glass_thickness if args.glass_layers == 1
            else args.glass_thickness * 2 + args.glass_gap
        )
        bubble_padding, bubble_center, bubble_radii, bubble_power = bubble_geometry(
            bubble_target, base_y, args.dome_shape, shell_extent,
        )
        solid, explicit_air, envelope, surface, interior_air, aura, cavern_aura = (
            np.pad(mask, bubble_padding)
            for mask in (
                solid, explicit_air, envelope, surface, interior_air, aura,
                cavern_aura,
            )
        )
        bubble_target = np.pad(bubble_target, bubble_padding)
        x, y, z = np.ogrid[
            :bubble_target.shape[0],
            :bubble_target.shape[1],
            :bubble_target.shape[2],
        ]
        bubble_volume = (
            (np.abs(x - bubble_center[0]) / bubble_radii[0]) ** bubble_power
            + (np.abs(y - bubble_center[1]) / bubble_radii[1]) ** bubble_power
            + (np.abs(z - bubble_center[2]) / bubble_radii[2]) ** bubble_power
            <= 1.0 + 1e-9
        )
        bubble_volume[:, :base_y, :] = False
        aura &= bubble_volume
        cavern_aura &= bubble_volume
        bubble_aura = bubble_volume & ~(envelope | aura | cavern_aura)
        if args.glass_layers == 2:
            inner = dilation(bubble_volume, float(args.glass_thickness)) & ~bubble_volume
            outer_start = args.glass_thickness + args.glass_gap
            glass_gap_air = (
                dilation(bubble_volume, float(outer_start))
                & ~dilation(bubble_volume, float(args.glass_thickness))
            )
            outer = (
                dilation(bubble_volume, float(outer_start + args.glass_thickness))
                & ~dilation(bubble_volume, float(outer_start))
            )
            glass_dome = inner | outer
        else:
            glass_dome = (
                dilation(bubble_volume, float(args.glass_thickness)) & ~bubble_volume
            )
            glass_gap_air = np.zeros_like(bubble_volume)
        glass_dome[:, :base_y, :] = False
        shift_x = margin + bubble_padding[0][0]
        shift_z = margin + bubble_padding[2][0]
    else:
        shift_x = shift_z = margin

    crop = (slice(None), slice(margin, None), slice(None))
    solid = solid[crop]
    envelope = envelope[crop]
    surface = surface[crop]
    interior_air = interior_air[crop]
    aura = aura[crop]
    cavern_aura = cavern_aura[crop]
    bubble_aura = bubble_aura[crop]
    glass_gap_air = glass_gap_air[crop]
    glass_dome = glass_dome[crop]
    base_y -= margin
    bubble_center[1] -= margin

    shift = (shift_x, 0, shift_z)
    protected_air = interior_air | aura | cavern_aura | bubble_aura | glass_gap_air
    block_count = save_structure(
        src, args.dst, envelope.shape, shift,
        chain(
            ((pos, "minecraft:air") for pos in np.argwhere(protected_air)),
            ((pos, args.glass_block) for pos in np.argwhere(glass_dome)),
        ),
    )

    if args.masks:
        with open(args.masks, "wb") as output:
            np.savez_compressed(
                output, solid=solid, envelope=envelope, surface=surface,
                interior_air=interior_air, aura=aura, cavern_aura=cavern_aura,
                bubble_aura=bubble_aura, glass_dome=glass_dome,
                glass_gap_air=glass_gap_air,
                shift=np.asarray(shift),
                base_y=base_y, envelope_radius=args.envelope_radius,
                aura_radius=args.aura_radius,
                cavern_aura_radius=cavern_radius,
                bubble_center=bubble_center, bubble_radii=bubble_radii,
                bubble_power=bubble_power,
                dome_shape=args.dome_shape,
                dome_fit=args.dome_fit,
                glass_thickness=args.glass_thickness,
                glass_layers=args.glass_layers, glass_gap=args.glass_gap,
            )

    base_y_mode = "manual" if args.base_y is not None else "auto"
    print(f"base_y={base_y} ({base_y_mode})")
    print(f"size={envelope.shape} blocks={block_count}")
    print(f"envelope={int(envelope.sum())} surface={int(surface.sum())}")
    print(
        f"interior_air={int(interior_air.sum())} aura={int(aura.sum())} "
        f"cavern_aura={int(cavern_aura.sum())} "
        f"bubble_aura={int(bubble_aura.sum())} glass={int(glass_dome.sum())}"
    )
    mode = "manual" if args.cavern_aura_radius is not None else "adaptive"
    print(
        f"cavern_radius={cavern_radius:g} ({mode}) "
        f"bubble_radii={'x'.join(f'{value:.1f}' for value in bubble_radii)} "
        f"shape={args.dome_shape} fit={args.dome_fit} "
        f"glass_thickness={args.glass_thickness}"
    )


if __name__ == "__main__":
    main()
