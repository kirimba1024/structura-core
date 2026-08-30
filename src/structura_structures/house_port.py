#!/usr/bin/env python3
"""Carve a corridor from a house door out to the file boundary and place a
structura:route_port Jigsaw there, per docs/connectors.md."""
import argparse

from amulet_nbt import (
    CompoundTag, IntTag, ListTag, NamedTag, StringTag, load as load_nbt,
)
from .nbt import Structure, save_structure

AXIS = {"west": (0, -1), "east": (0, 1), "north": (2, -1), "south": (2, 1)}
FLOOR = "minecraft:dirt_path"


def corridor_cells(axis, sign, boundary, cavern_edge, floor_y, center):
    lo, hi = sorted((boundary, cavern_edge - sign))
    for pos in range(lo, hi + 1):
        for w in (-1, 0, 1):
            for h in (0, 1, 2):
                cell = [0, 0, 0]
                cell[axis] = pos
                cell[1] = floor_y + h
                cell[2 - axis] = center + w
                yield tuple(cell), "minecraft:air"
            floor = [0, 0, 0]
            floor[axis] = pos
            floor[1] = floor_y - 1
            floor[2 - axis] = center + w
            yield tuple(floor), FLOOR


def find_cavern_edge(src, door_pos, axis, sign, size):
    pos = door_pos[axis]
    edge = pos
    while 0 <= pos < size[axis]:
        cell = list(door_pos)
        cell[axis] = pos
        if tuple(cell) not in src.present:
            return pos
        pos += sign
        edge = pos
    return edge


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
                "final_state": StringTag("minecraft:air"),
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
    parser.add_argument("--door-x", type=int, required=True)
    parser.add_argument("--door-y", type=int, required=True)
    parser.add_argument("--door-z", type=int, required=True)
    parser.add_argument("--facing", choices=AXIS, required=True)
    parser.add_argument("--pool", default="structura:connectors/surface")
    args = parser.parse_args()

    axis, sign = AXIS[args.facing]
    perp = 2 - axis
    door_pos = (args.door_x, args.door_y, args.door_z)
    center = door_pos[perp]

    src = Structure(args.src)
    size = src.size
    boundary = 0 if sign < 0 else size[axis] - 1
    cavern_edge = find_cavern_edge(src, door_pos, axis, sign, size)

    additions = list(
        corridor_cells(axis, sign, boundary, cavern_edge, args.door_y, center),
    )
    save_structure(src, args.dst, size, replacements=additions)

    port_pos = [0, 0, 0]
    port_pos[axis] = boundary
    port_pos[1] = args.door_y
    port_pos[perp] = center
    port_pos = tuple(port_pos)
    place_jigsaw(args.dst, port_pos, args.facing, args.pool)

    print(f"corridor {args.facing}: cavern_edge={cavern_edge} boundary={boundary}")
    print(f"port at {port_pos} pool={args.pool}")


if __name__ == "__main__":
    main()
