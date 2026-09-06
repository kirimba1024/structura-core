from amulet_nbt import CompoundTag, DoubleTag, ListTag, StringTag

from structura_core.convert_legacy import (
    _entity_data,
    _legacy_entities,
    _structure_entity,
)


def test_classic_direction_is_normalized_to_modern_facing():
    root = CompoundTag(
        {
            "Entities": ListTag(
                [
                    CompoundTag(
                        {
                            "id": StringTag("ItemFrame"),
                            "Direction": StringTag("2"),
                            "TileX": StringTag("4"),
                            "TileY": StringTag("5"),
                            "TileZ": StringTag("6"),
                        }
                    )
                ]
            )
        }
    )

    [(pos, payload)] = _legacy_entities(root)

    assert pos == (4, 5, 6)
    assert payload["id"] == "minecraft:item_frame"
    assert payload["facing"] == 2


def test_sponge_data_payload_and_fractional_position_are_preserved():
    root = CompoundTag(
        {
            "Schematic": CompoundTag(
                {
                    "Entities": ListTag(
                        [
                            CompoundTag(
                                {
                                    "Id": StringTag("minecraft:item"),
                                    "Pos": ListTag(
                                        [DoubleTag(1.25), DoubleTag(2), DoubleTag(3.75)]
                                    ),
                                    "Data": CompoundTag(
                                        {
                                            "Item": CompoundTag(
                                                {"id": StringTag("minecraft:apple")}
                                            ),
                                        }
                                    ),
                                }
                            )
                        ]
                    ),
                }
            )
        }
    )

    assert _legacy_entities(root) == []
    [(pos, payload)] = _legacy_entities(root, preserve_all=True)

    assert pos == (1.25, 2.0, 3.75)
    assert payload["id"] == "minecraft:item"
    assert payload["exact"] is True
    assert str(payload["nbt"]["Item"]["id"]) == "minecraft:apple"


def test_sponge_data_and_extra_payloads_are_merged():
    entry = CompoundTag(
        {
            "Id": StringTag("minecraft:item"),
            "Data": CompoundTag({"first": StringTag("data")}),
            "Extra": CompoundTag({"second": StringTag("extra")}),
        }
    )

    merged = _entity_data(entry)

    assert str(merged["first"]) == "data"
    assert str(merged["second"]) == "extra"


def test_structure_entity_rewrites_stale_inner_position():
    entity = _structure_entity(
        (1.25, 2, 3.75),
        {
            "id": "minecraft:item",
            "exact": True,
            "nbt": CompoundTag(
                {
                    "Pos": ListTag([DoubleTag(90), DoubleTag(91), DoubleTag(92)]),
                }
            ),
        },
    )

    assert [float(value.py_data) for value in entity["pos"]] == [1.25, 2, 3.75]
    assert [float(value.py_data) for value in entity["nbt"]["Pos"]] == [1.25, 2, 3.75]


def test_pre_flattening_entity_aliases_use_real_modern_ids():
    root = CompoundTag(
        {
            "Entities": ListTag(
                [
                    CompoundTag(
                        {
                            "id": StringTag(legacy),
                            "Pos": ListTag(
                                [DoubleTag(index), DoubleTag(0), DoubleTag(0)]
                            ),
                        }
                    )
                    for index, legacy in enumerate(
                        (
                            "LavaSlime",
                            "MushroomCow",
                            "PigZombie",
                            "WitherBoss",
                            "EvocationIllager",
                            "TNTPrimed",
                            "XPOrb",
                        )
                    )
                ]
            )
        }
    )
    found = _legacy_entities(root, preserve_all=True)
    assert [payload["id"] for _pos, payload in found] == [
        "minecraft:magma_cube",
        "minecraft:mooshroom",
        "minecraft:zombified_piglin",
        "minecraft:wither",
        "minecraft:evoker",
        "minecraft:tnt",
        "minecraft:experience_orb",
    ]
