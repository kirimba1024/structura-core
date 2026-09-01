#!/usr/bin/env python3
"""Cut sealed door sockets into a glass dome's own contour. Closed doors
block water on their own, so the structure is a self-sufficient, sealed
underwater room with no dependency on anything else ever being built."""
import argparse

import sys

import numpy as np

from .nbt import AIR_NAMES, Structure, save_structure

AXIS = {"west": (0, -1), "east": (0, 1), "north": (2, -1), "south": (2, 1)}
HINGE = {"west": "left", "east": "left", "north": "left", "south": "left"}
FRAME_SEARCH_RADIUS = 8


def find_wall(src, center, axis, sign, size):
    pos = center[axis]
    while 0 <= pos < size[axis]:
        cell = list(center)
        cell[axis] = pos
        if tuple(cell) not in src.present:
            return pos
        pos += sign
    return pos


def is_solid(src, pos):
    index = src.present.get(tuple(pos))
    return index is not None and src.palette[index] not in AIR_NAMES


def frame_positions(door_pos, perp):
    up = tuple(v + (1 if i == 1 else 0) for i, v in enumerate(door_pos))
    sill = tuple(v - (1 if i == 1 else 0) for i, v in enumerate(door_pos))
    sides = []
    for level in (door_pos, up):
        for d in (-1, 1):
            side = list(level)
            side[perp] += d
            sides.append(tuple(side))
    return up, sill, sides


def find_wall_at_base(src, anchor, axis, sign, size, perp):
    for radius in range(FRAME_SEARCH_RADIUS + 1):
        for dp in ({0} if radius == 0 else {-radius, radius}):
            candidate = list(anchor)
            candidate[perp] += dp
            if not 0 <= candidate[perp] < size[perp]:
                continue
            wall = find_wall(src, candidate, axis, sign, size)
            door_pos = list(candidate)
            door_pos[axis] = wall - sign
            return tuple(door_pos)
    return tuple(anchor)


def door_state(facing):
    lower = f"minecraft:oak_door[half=lower,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    upper = f"minecraft:oak_door[half=upper,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    return lower, upper


def auto_center(pod_masks):
    """Any point at floor height, roughly inside the footprint, works --
    doors are cut by shooting rays out to the shell, not by a meaningful
    building center. base_y/raw_footprint are already computed by
    terrain_pod for this exact structure, so no per-asset input is needed."""
    masks = np.load(pod_masks)
    base_y = int(masks["base_y"])
    footprint = masks["raw_footprint"]
    xs, zs = np.nonzero(footprint)
    return int(round(xs.mean())), base_y, int(round(zs.mean()))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--center-x", type=int)
    parser.add_argument("--center-y", type=int)
    parser.add_argument("--center-z", type=int)
    parser.add_argument(
        "--pod-masks",
        help="terrain_pod's --masks npz; derives the center automatically "
             "(base_y + footprint centroid) when --center-x/y/z are omitted",
    )
    parser.add_argument(
        "--directions", default="north,south,east,west",
        help="comma-separated subset of north,south,east,west",
    )
    args = parser.parse_args()

    directions = [d.strip() for d in args.directions.split(",") if d.strip()]
    for d in directions:
        if d not in AXIS:
            parser.error(f"unknown direction {d!r}; choose from {sorted(AXIS)}")

    manual = (args.center_x, args.center_y, args.center_z)
    if all(v is not None for v in manual):
        center = manual
    elif any(v is not None for v in manual):
        parser.error("--center-x/y/z must be given together, or not at all")
    elif args.pod_masks:
        center = auto_center(args.pod_masks)
    else:
        parser.error("need --center-x/y/z or --pod-masks")

    src = Structure(args.src)
    size = src.size

    replacements = []
    doors = []
    for facing in directions:
        axis, sign = AXIS[facing]
        perp = 2 - axis
        door_pos = find_wall_at_base(src, center, axis, sign, size, perp)
        upper_pos, sill, sides = frame_positions(door_pos, perp)
        patched = 0
        for pos in (sill, *sides):
            if not all(0 <= v < limit for v, limit in zip(pos, size)):
                continue
            if not is_solid(src, pos):
                replacements.append((pos, "minecraft:glass"))
                patched += 1
        if patched:
            print(f"forced glass frame around {facing} door: {patched} block(s)", file=sys.stderr)
        lower, upper = door_state(facing)
        replacements.append((door_pos, lower))
        replacements.append((upper_pos, upper))
        doors.append((door_pos, facing))

    save_structure(src, args.dst, size, replacements=replacements)
    for pos, facing in doors:
        print(f"door {facing}: {pos}")


if __name__ == "__main__":
    main()
