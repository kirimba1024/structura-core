#!/usr/bin/env python3
"""Carve a corridor from a house door out to the file boundary and place a
structura:route_port Jigsaw there, per docs/connectors.md.

--auto-network replaces the single manual door with a yard path network:
a hub near the building (at its doors, if any are detected, else just the
nearest yard cell to the footprint) spoked out to one randomized exit per
cardinal side, each carved down to the pod's own surface and out to the
file boundary."""
import argparse

import numpy as np
from amulet_nbt import (
    CompoundTag, IntTag, ListTag, NamedTag, StringTag, load as load_nbt,
)
from scipy import ndimage

from .check_doors import find_doors
from .nbt import Structure, save_structure

AXIS = {"west": (0, -1), "east": (0, 1), "north": (2, -1), "south": (2, 1)}


def hash3(x, y, z, salt):
    return (x * 73856093 ^ y * 19349663 ^ z * 83492791 ^ salt) & 0xff


def column_top(pod, x, z):
    idx = np.nonzero(pod[x, :, z])[0]
    return int(idx.max()) if idx.size else None


def find_side_edge(pod2d, axis, sign, p):
    line = pod2d[:, p] if axis == 0 else pod2d[p, :]
    idx = np.nonzero(line)[0]
    if idx.size == 0:
        return None
    return int(idx.max()) if sign > 0 else int(idx.min())


def pick_anchor(pod, pod2d, axis, sign, perp_lo, perp_hi, salt, index, attempts=12):
    span = max(1, perp_hi - perp_lo + 1)
    for attempt in range(attempts):
        p = perp_lo + hash3(index, attempt, 0, salt) % span
        edge = find_side_edge(pod2d, axis, sign, p)
        if edge is None:
            continue
        pos = [0, 0, 0]
        pos[axis] = edge
        pos[2 - axis] = p
        y = column_top(pod, pos[0], pos[2])
        if y is None:
            continue
        pos[1] = y
        return tuple(pos)
    return None


def line_cells(a, b):
    x0, z0 = a
    x1, z1 = b
    dx, dz = abs(x1 - x0), abs(z1 - z0)
    sx = 1 if x1 > x0 else -1
    sz = 1 if z1 > z0 else -1
    err = dx - dz
    x, z = x0, z0
    cells = []
    while True:
        cells.append((x, z))
        if x == x1 and z == z1:
            break
        e2 = 2 * err
        if e2 > -dz:
            err -= dz
            x += sx
        if e2 < dx:
            err += dx
            z += sz
    return cells


def path_cells(pod, protect, hub_xz, anchor_xz, floor_block, salt, index, torch_block=None, torch_interval=5):
    mx = (hub_xz[0] + anchor_xz[0]) // 2 + (hash3(index, 1, 1, salt) % 7 - 3)
    mz = (hub_xz[1] + anchor_xz[1]) // 2 + (hash3(index, 2, 2, salt) % 7 - 3)
    mx = max(0, min(pod.shape[0] - 1, mx))
    mz = max(0, min(pod.shape[2] - 1, mz))
    route = line_cells(hub_xz, (mx, mz)) + line_cells((mx, mz), anchor_xz)
    prev = None
    for i, (x, z) in enumerate(route):
        if protect[x, z]:
            prev = (x, z)
            continue
        y = column_top(pod, x, z)
        if y is None:
            prev = (x, z)
            continue
        yield (x, y, z), floor_block
        yield (x, y + 1, z), "minecraft:air"
        yield (x, y + 2, z), "minecraft:air"
        if torch_block and torch_interval > 0 and i % torch_interval == 0 and prev is not None:
            dx, dz = x - prev[0], z - prev[1]
            px, pz = -dz, dx
            if hash3(x, z, index, salt) % 2:
                px, pz = -px, -pz
            tx, tz = x + px, z + pz
            if 0 <= tx < pod.shape[0] and 0 <= tz < pod.shape[2] and not protect[tx, tz]:
                ty = column_top(pod, tx, tz)
                if ty is not None:
                    yield (tx, ty + 1, tz), torch_block
        prev = (x, z)


