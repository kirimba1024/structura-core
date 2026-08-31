#!/usr/bin/env python3
"""Cut sealed door sockets into a glass dome's own contour, each wired as a
structura:route_port Jigsaw. Closed doors block water, so this is safe with
or without anything ever connecting -- no separate village-only variant."""
import argparse

from amulet_nbt import (
    CompoundTag, IntTag, ListTag, NamedTag, StringTag, load as load_nbt,
)
from .nbt import Structure, save_structure

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
    args = parser.parse_args()

    directions = [d.strip() for d in args.directions.split(",") if d.strip()]
    for d in directions:
        if d not in AXIS:
            parser.error(f"unknown direction {d!r}; choose from {sorted(AXIS)}")

    src = Structure(args.src)
    size = src.size
    center = (args.center_x, args.center_y, args.center_z)

    replacements = []
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
        replacements.append((door_pos, lower))
        replacements.append((upper_pos, upper))
        reinforcement = []
        for dw in (-1, 1):
            for dy in (0, 1):
                post = list(door_pos)
                post[perp] += dw
                post[1] += dy
                reinforcement.append(tuple(post))
        for dw in (-1, 0, 1):
            lintel = list(door_pos)
            lintel[perp] += dw
            lintel[1] += 2
            reinforcement.append(tuple(lintel))
        sill = list(door_pos)
        sill[1] -= 1
        reinforcement.append(tuple(sill))
        for pos in reinforcement:
            if src.is_air(pos):
                replacements.append((pos, FRAME))
        ports.append((door_pos, facing))

    save_structure(src, args.dst, size, replacements=replacements)
    for pos, facing in ports:
        place_jigsaw(args.dst, pos, facing, args.pool)
    for pos, facing in ports:
        print(f"door+port {facing}: {pos}")


if __name__ == "__main__":
    main()
