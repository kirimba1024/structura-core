#!/usr/bin/env python3
"""Write the structura:chests/default indirection loot table.

Containers point at this one instead of a vanilla table directly, so the
actual loot can be swapped for every structure at once by editing this
single file.
"""
import argparse
import json
from pathlib import Path


def build(target, data_root):
    path = Path(data_root) / "loot_table/chests/default.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({
        "type": "minecraft:chest",
        "pools": [{
            "rolls": 1,
            "entries": [{"type": "minecraft:loot_table", "value": target}],
        }],
    }, indent=2) + "\n")
    return path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--target", default="minecraft:chests/simple_dungeon")
    parser.add_argument(
        "--data-root", type=Path, default=Path("build/data/structura"),
    )
    args = parser.parse_args()

    path = build(args.target, args.data_root)
    print(path)


if __name__ == "__main__":
    main()
