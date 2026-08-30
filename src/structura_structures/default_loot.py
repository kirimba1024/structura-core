#!/usr/bin/env python3
"""Point every empty container at structura:chests/default, vanilla or modded.

Skips anything that already has a LootTable or hand-placed Items -- this
only fills containers that would otherwise generate empty.
"""
import argparse

from amulet_nbt import CompoundTag, StringTag

from .nbt import Structure, save_structure

CONTAINER_HINTS = (
    "chest", "barrel", "shulker_box", "hopper", "dispenser", "dropper",
)
NO_LOOT_TABLE = ("ender_chest",)
KNOWN_BLOCK_ENTITY_ID = sorted({
    "chest": "minecraft:chest",
    "trapped_chest": "minecraft:chest",
    "barrel": "minecraft:barrel",
    "shulker_box": "minecraft:shulker_box",
    "hopper": "minecraft:hopper",
    "dispenser": "minecraft:dispenser",
    "dropper": "minecraft:dropper",
}.items(), key=lambda kv: -len(kv[0]))


def supports_loot_table(name):
    suffix = name.split(":", 1)[-1]
    return not any(suffix == n or suffix.endswith(f"_{n}") for n in NO_LOOT_TABLE)


def known_block_entity_id(name):
    suffix = name.split(":", 1)[-1]
    for key, block_entity_id in KNOWN_BLOCK_ENTITY_ID:
        if suffix == key or suffix.endswith(f"_{key}"):
            return block_entity_id
    return None


def is_container(name):
    suffix = name.split(":", 1)[-1]
    return any(hint in suffix for hint in CONTAINER_HINTS)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("src")
    parser.add_argument("dst")
    parser.add_argument("--loot-table", default="structura:chests/default")
    args = parser.parse_args()

    src = Structure(args.src)
    filled = 0
    skipped_existing = 0
    skipped_unknown = 0
    for pos, index in src.present.items():
        name = src.palette[index]
        if not is_container(name) or not supports_loot_table(name):
            continue
        existing = src.block_nbt.get(pos)
        if existing is not None:
            if "LootTable" in existing or "Items" in existing:
                skipped_existing += 1
                continue
            data = dict(existing.items())
        else:
            block_entity_id = known_block_entity_id(name)
            if block_entity_id is None:
                skipped_unknown += 1
                continue
            data = {"id": StringTag(block_entity_id)}
        data["LootTable"] = StringTag(args.loot_table)
        src.block_nbt[pos] = CompoundTag(data)
        filled += 1

    block_count = save_structure(src, args.dst, src.size, (0, 0, 0))
    print(f"blocks={block_count} filled={filled} "
          f"skipped_existing_loot={skipped_existing} skipped_unknown={skipped_unknown}")


if __name__ == "__main__":
    main()
