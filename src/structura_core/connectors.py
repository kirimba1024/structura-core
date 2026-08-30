#!/usr/bin/env python3
"""Build standardized Jigsaw adapters and route pieces."""
import argparse
import json
import math
from pathlib import Path

from amulet_nbt import CompoundTag, IntTag, ListTag, NamedTag, StringTag

from .version import DATA_VERSION

PORT_ID = "structura:route_port"
WIDTH = 7
HEIGHT = 6

MATERIALS = {
    "surface": ("minecraft:stone_bricks", "minecraft:dirt_path", "minecraft:oak_fence", "minecraft:stone_bricks"),
    "cave": ("minecraft:deepslate_bricks", "minecraft:polished_deepslate", "minecraft:iron_bars", "minecraft:deepslate_bricks"),
    "sky": ("minecraft:stripped_spruce_log", "minecraft:spruce_planks", "minecraft:spruce_fence", "minecraft:stripped_spruce_log"),
    "underwater": ("minecraft:oxidized_cut_copper", "minecraft:oxidized_cut_copper", "minecraft:sea_lantern", "minecraft:glass"),
}


def state(name, **properties):
    return name, tuple(sorted((key, str(value).lower()) for key, value in properties.items()))


class Piece:
    def __init__(self, length):
        self.size = (WIDTH, HEIGHT, length)
        self.blocks = {}
        self.nbt = {}

    def put(self, pos, block, nbt=None):
        self.blocks[pos] = block if isinstance(block, tuple) else state(block)
        if nbt is not None:
            self.nbt[pos] = nbt

    def port(self, z, facing, pool):
        pos = (WIDTH // 2, 1, z)
        self.put(pos, state("minecraft:jigsaw", orientation=f"{facing}_up"), {
            "id": "minecraft:jigsaw",
            "name": PORT_ID,
            "target": PORT_ID,
            "pool": pool,
            "final_state": "minecraft:air",
            "joint": "aligned",
        })

    def save(self, path):
        palette = []
        indices = {}
        blocks = ListTag()
        for pos in sorted(self.blocks):
            block = self.blocks[pos]
            if block not in indices:
                indices[block] = len(palette)
                name, properties = block
                raw = CompoundTag({"Name": StringTag(name)})
                if properties:
                    raw["Properties"] = CompoundTag({
                        key: StringTag(value) for key, value in properties
                    })
                palette.append(raw)
            raw = CompoundTag({
                "pos": ListTag([IntTag(value) for value in pos]),
                "state": IntTag(indices[block]),
            })
            if pos in self.nbt:
                raw["nbt"] = CompoundTag({
                    key: StringTag(value) for key, value in self.nbt[pos].items()
                })
            blocks.append(raw)
        root = CompoundTag({
            "DataVersion": IntTag(DATA_VERSION),
            "size": ListTag([IntTag(value) for value in self.size]),
            "palette": ListTag(palette),
            "blocks": blocks,
            "entities": ListTag(),
        })
        path.parent.mkdir(parents=True, exist_ok=True)
        NamedTag(root, "").save_to(str(path))


TUBE_CX = (WIDTH - 1) / 2
TUBE_HALF_WIDTH = 2.0
TUBE_BODY_TOP = 3
WALL = 1.0


def _half_width_at(y, half_width):
    if y <= TUBE_BODY_TOP:
        return half_width
    dy = y - TUBE_BODY_TOP
    return math.sqrt(max(half_width ** 2 - dy ** 2, 0.0))


def tube_cell(x, y):
    dx = abs(x - TUBE_CX)
    if dx <= _half_width_at(y, TUBE_HALF_WIDTH):
        return "air"
    if dx <= _half_width_at(y, TUBE_HALF_WIDTH + WALL):
        return "wall"
    return None


def square_slice(piece, profile, z, frame, floor, trim):
    for x in range(1, WIDTH - 1):
        piece.put((x, 0, z), floor)
        for y in range(1, 5):
            piece.put((x, y, z), "minecraft:air")
    piece.put((1, 1, z), trim)
    piece.put((WIDTH - 2, 1, z), trim)
    for y in range(1, 5):
        piece.put((1, y, z), frame)
        piece.put((WIDTH - 2, y, z), frame)
    for x in range(1, WIDTH - 1):
        piece.put((x, 4, z), frame)


def open_slice(piece, z, floor, trim):
    for x in range(1, WIDTH - 1):
        piece.put((x, 0, z), floor)
    piece.put((1, 1, z), trim)
    piece.put((WIDTH - 2, 1, z), trim)


def shell(piece, profile, *, cap=False):
    frame, floor, trim, wall = MATERIALS[profile]
    end = piece.size[2] - 1
    round_tube = profile in ("cave", "underwater")
    for z in range(piece.size[2]):
        if z in (0, end):
            square_slice(piece, profile, z, frame, floor, trim)
            continue
        if not round_tube:
            open_slice(piece, z, floor, trim)
            continue
        for x in range(WIDTH):
            if tube_cell(x, 1) == "air":
                piece.put((x, 0, z), floor)
        for y in range(1, HEIGHT):
            for x in range(WIDTH):
                cell = tube_cell(x, y)
                if cell == "air":
                    piece.put((x, y, z), "minecraft:air")
                elif cell == "wall":
                    piece.put((x, y, z), wall)
    if profile == "sky":
        for x in (1, WIDTH - 2):
            piece.put((x, 4, end // 2), "minecraft:lantern")
    elif profile == "cave":
        for x in (1, WIDTH - 2):
            piece.put((x, 1, end // 2), "minecraft:lantern")
    elif profile == "underwater":
        for x in (1, WIDTH - 2):
            piece.put((x, 1, end // 2), trim)
    if cap:
        for x in range(1, WIDTH - 1):
            for y in range(1, 5):
                piece.put((x, y, end), frame)
        piece.put((WIDTH // 2, 2, end), trim)


def make_piece(profile, kind):
    length = {"adapter": 7, "straight": 9, "cap": 5}[kind]
    piece = Piece(length)
    shell(piece, profile, cap=kind == "cap")
    piece.port(0, "north", "minecraft:empty")
    if kind != "cap":
        piece.port(length - 1, "south", f"structura:routes/{profile}")
    return piece


def pool(location, weight=1):
    return {
        "weight": weight,
        "element": {
            "element_type": "minecraft:single_pool_element",
            "location": location,
            "processors": "minecraft:empty",
            "projection": "rigid",
        },
    }


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2) + "\n")


def build(root):
    structures = root / "structure" / "connectors"
    pools = root / "worldgen" / "template_pool" / "connectors"
    routes = root / "worldgen" / "template_pool" / "routes"
    for profile in MATERIALS:
        for kind in ("adapter", "straight", "cap"):
            make_piece(profile, kind).save(structures / f"{profile}_{kind}.nbt")
        write_json(pools / f"{profile}.json", {
            "fallback": "minecraft:empty",
            "elements": [pool(f"structura:connectors/{profile}_adapter")],
        })
        write_json(routes / f"{profile}.json", {
            "fallback": "minecraft:empty",
            "elements": [
                pool(f"structura:connectors/{profile}_straight", 4),
                pool(f"structura:connectors/{profile}_cap", 1),
            ],
        })
    print(f"built {len(MATERIALS) * 3} pieces in {root}")
    print(f"port={PORT_ID} frame=5x5 clearance=3x3 floor_y=0")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root", type=Path,
        default=Path("sources/connectors/data/structura"),
        help="connectors are their own generated source, not build output "
             "-- tracked under sources/, copied into build/ at deploy",
    )
    args = parser.parse_args()
    build(args.data_root)


if __name__ == "__main__":
    main()
