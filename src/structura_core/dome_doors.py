#!/usr/bin/env python3
"""Cut sealed door sockets into a glass dome's own contour. Closed doors
block water on their own, so the structure is a self-sufficient, sealed
underwater room with no dependency on anything else ever being built."""
import argparse

from .nbt import Structure, save_structure

AXIS = {"west": (0, -1), "east": (0, 1), "north": (2, -1), "south": (2, 1)}
HINGE = {"west": "left", "east": "left", "north": "left", "south": "left"}


def find_wall(src, center, axis, sign, size):
    pos = center[axis]
    while 0 <= pos < size[axis]:
        cell = list(center)
        cell[axis] = pos
        if tuple(cell) not in src.present:
            return pos
        pos += sign
    return pos


def door_state(facing):
    lower = f"minecraft:oak_door[half=lower,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    upper = f"minecraft:oak_door[half=upper,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    return lower, upper


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--center-x", type=int, required=True)
    parser.add_argument("--center-y", type=int, required=True)
    parser.add_argument("--center-z", type=int, required=True)
    parser.add_argument(
        "--directions", default="north,south,east,west",
        help="comma-separated subset of north,south,east,west",
    )
    args = parser.parse_args()

    directions = [d.strip() for d in args.directions.split(",") if d.strip()]
    for d in directions:
        if d not in AXIS:
            parser.error(f"unknown direction {d!r}; choose from {sorted(AXIS)}")

    src = Structure(args.src)
    size = src.size
    center = (args.center_x, args.center_y, args.center_z)

    replacements = []
    doors = []
    for facing in directions:
        axis, sign = AXIS[facing]
        wall = find_wall(src, center, axis, sign, size)
        door_pos = list(center)
        door_pos[axis] = wall - sign
        door_pos = tuple(door_pos)
        lower, upper = door_state(facing)
        upper_pos = tuple(
            v + (1 if i == 1 else 0) for i, v in enumerate(door_pos)
        )
        replacements.append((door_pos, lower))
        replacements.append((upper_pos, upper))
        doors.append((door_pos, facing))

    save_structure(src, args.dst, size, replacements=replacements)
    for pos, facing in doors:
        print(f"door {facing}: {pos}")


if __name__ == "__main__":
    main()
