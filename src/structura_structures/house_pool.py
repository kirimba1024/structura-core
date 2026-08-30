#!/usr/bin/env python3
"""Wrap one house NBT (already in build/) in a single-element template_pool,
so it can be tested with /place jigsaw without a full structure_set/village.
"""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("house", help="e.g. structura:davegr_house")
    parser.add_argument("pool", help="e.g. structura:house_test")
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    parser.add_argument("--processors", default="minecraft:empty")
    args = parser.parse_args()

    namespace, pool_name = args.pool.split(":", 1)
    path = args.data_root / "worldgen/template_pool" / f"{pool_name}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "fallback": "minecraft:empty",
        "elements": [{
            "weight": 1,
            "element": {
                "element_type": "minecraft:single_pool_element",
                "location": args.house,
                "processors": args.processors,
                "projection": "rigid",
            },
        }],
    }, indent=2) + "\n")
    print(path)


if __name__ == "__main__":
    main()
