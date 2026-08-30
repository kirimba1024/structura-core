#!/usr/bin/env python3
"""Write a worldgen/processor_list JSON for cosmetic block-state variation."""
import argparse
import itertools
import json
from pathlib import Path

PLAIN = [
    ("minecraft:cobblestone", [(0.25, "minecraft:mossy_cobblestone")]),
    ("minecraft:cobblestone_wall", [(0.25, "minecraft:mossy_cobblestone_wall")]),
    ("minecraft:stone_bricks", [
        (0.2, "minecraft:mossy_stone_bricks"),
        (0.15, "minecraft:cracked_stone_bricks"),
    ]),
    ("minecraft:stone_brick_wall", [(0.25, "minecraft:mossy_stone_brick_wall")]),
]
STAIRS = [
    ("minecraft:cobblestone_stairs", [(0.25, "minecraft:mossy_cobblestone_stairs")]),
    ("minecraft:stone_brick_stairs", [(0.25, "minecraft:mossy_stone_brick_stairs")]),
]
SLABS = [
    ("minecraft:cobblestone_slab", [(0.25, "minecraft:mossy_cobblestone_slab")]),
    ("minecraft:stone_brick_slab", [(0.25, "minecraft:mossy_stone_brick_slab")]),
]
STAIR_FACINGS = ("north", "south", "east", "west")
STAIR_HALVES = ("bottom", "top")
STAIR_SHAPES = ("straight", "inner_left", "inner_right", "outer_left", "outer_right")
SLAB_TYPES = ("bottom", "top")


def plain_rule(source, output, probability):
    return {
        "input_predicate": {
            "predicate_type": "minecraft:random_block_match",
            "block": source,
            "probability": probability,
        },
        "location_predicate": {"predicate_type": "minecraft:always_true"},
        "output_state": {"Name": output},
    }


def blockstate_rule(source, output, probability, properties):
    return {
        "input_predicate": {
            "predicate_type": "minecraft:random_blockstate_match",
            "block_state": {"Name": source, "Properties": properties},
            "probability": probability,
        },
        "location_predicate": {"predicate_type": "minecraft:always_true"},
        "output_state": {"Name": output, "Properties": properties},
    }


def rules(mossiness):
    scale = mossiness / 0.25
    result = []
    for source, variants in PLAIN:
        for base_probability, output in variants:
            result.append(plain_rule(source, output, round(base_probability * scale, 3)))
    for source, variants in STAIRS:
        for base_probability, output in variants:
            probability = round(base_probability * scale, 3)
            for facing, half, shape in itertools.product(STAIR_FACINGS, STAIR_HALVES, STAIR_SHAPES):
                properties = {
                    "facing": facing, "half": half, "shape": shape, "waterlogged": "false",
                }
                result.append(blockstate_rule(source, output, probability, properties))
    for source, variants in SLABS:
        for base_probability, output in variants:
            probability = round(base_probability * scale, 3)
            for slab_type in SLAB_TYPES:
                properties = {"type": slab_type, "waterlogged": "false"}
                result.append(blockstate_rule(source, output, probability, properties))
    return result


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="e.g. structura:aged_stone")
    parser.add_argument(
        "--mossiness", type=float, default=0.25,
        help="0..1, scales every rule's probability relative to its base value",
    )
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    args = parser.parse_args()

    if not 0.0 <= args.mossiness <= 1.0:
        parser.error("--mossiness must be between 0 and 1")
    if ":" not in args.name:
        parser.error("name must be namespaced, for example structura:aged_stone")

    list_name = args.name.split(":", 1)[1]
    path = args.data_root / "worldgen/processor_list" / f"{list_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "processors": [{
            "processor_type": "minecraft:rule",
            "rules": rules(args.mossiness),
        }],
    }, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
