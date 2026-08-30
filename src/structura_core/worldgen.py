#!/usr/bin/env python3
"""Write a jigsaw worldgen/structure + structure_set for real generation testing."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="e.g. structura:davegr_house_structure")
    parser.add_argument("start_pool", help="e.g. structura:davegr_house_pool")
    parser.add_argument("--biomes", nargs="+", default=["minecraft:plains"])
    parser.add_argument("--spacing", type=int, default=20)
    parser.add_argument("--separation", type=int, default=8)
    parser.add_argument("--salt", type=int, default=918274)
    parser.add_argument("--size", type=int, default=6)
    parser.add_argument("--start-height", type=int, default=0)
    parser.add_argument("--step", default="surface_structures")
    parser.add_argument("--terrain-adaptation", default="none")
    parser.add_argument("--heightmap", default="WORLD_SURFACE_WG")
    parser.add_argument("--max-distance", type=int, default=80)
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    args = parser.parse_args()

    if len(args.biomes) > 1 and any(b.startswith("#") for b in args.biomes):
        parser.error("a biome tag ('#ns:tag') can't be mixed with a biome list")
    if args.size < 1:
        parser.error("--size must be at least 1; size=0 hangs Minecraft 1.21.1 worldgen")
    if args.spacing <= 0 or not 0 <= args.separation < args.spacing:
        parser.error("require spacing > 0 and 0 <= separation < spacing")
    if args.max_distance <= 0:
        parser.error("--max-distance must be positive")

    namespace, structure_name = args.name.split(":", 1)
    structure_path = args.data_root / "worldgen/structure" / f"{structure_name}.json"
    structure_path.parent.mkdir(parents=True, exist_ok=True)
    body = {
        "type": "minecraft:jigsaw",
        "step": args.step,
        "spawn_overrides": {},
        "start_pool": args.start_pool,
        "size": args.size,
        "start_height": {
            "type": "minecraft:constant",
            "value": {"absolute": args.start_height},
        },
        "use_expansion_hack": False,
        "biomes": args.biomes[0] if len(args.biomes) == 1 else args.biomes,
        "max_distance_from_center": args.max_distance,
        "dimension_padding": 1,
        "liquid_settings": "ignore_waterlogging",
        "terrain_adaptation": args.terrain_adaptation,
    }
    if args.heightmap != "none":
        body["project_start_to_heightmap"] = args.heightmap
    structure_path.write_text(json.dumps(body, indent=2) + "\n")

    set_path = args.data_root / "worldgen/structure_set" / f"{structure_name}_set.json"
    set_path.parent.mkdir(parents=True, exist_ok=True)
    set_path.write_text(json.dumps({
        "structures": [{"structure": args.name, "weight": 1}],
        "placement": {
            "type": "minecraft:random_spread",
            "salt": args.salt,
            "spacing": args.spacing,
            "separation": args.separation,
        },
    }, indent=2) + "\n")

    print(structure_path)
    print(set_path)


if __name__ == "__main__":
    main()
