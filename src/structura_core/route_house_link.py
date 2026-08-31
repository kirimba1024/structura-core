#!/usr/bin/env python3
"""Add house pools as weighted alternatives inside a built routes/<profile>
pool, so a route segment can terminate by attaching a whole second house
instead of always just capping -- real jigsaw-linked villages, for
environments (sky, underwater) where houses don't rely on a per-piece
terrain anchor."""
import argparse
import json
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("routes_path", type=Path)
    parser.add_argument("house", nargs="+", help="structura:structure_name:weight")
    args = parser.parse_args()

    data = json.loads(args.routes_path.read_text())
    for entry in args.house:
        name, _, weight = entry.rpartition(":")
        if not name or not weight.isdigit():
            parser.error(f"expected structura:structure_name:weight, got {entry!r}")
        data["elements"].append({
            "weight": int(weight),
            "element": {
                "element_type": "minecraft:single_pool_element",
                "location": name,
                "processors": "minecraft:empty",
                "projection": "rigid",
            },
        })
    args.routes_path.write_text(json.dumps(data, indent=2) + "\n")
    print(args.routes_path)


if __name__ == "__main__":
    main()
