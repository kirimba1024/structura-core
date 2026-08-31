#!/usr/bin/env python3
"""Group several already-built structures into one weighted structure_set,
so multiple house types share one spacing/separation grid instead of
spawning as independent, potentially-overlapping structure_sets."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("name", help="e.g. structura:village_ground")
    parser.add_argument(
        "structure", nargs="+",
        help="structura:name:weight, e.g. structura:davegr_house_structure:1",
    )
    parser.add_argument("--spacing", type=int, default=24)
    parser.add_argument("--separation", type=int, default=10)
    parser.add_argument("--salt", type=int, required=True)
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    args = parser.parse_args()

    if args.spacing <= 0 or not 0 <= args.separation < args.spacing:
        parser.error("require spacing > 0 and 0 <= separation < spacing")

    structures = []
    for entry in args.structure:
        parts = entry.rsplit(":", 1)
        if len(parts) != 2 or not parts[1].isdigit():
            parser.error(f"expected name:weight, got {entry!r}")
        structures.append({"structure": parts[0], "weight": int(parts[1])})
    if not structures or all(s["weight"] <= 0 for s in structures):
        parser.error("need at least one structure with weight > 0")

    namespace, set_name = args.name.split(":", 1)
    set_path = args.data_root / "worldgen/structure_set" / f"{set_name}.json"
    set_path.parent.mkdir(parents=True, exist_ok=True)
    set_path.write_text(json.dumps({
        "structures": structures,
        "placement": {
            "type": "minecraft:random_spread",
            "salt": args.salt,
            "spacing": args.spacing,
            "separation": args.separation,
        },
    }, indent=2) + "\n")
    print(set_path)


if __name__ == "__main__":
    main()
