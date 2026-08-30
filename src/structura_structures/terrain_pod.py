#!/usr/bin/env python3
"""Add an organic terrain pod below an enveloped structure."""
import argparse
import itertools
import math

import numpy as np
from scipy import ndimage

from .nbt import Structure, save_structure
from .voxel import closing, signed_distance


def base_footprint(envelope, base_y, tolerance=2):
    top = min(envelope.shape[1], base_y + tolerance + 1)
    footprint = envelope[:, base_y:top, :].any(axis=1)
    return ndimage.binary_fill_holes(closing(footprint, 2.0))


def rounded_footprint(footprint, sigma, threshold):
    if sigma <= 0:
        return footprint
    field = ndimage.gaussian_filter(footprint.astype(np.float32), sigma=sigma)
    return ndimage.binary_fill_holes((field >= threshold) | footprint)


def inradius_of(footprint):
    return float(ndimage.distance_transform_edt(footprint).max())


def smootherstep(edge0, edge1, x):
    t = np.clip((x - edge0) / (edge1 - edge0), 0.0, 1.0)
    return t * t * t * (t * (t * 6 - 15) + 10)


BELLY_T = 0.28


def radius_profile(inradius, top_radius, bulge, depth):
    end_radius = top_radius - inradius - 1
    peak_radius = top_radius + bulge
    t = np.linspace(0.0, 1.0, depth)
    u = np.clip(t / BELLY_T, 0.0, 1.0)
    rise = 1 - (1 - u) ** 2
    fall = smootherstep(BELLY_T, 1.0, t)
    return np.where(
        t <= BELLY_T,
        top_radius + bulge * rise,
        peak_radius - (peak_radius - end_radius) * fall,
    )


def curve_offsets(depth, amount, angle_degrees, twist_degrees=0.0):
    if amount <= 0:
        return np.zeros((depth, 2))
    t = np.linspace(0.0, 1.0, depth)
    lean = smootherstep(BELLY_T, 0.9, t) * amount
    angle = math.radians(angle_degrees) + math.radians(twist_degrees) * smootherstep(0.55, 1.0, t)
    return np.stack([lean * np.cos(angle), lean * np.sin(angle)], axis=1)


def pod_depth(inradius, top_radius, bulge, max_depth=None):
    depth = int(round((bulge + inradius) * 2.1)) + 6
    return depth if max_depth is None else min(depth, max_depth)


def build_pod(
    footprint, base_y, depth, profile, smoothing, offsets=None, roundness=0.0,
    side_bulge=0.0,
):
    field = signed_distance(footprint)
    coords = np.argwhere(footprint)
    center = coords.mean(axis=0)
    circumscribing_radius = float(np.hypot(*(coords - center).T).max())
    grid = np.mgrid[:footprint.shape[0], :footprint.shape[1]] - center[:, None, None]
    disk_dist = np.hypot(*grid)
    circle_r_by_layer = (
        smootherstep(0.0, BELLY_T, np.linspace(0.0, 1.0, depth))
        * circumscribing_radius * roundness
    )
    rise_frac = np.clip(
        (profile - profile[0]) / (profile.max() - profile[0] + 1e-9), 0.0, None,
    )
    side_lobes = np.clip(np.cos(4 * np.arctan2(grid[1], grid[0])), 0.0, None)
    pod = np.zeros((footprint.shape[0], base_y + depth, footprint.shape[1]), dtype=bool)
    top_y = base_y + depth - 1
    for layer, radius in enumerate(profile):
        circle_r = circle_r_by_layer[layer]
        layer_field = field if circle_r <= 0 else np.minimum(field, disk_dist - circle_r)
        if side_bulge > 0:
            layer_field = layer_field - side_bulge * rise_frac[layer] * side_lobes
        dx, dz = offsets[layer] if offsets is not None else (0.0, 0.0)
        layer_field = layer_field if dx == 0 and dz == 0 else ndimage.shift(
            layer_field, (-dx, -dz), order=1, mode="constant", cval=layer_field.max() + 1,
        )
        pod[:, top_y - layer, :] = layer_field <= radius
    if smoothing > 0:
        field3d = ndimage.gaussian_filter(pod.astype(np.float32), sigma=smoothing)
        pod = field3d >= 0.5
    return pod


