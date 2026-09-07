"""Regenerate with litemapy==0.11.0b0; not a runtime or test dependency."""

from pathlib import Path

from litemapy import BlockState, Entity, Region, Schematic, TileEntity
from nbtlib import Compound, Int, String


def main():
    negative = Region(10, 20, 30, -5, -3, -7)
    for y in range(3):
        for z in range(7):
            for x in range(5):
                index = y * 35 + z * 5 + x
                negative[x - 4, y - 2, z - 6] = BlockState(f"example:block_{index % 34}", variant="a")
    negative.tile_entities.append(TileEntity(Compound({
        "id": String("minecraft:chest"), "x": Int(1), "y": Int(1), "z": Int(1),
        "CustomName": String('"kept"'),
    })))
    entity = Entity("minecraft:armor_stand")
    entity.position = (-1.5, -0.25, -2.5)
    negative.entities.append(entity)
    positive = Region(12, 20, 30, 2, 1, 1)
    positive[0, 0, 0] = BlockState("minecraft:stone")
    schematic = Schematic(
        name="Signed regions", author="Structura interoperability fixture",
        regions={"negative": negative, "positive": positive}, mc_version=3955,
    )
    schematic.created = schematic.modified = 0
    schematic.save(Path(__file__).with_name("signed-regions.litematic"), update_meta=False)


if __name__ == "__main__":
    main()