AIR = "minecraft:air"


def merge_cells(merged, cells):
    for pos, state in cells:
        current = merged.get(pos)
        if current is None or current == state:
            merged[pos] = state
        elif current == AIR:
            merged[pos] = state
        # else: keep the existing solid state -- a solid block always wins
        # over air, so two crossing corridors never eat a hole in each
        # other's floor.


def build_network(
    src, pod, raw_footprint, floor_block, embankment_depth, salt,
    torch_block=None, torch_interval=5, make_ports=True,
):
    pod2d = pod.any(axis=1)
    protect = ndimage.binary_dilation(raw_footprint, iterations=2)

    doors = find_doors(src)
    ground_y = min((y for (_x, y, _z), _facing, _vec in doors), default=None)
    door_nodes = [
        (x + vx, y, z + vz) for (x, y, z), _facing, (vx, vy, vz) in doors
        if ground_y is not None and y <= ground_y + 3
    ]
    if door_nodes:
        hub = door_nodes[0]
    else:
        coords = np.argwhere(raw_footprint)
        center = coords.mean(axis=0)
        yard = pod2d & ~protect
        yc = np.argwhere(yard)
        if len(yc):
            d = np.hypot(yc[:, 0] - center[0], yc[:, 1] - center[1])
            hx, hz = (int(v) for v in yc[np.argmin(d)])
        else:
            hx, hz = int(center[0]), int(center[1])
        hy = column_top(pod, hx, hz)
        hub = (hx, hy if hy is not None else 0, hz)

    merged = {}
    for other in door_nodes[1:]:
        merge_cells(
            merged,
            path_cells(
                pod, protect, (hub[0], hub[2]), (other[0], other[2]), floor_block,
                salt, 100, torch_block, torch_interval,
            ),
        )

    fb_x = np.nonzero(raw_footprint.any(axis=1))[0]
    fb_z = np.nonzero(raw_footprint.any(axis=0))[0]
    x_lo, x_hi = int(fb_x.min()), int(fb_x.max())
    z_lo, z_hi = int(fb_z.min()), int(fb_z.max())
    pad = 4

    def shrink(lo, hi, limit, frac=0.15):
        lo = max(0, lo - pad)
        hi = min(limit, hi + pad)
        span = hi - lo
        return lo + int(span * frac), hi - int(span * frac)

    z_side_lo, z_side_hi = shrink(z_lo, z_hi, pod.shape[2] - 1)
    x_side_lo, x_side_hi = shrink(x_lo, x_hi, pod.shape[0] - 1)
    sides = [
        ("west", 0, -1, z_side_lo, z_side_hi),
        ("east", 0, 1, z_side_lo, z_side_hi),
        ("north", 2, -1, x_side_lo, x_side_hi),
        ("south", 2, 1, x_side_lo, x_side_hi),
    ]

    ports = []
    for index, (facing, axis, sign, lo, hi) in enumerate(sides):
        anchor = pick_anchor(pod, pod2d, axis, sign, lo, hi, salt, index)
        if anchor is None:
            continue
        merge_cells(
            merged,
            path_cells(
                pod, protect, (hub[0], hub[2]), (anchor[0], anchor[2]), floor_block,
                salt, index, torch_block, torch_interval,
            ),
        )
        if not make_ports:
            continue
        boundary = 0 if sign < 0 else pod.shape[axis] - 1
        cavern_edge = anchor[axis] + sign
        center = anchor[2 - axis]
        merge_cells(
            merged,
            corridor_cells(
                axis, sign, boundary, cavern_edge, anchor[1], center, floor_block,
                embankment_depth,
            ),
        )
        port_pos = [0, 0, 0]
        port_pos[axis] = boundary
        port_pos[1] = anchor[1]
        port_pos[2 - axis] = center
        ports.append((tuple(port_pos), facing))
    return list(merged.items()), ports


