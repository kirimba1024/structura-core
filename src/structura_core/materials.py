"""Block taxonomy: which names are geology and which are architecture.

Every terrain mechanism in the stack needs the same distinction -- a scree
apron must be able to lean on a hillside without leaning on a house wall --
so it lives in exactly one place rather than being re-guessed per module.

Unknown names are deliberately NOT terrain. The set of blocks a builder can
place is open-ended and grows every release, so the classification has to
have a safe direction to fail in: treating an unrecognised block as
architecture means the terrain passes decline to grow from it (they
under-fill, which looks like nothing happened) instead of piling soil over
something the author built (which is unrecoverable and obvious).
"""

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
    """True for geology the ground passes may grow from or lean against.

    Ores count: they are the inside of a hill, and a hillside with an iron
    seam in it is still a hillside.

    _MASONRY_LOOKALIKES do not, even though every one of them does occur in
    world generation. Cobblestone, sandstone, terracotta, obsidian and the
    ices are all far more often something a builder stacked than something
    the world grew, and the cost is wildly asymmetric: reading masonry as
    geology invites a scree apron to bank itself against a castle wall,
    while reading a badlands mesa as masonry only means the apron declines
    to grow there. Measured on [Arolas]MountianCastle, where the castle is
    cobblestone: counting it as terrain put the "ground surface" 41 blocks
    up on the battlements, one column away from grass at 11.

    Names alone cannot finish this job -- a castle built out of plain stone
    would still read as a hill -- which is why the geometric guard in
    terrain_and_architecture() exists alongside this list rather than
    downstream of it."""
    if name in NATURAL_TERRAIN:
        return True
    return name.endswith(_ORE_SUFFIXES)
