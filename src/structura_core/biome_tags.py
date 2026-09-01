#!/usr/bin/env python3
"""Write reusable worldgen/biome tags for structure placement."""
import argparse
import json
from pathlib import Path

SURFACE_LAND = [
    "minecraft:plains", "minecraft:sunflower_plains", "minecraft:meadow",
    "minecraft:forest", "minecraft:flower_forest", "minecraft:birch_forest",
    "minecraft:old_growth_birch_forest", "minecraft:dark_forest",
    "minecraft:taiga", "minecraft:old_growth_pine_taiga",
    "minecraft:old_growth_spruce_taiga", "minecraft:snowy_taiga",
    "minecraft:savanna", "minecraft:savanna_plateau", "minecraft:windswept_savanna",
    "minecraft:desert", "minecraft:badlands", "minecraft:eroded_badlands",
    "minecraft:wooded_badlands", "minecraft:swamp", "minecraft:mangrove_swamp",
    "minecraft:jungle", "minecraft:sparse_jungle", "minecraft:bamboo_jungle",
    "minecraft:grove", "minecraft:snowy_plains", "minecraft:ice_spikes",
    "minecraft:stony_shore", "minecraft:windswept_hills",
    "minecraft:windswept_gravelly_hills", "minecraft:windswept_forest",
    "minecraft:cherry_grove",
]

OCEAN = [
    "minecraft:ocean", "minecraft:deep_ocean", "minecraft:warm_ocean",
    "minecraft:lukewarm_ocean", "minecraft:deep_lukewarm_ocean",
    "minecraft:cold_ocean", "minecraft:deep_cold_ocean",
    "minecraft:frozen_ocean", "minecraft:deep_frozen_ocean",
]

NETHER = [
    "minecraft:nether_wastes", "minecraft:soul_sand_valley",
    "minecraft:crimson_forest", "minecraft:warped_forest",
    "minecraft:basalt_deltas",
]

SKY_ANYWHERE = ["#structura:surface_land", "#structura:ocean"]


def write_tag(data_root, name, values):
    path = data_root / f"tags/worldgen/biome/{name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"values": values}, indent=2) + "\n")
    print(path, f"{len(values)} biomes")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    args = parser.parse_args()

    write_tag(args.data_root, "surface_land", SURFACE_LAND)
    write_tag(args.data_root, "ocean", OCEAN)
    write_tag(args.data_root, "nether", NETHER)
    write_tag(args.data_root, "sky_anywhere", SKY_ANYWHERE)


if __name__ == "__main__":
    main()