def pod_torch_blocks(pod, house_footprint, density, max_distance=6, rim_depth=1, bucket=3):
    if density <= 0:
        return
    top_y = pod.shape[1] - 1
    grass_mask = pod & ~np.pad(pod, ((0, 0), (0, 1), (0, 0)))[:, 1:, :]
    grass_mask[:, :top_y - rim_depth, :] = False
    free = grass_mask.any(axis=1) & ~house_footprint
    distance = ndimage.distance_transform_edt(~house_footprint)
    for bx in range(0, free.shape[0], bucket):
        for bz in range(0, free.shape[1], bucket):
            block = free[bx:bx + bucket, bz:bz + bucket]
            if not block.any():
                continue
            xs, zs = np.nonzero(block)
            pick = hash3(bx, bz, 1, 10) % len(xs)
            x, z = bx + int(xs[pick]), bz + int(zs[pick])
            d = float(distance[x, z])
            if d > max_distance:
                continue
            local_density = density * (1 - d / max_distance)
            if hash3(bx, bz, 0, 10) >= int(local_density * 255):
                continue
            y = int(np.argmax(grass_mask[x, :, z]))
            yield (x, y + 1, z), "minecraft:torch"


def hash3(x, y, z, salt):
    return (x * 73856093 ^ y * 19349663 ^ z * 83492791 ^ salt) & 0xff


STONE_PATCH = 4

NATURAL_GROUND_BLOCKS = {
    "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
    "minecraft:podzol", "minecraft:mycelium", "minecraft:mud",
    "minecraft:stone", "minecraft:mossy_cobblestone",
    "minecraft:andesite", "minecraft:diorite", "minecraft:granite",
    "minecraft:deepslate", "minecraft:moss_block",
    "minecraft:gravel", "minecraft:sand", "minecraft:red_sand",
}


def ground_palette(src, footprint, base_y):
    counts = {}
    for x, z in np.argwhere(footprint):
        index = src.present.get((int(x), base_y, int(z)))
        if index is None:
            continue
        name = src.palette[index]
        if name not in NATURAL_GROUND_BLOCKS:
            continue
        counts[name] = counts.get(name, 0) + 1
    if not counts:
        return None
    names = list(counts)
    weights = np.array([counts[n] for n in names], dtype=float)
    return names, np.cumsum(weights / weights.sum())


def pick_palette(names, cumulative, hash_value):
    index = min(int(np.searchsorted(cumulative, hash_value / 255)), len(names) - 1)
    return names[index]


PATCH_CELL = 6