def corridor_cells(axis, sign, boundary, cavern_edge, floor_y, center, floor_block, embankment_depth):
    lo, hi = sorted((boundary, cavern_edge - sign))
    for pos in range(lo, hi + 1):
        for w in (-1, 0, 1):
            for h in (0, 1, 2):
                cell = [0, 0, 0]
                cell[axis] = pos
                cell[1] = floor_y + h
                cell[2 - axis] = center + w
                yield tuple(cell), "minecraft:air"
            for d in range(1, embankment_depth + 1):
                floor = [0, 0, 0]
                floor[axis] = pos
                floor[1] = floor_y - d
                floor[2 - axis] = center + w
                yield tuple(floor), floor_block


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
    parser.add_argument("--door-x", type=int)
    parser.add_argument("--door-y", type=int)
    parser.add_argument("--door-z", type=int)
    parser.add_argument("--facing", choices=AXIS)
    parser.add_argument("--pool", default="structura:connectors/surface")
    parser.add_argument("--floor", default="minecraft:dirt_path")
    parser.add_argument("--embankment-depth", type=int, default=6)
    parser.add_argument(
        "--auto-network", action="store_true",
        help="build a yard path network with up to 4 side exits instead of "
             "a single manual door corridor; requires --pod-masks",
    )
    parser.add_argument("--pod-masks", help="terrain_pod --masks debug file")
    parser.add_argument("--no-ports", action="store_true",
                         help="with --auto-network: paths and torches only, no jigsaw exits")
    parser.add_argument("--torch", default="minecraft:torch")
    parser.add_argument("--no-torches", action="store_true")
    parser.add_argument("--torch-interval", type=int, default=5)
    parser.add_argument("--salt", type=int, default=1)
    args = parser.parse_args()

    src = Structure(args.src)
    size = src.size

    if args.auto_network:
        if not args.pod_masks:
            parser.error("--auto-network requires --pod-masks")
        masks = np.load(args.pod_masks)
        pod = masks["pod"]
        raw_footprint = masks["raw_footprint"]
        if pod.shape[0] != size[0] or pod.shape[2] != size[2] or pod.shape[1] > size[1]:
            parser.error("pod masks do not match the source NBT")
        if pod.shape[1] != size[1]:
            padded = np.zeros(size, dtype=bool)
            padded[:, :pod.shape[1], :] = pod
            pod = padded
        if raw_footprint.shape != (size[0], size[2]):
            parser.error("pod masks do not match the source NBT")
        torch_block = None if args.no_torches else args.torch
        replacements, ports = build_network(
            src, pod, raw_footprint, args.floor, args.embankment_depth, args.salt,
            torch_block, args.torch_interval, make_ports=not args.no_ports,
        )
        save_structure(src, args.dst, size, replacements=replacements)
        for pos, facing in ports:
            place_jigsaw(args.dst, pos, facing, args.pool)
        for pos, facing in ports:
            print(f"port {facing}: {pos} pool={args.pool}")
        print(f"paths+torches placed, {len(ports)} exit(s)")
        return

    if None in (args.door_x, args.door_y, args.door_z, args.facing):
        parser.error("--door-x/--door-y/--door-z/--facing are required without --auto-network")

    axis, sign = AXIS[args.facing]
    perp = 2 - axis
    door_pos = (args.door_x, args.door_y, args.door_z)
    center = door_pos[perp]

    boundary = 0 if sign < 0 else size[axis] - 1
    cavern_edge = find_cavern_edge(src, door_pos, axis, sign, size)

    additions = list(
        corridor_cells(
            axis, sign, boundary, cavern_edge, args.door_y, center, args.floor,
            args.embankment_depth,
        ),
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
