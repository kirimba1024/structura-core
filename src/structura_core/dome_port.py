#!/usr/bin/env python3
"""Cut sealed door sockets into a glass dome's own contour, each wired as a
structura:route_port Jigsaw. Closed doors block water, so this is safe with
or without anything ever connecting -- no separate village-only variant.

Also lays a room-floor path network from the building's own ground-floor
door(s) to each dome door, since the fitted bubble leaves real open floor
between the building and the glass -- same hub-and-spokes idea as
house_port.py's --auto-network, but flat (fixed Y, no pod to follow) and
lit with lanterns instead of torches, which don't survive underwater."""
import argparse

import numpy as np
from amulet_nbt import (
    CompoundTag, IntTag, ListTag, NamedTag, StringTag, load as load_nbt,
)
from scipy import ndimage

from .check_doors import find_doors
from .nbt import Structure, save_structure
from .paths import hash3, jittered_route, merge_cells, wall_mask

AXIS = {"west": (0, -1), "east": (0, 1), "north": (2, -1), "south": (2, 1)}
HINGE = {"west": "left", "east": "left", "north": "left", "south": "left"}
FRAME = "minecraft:glass"


def find_wall(src, center, axis, sign, size):
    pos = center[axis]
    while 0 <= pos < size[axis]:
        cell = list(center)
        cell[axis] = pos
        if tuple(cell) not in src.present:
            return pos
        pos += sign
    return pos


def room_path_cells(
    protect, hub_xz, target_xz, y, floor_block, salt, index,
    light_block=None, light_interval=5,
):
    route = jittered_route(hub_xz, target_xz, protect.shape, salt, index)
    prev = None
    for i, (x, z) in enumerate(route):
        if protect[x, z]:
            prev = (x, z)
            continue
        yield (x, y, z), floor_block
        yield (x, y + 1, z), "minecraft:air"
        yield (x, y + 2, z), "minecraft:air"
        if light_block and light_interval > 0 and i % light_interval == 0 and prev is not None:
            dx, dz = x - prev[0], z - prev[1]
            px, pz = -dz, dx
            if hash3(x, z, index, salt) % 2:
                px, pz = -px, -pz
            tx, tz = x + px, z + pz
            if 0 <= tx < protect.shape[0] and 0 <= tz < protect.shape[1] and not protect[tx, tz]:
                yield (tx, y + 1, tz), light_block
        prev = (x, z)


def door_state(facing):
    lower = f"minecraft:oak_door[half=lower,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    upper = f"minecraft:oak_door[half=upper,facing={facing},hinge={HINGE[facing]},open=false,powered=false]"
    return lower, upper


def place_jigsaw(path, pos, facing, pool):
    nbt = load_nbt(path, compressed=True)
    root = nbt.compound
    palette = root["palette"]
    block = CompoundTag({
        "Name": StringTag("minecraft:jigsaw"),
        "Properties": CompoundTag({"orientation": StringTag(f"{facing}_up")}),
    })
    index = len(palette)
    palette.append(block)
    for b in root["blocks"]:
        if tuple(int(v.py_data) for v in b["pos"]) == pos:
            b["state"] = IntTag(index)
            b["nbt"] = CompoundTag({
                "id": StringTag("minecraft:jigsaw"),
                "name": StringTag("structura:route_port"),
                "target": StringTag("structura:route_port"),
                "pool": StringTag(pool),
                "final_state": StringTag(
                    f"minecraft:oak_door[half=lower,facing={facing},"
                    f"hinge={HINGE[facing]},open=false,powered=false]",
                ),
                "joint": StringTag("aligned"),
            })
            break
    else:
        raise ValueError(f"no block entry at {pos} to convert to a jigsaw")
    NamedTag(root, "").save_to(path)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--center-x", type=int, required=True)
    parser.add_argument("--center-y", type=int, required=True)
    parser.add_argument("--center-z", type=int, required=True)
    parser.add_argument("--pool", default="structura:connectors/underwater")
    parser.add_argument(
        "--directions", default="north,south,east,west",
        help="comma-separated subset of north,south,east,west",
    )
    parser.add_argument("--no-paths", action="store_true")
    parser.add_argument("--floor", default="minecraft:sand")
    parser.add_argument("--light", default="minecraft:lantern")
    parser.add_argument("--light-interval", type=int, default=5)
    parser.add_argument("--salt", type=int, default=1)
    args = parser.parse_args()

    directions = [d.strip() for d in args.directions.split(",") if d.strip()]
    for d in directions:
        if d not in AXIS:
            parser.error(f"unknown direction {d!r}; choose from {sorted(AXIS)}")

    src = Structure(args.src)
    size = src.size
    center = (args.center_x, args.center_y, args.center_z)

    merged = {}
    ports = []
    for facing in directions:
        axis, sign = AXIS[facing]
        perp = 2 - axis
        wall = find_wall(src, center, axis, sign, size)
        door_pos = list(center)
        door_pos[axis] = wall - sign
        door_pos = tuple(door_pos)
        lower, upper = door_state(facing)
        upper_pos = tuple(
            v + (1 if i == 1 else 0) for i, v in enumerate(door_pos)
        )
        merge_cells(merged, [(door_pos, lower), (upper_pos, upper)])
        reinforcement = []
        for dd in (0, 1, 2):
            depth = list(door_pos)
            depth[axis] += dd * sign
            for dw in (-1, 1):
                for dy in (0, 1):
                    post = list(depth)
                    post[perp] += dw
                    post[1] += dy
                    reinforcement.append(tuple(post))
            for dw in (-1, 0, 1):
                lintel = list(depth)
                lintel[perp] += dw
                lintel[1] += 2
                reinforcement.append(tuple(lintel))
            sill = list(depth)
            sill[1] -= 1
            reinforcement.append(tuple(sill))
        for pos in reinforcement:
            if src.is_air(pos):
                merge_cells(merged, [(pos, FRAME)])
        ports.append((door_pos, facing))

    if not args.no_paths and ports:
        floor_y = center[1]
        protect = wall_mask(src, floor_y + 1, floor_y + 6, (size[0], size[2]))
        protect = ndimage.binary_dilation(protect, iterations=1)
        doors = find_doors(src)
        ground_y = min((y for (_x, y, _z), _f, _v in doors), default=None)
        door_nodes = [
            (x + vx, y, z + vz) for (x, y, z), _f, (vx, vy, vz) in doors
            if ground_y is not None and y <= ground_y + 3
        ]
        hub_xz = (door_nodes[0][0], door_nodes[0][2]) if door_nodes else (center[0], center[2])
        for i, other in enumerate(door_nodes[1:]):
            merge_cells(
                merged,
                room_path_cells(
                    protect, hub_xz, (other[0], other[2]), floor_y, args.floor,
                    args.salt, 100 + i, args.light, args.light_interval,
                ),
            )
        for index, (door_pos, facing) in enumerate(ports):
            merge_cells(
                merged,
                room_path_cells(
                    protect, hub_xz, (door_pos[0], door_pos[2]), floor_y, args.floor,
                    args.salt, index, args.light, args.light_interval,
                ),
            )

    replacements = list(merged.items())
    save_structure(src, args.dst, size, replacements=replacements)
    for pos, facing in ports:
        place_jigsaw(args.dst, pos, facing, args.pool)
    for pos, facing in ports:
        print(f"door+port {facing}: {pos}")


if __name__ == "__main__":
    main()