def patch_noise(shape, cell, salt):
    lattice_shape = (shape[0] // cell + 2, shape[1] // cell + 2)
    lattice = np.array([
        [hash3(gx, gz, 0, salt) for gz in range(lattice_shape[1])]
        for gx in range(lattice_shape[0])
    ], dtype=np.float64) / 255.0
    smooth = ndimage.zoom(lattice, cell, order=1, mode="nearest")
    return smooth[:shape[0], :shape[1]]


def pod_blocks(pod, soil_depth, grass, dirt, stone, hidden_top=None, ground=None):
    surface_dist = ndimage.distance_transform_edt(pod)
    grass_mask = pod & ~np.pad(pod, ((0, 0), (0, 1), (0, 0)))[:, 1:, :]
    if hidden_top is not None:
        grass_mask[:, -1, :] &= ~hidden_top

    stone_variants = (
        stone, "minecraft:andesite",
        "minecraft:mossy_cobblestone", "minecraft:moss_block",
    )
    surface_noise = patch_noise((pod.shape[0], pod.shape[2]), PATCH_CELL, 6)
    for x, y, z in np.argwhere(pod):
        if grass_mask[x, y, z]:
            material = (
                pick_palette(*ground, int(surface_noise[x, z] * 255)) if ground else grass
            )
        elif surface_dist[x, y, z] <= soil_depth:
            material = "minecraft:coarse_dirt" if hash3(x, y, z, 1) < 60 else dirt
        else:
            patch = hash3(x // STONE_PATCH, y // STONE_PATCH, z // STONE_PATCH, 2)
            material = stone_variants[patch % len(stone_variants)]
        yield (int(x), int(y), int(z)), material


def vine_blocks(pod, density, max_length, center=None, lean_angle=None, lean_boost=2.0):
    if density <= 0:
        return
    overhang = pod.copy()
    overhang[:, 1:, :] &= ~pod[:, :-1, :]
    overhang[:, 0, :] = False
    lean_rad = math.radians(lean_angle) if lean_angle else None
    for x, y, z in np.argwhere(overhang):
        local_density = density
        if lean_rad is not None and center is not None:
            angle = math.atan2(z - center[1], x - center[0])
            alignment = max(0.0, math.cos(angle - lean_rad))
            local_density = min(1.0, density * (1 + lean_boost * alignment))
        if hash3(x, y, z, 3) >= int(local_density * 255):
            continue
        anchor_y = y - 1
        if anchor_y < 0 or pod[x, anchor_y, z]:
            continue
        if hash3(x, y, z, 5) < 25:
            yield (int(x), int(anchor_y), int(z)), "minecraft:glow_lichen[up=true]"
            continue
        length = 1 + hash3(x, y, z, 4) % max_length
        segments = []
        for i in range(1, length + 1):
            py = y - i
            if py < 0 or pod[x, py, z]:
                break
            segments.append(py)
        for i, py in enumerate(segments):
            tip = i == len(segments) - 1
            material = (
                "minecraft:cave_vines[berries=false]" if tip
                else "minecraft:cave_vines_plant[berries=false]"
            )
            yield (int(x), int(py), int(z)), material


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src", help="enveloped Structure NBT")
    parser.add_argument("dst")
    parser.add_argument("--envelope-masks", required=True)
    parser.add_argument("--top-radius", type=float, default=2.0)
    parser.add_argument("--bulge", type=float, default=3.0)
    parser.add_argument("--smoothing", type=float, default=1.2)
    parser.add_argument("--rounding", type=float, default=1.5)
    parser.add_argument("--rounding-threshold", type=float, default=0.5)
    parser.add_argument("--soil-depth", type=int, default=3)
    parser.add_argument("--curve-amount", type=float, default=0.0)
    parser.add_argument("--curve-angle", type=float, default=0.0)
    parser.add_argument("--curve-twist", type=float, default=0.0)
    parser.add_argument("--max-depth", type=int)
    parser.add_argument("--roundness", type=float, default=0.0)
    parser.add_argument("--side-bulge", type=float, default=0.0)
    parser.add_argument("--vine-density", type=float, default=0.0)
    parser.add_argument("--vine-length", type=int, default=3)
    parser.add_argument("--torch-density", type=float, default=0.0)
    parser.add_argument("--torch-max-distance", type=float, default=6.0)
    parser.add_argument("--torch-rim-depth", type=int, default=1)
    parser.add_argument("--grass", default="minecraft:grass_block")
    parser.add_argument("--dirt", default="minecraft:dirt")
    parser.add_argument("--stone", default="minecraft:stone")
    parser.add_argument("--masks", help="optional compressed NumPy debug file")
    args = parser.parse_args()

    src = Structure(args.src)
    masks = np.load(args.envelope_masks)
    envelope = masks["envelope"]
    base_y = int(masks["base_y"])
    if envelope.shape != src.size:
        parser.error("envelope masks do not match the source NBT")

    raw_footprint = base_footprint(envelope, base_y)
    if "glass_dome" in masks and masks["glass_dome"].any():
        glass_ring = masks["glass_dome"][:, base_y, :]
        raw_footprint = ndimage.binary_fill_holes(
            closing(raw_footprint | glass_ring, 2.0),
        )
    if min(args.top_radius, args.bulge, args.rounding) < 0:
        parser.error("radii must be non-negative")
    if args.smoothing < 0 or args.side_bulge < 0 or args.curve_amount < 0:
        parser.error("smoothing, side bulge and curve amount must be non-negative")
    if args.roundness < 0:
        parser.error("--roundness must be non-negative")
    if args.max_depth is not None and args.max_depth < 2:
        parser.error("--max-depth must be at least 2")
    if args.vine_length < 1:
        parser.error("--vine-length must be positive")
    if args.soil_depth < 0:
        parser.error("--soil-depth must be non-negative")
    if not 0 <= args.vine_density <= 1 or not 0 <= args.torch_density <= 1:
        parser.error("densities must be between 0 and 1")
    if args.torch_max_distance <= 0 or args.torch_rim_depth < 0:
        parser.error("torch max distance must be positive and rim depth non-negative")
    if not 0 < args.rounding_threshold < 1:
        parser.error("rounding threshold must be between 0 and 1")

    ground = ground_palette(src, raw_footprint, base_y)

    margin = math.ceil(
        args.top_radius + args.bulge + 2 * args.rounding + 2 * args.smoothing
        + args.curve_amount + args.side_bulge
    ) + 2
    raw_footprint = np.pad(raw_footprint, margin)
    footprint = rounded_footprint(
        raw_footprint, args.rounding, args.rounding_threshold,
    )
    inradius = inradius_of(footprint)
    depth = pod_depth(inradius, args.top_radius, args.bulge, args.max_depth)
    profile = radius_profile(inradius, args.top_radius, args.bulge, depth)
    offsets = curve_offsets(depth, args.curve_amount, args.curve_angle, args.curve_twist)
    pod = build_pod(
        footprint, base_y, depth, profile, args.smoothing, offsets, args.roundness,
        args.side_bulge,
    )

    pod_xz = np.argwhere(pod.any(axis=1))
    x0 = min(margin, int(pod_xz[:, 0].min()))
    z0 = min(margin, int(pod_xz[:, 1].min()))
    x1 = max(margin + src.size[0] - 1, int(pod_xz[:, 0].max()))
    z1 = max(margin + src.size[2] - 1, int(pod_xz[:, 1].max()))
    pod = pod[x0:x1 + 1, :, z0:z1 + 1]
    footprint = footprint[x0:x1 + 1, z0:z1 + 1]
    raw_footprint = raw_footprint[x0:x1 + 1, z0:z1 + 1]

    shift = (margin - x0, depth, margin - z0)
    size = (pod.shape[0], src.size[1] + depth, pod.shape[2])
    pod_center = np.argwhere(raw_footprint).mean(axis=0)
    block_count = save_structure(
        src, args.dst, size, shift,
        itertools.chain(
            pod_blocks(
                pod, args.soil_depth, args.grass, args.dirt, args.stone,
                raw_footprint, ground,
            ),
            vine_blocks(
                pod, args.vine_density, args.vine_length,
                pod_center, args.curve_angle,
            ),
            pod_torch_blocks(
                pod, raw_footprint, args.torch_density, args.torch_max_distance,
                args.torch_rim_depth,
            ),
        ),
    )

    if args.masks:
        with open(args.masks, "wb") as output:
            np.savez_compressed(
                output, raw_footprint=raw_footprint, footprint=footprint,
                pod=pod, profile=profile,
                shift=np.asarray(shift), base_y=base_y + depth,
            )

    ground_names = ", ".join(ground[0]) if ground else "none"
    print(f"size={size} blocks={block_count} pod={int(pod.sum())} ground=[{ground_names}]")
    print(
        f"footprint={int(footprint.sum())} depth={depth} "
        f"radius={profile[0]:.1f}->{profile.max():.1f}->{profile[-1]:.1f}"
    )


if __name__ == "__main__":
    main()
