#!/usr/bin/env python3

GROUND_MARKERS = frozenset({
    "minecraft:grass_block", "minecraft:dirt_path", "minecraft:coarse_dirt",
    "minecraft:farmland", "minecraft:podzol", "minecraft:mycelium",
    "minecraft:sand", "minecraft:red_sand", "minecraft:gravel",
    "minecraft:snow_block",
})

NATURAL_GROUND_BLOCKS = frozenset({
    "minecraft:grass_block", "minecraft:dirt", "minecraft:coarse_dirt",
    "minecraft:podzol", "minecraft:mycelium", "minecraft:mud",
    "minecraft:stone", "minecraft:mossy_cobblestone",
    "minecraft:andesite", "minecraft:diorite", "minecraft:granite",
    "minecraft:deepslate", "minecraft:moss_block",
    "minecraft:gravel", "minecraft:sand", "minecraft:red_sand",
})

METRIC_NATURAL_BLOCKS = frozenset({
    "minecraft:dirt", "minecraft:grass_block", "minecraft:stone",
    "minecraft:gravel", "minecraft:sand", "minecraft:coarse_dirt",
    "minecraft:podzol", "minecraft:mycelium", "minecraft:andesite",
    "minecraft:diorite", "minecraft:granite", "minecraft:clay",
})

_SOIL = frozenset({
    "minecraft:dirt", "minecraft:rooted_dirt", "minecraft:mud", "minecraft:clay",
    "minecraft:soul_sand", "minecraft:soul_soil", "minecraft:snow",
    "minecraft:suspicious_sand", "minecraft:suspicious_gravel",
})

_ROCK = frozenset({
    "minecraft:stone", "minecraft:deepslate", "minecraft:tuff",
    "minecraft:calcite", "minecraft:dripstone_block", "minecraft:pointed_dripstone",
    "minecraft:blackstone", "minecraft:basalt", "minecraft:smooth_basalt",
    "minecraft:magma_block", "minecraft:netherrack", "minecraft:end_stone",
    "minecraft:bedrock",
})

_MASONRY_LOOKALIKES = frozenset({
    "minecraft:cobblestone", "minecraft:mossy_cobblestone", "minecraft:obsidian",
    "minecraft:sandstone", "minecraft:red_sandstone", "minecraft:terracotta",
    "minecraft:ice", "minecraft:packed_ice", "minecraft:blue_ice",
})

_ORE_SUFFIXES = ("_ore", "_raw_block")

NATURAL_TERRAIN = frozenset(GROUND_MARKERS | _SOIL | _ROCK)


def is_terrain(name):
    if name in NATURAL_TERRAIN:
        return True
    return name.endswith(_ORE_SUFFIXES)
