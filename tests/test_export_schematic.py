from copy import deepcopy

import pytest
from amulet_nbt import (
    ByteTag, CompoundTag, DoubleTag, IntArrayTag, IntTag, ListTag, StringTag, load,
)

from structura_core.export_schematic import export_schematic, schematic_root
from structura_core.nbt import Structure, write_root


def source(tmp_path, *, size=(2, 2, 2)):
    root = CompoundTag({
        "DataVersion": IntTag(3955),
        "size": ListTag([IntTag(v) for v in size]),
        "palette": ListTag([CompoundTag({"Name": StringTag("minecraft:chest")})]),
        "blocks": ListTag([CompoundTag({
            "pos": ListTag([IntTag(0), IntTag(0), IntTag(0)]),
            "state": IntTag(0),
            "nbt": CompoundTag({
                "id": StringTag("minecraft:chest"),
                "CustomName": StringTag('{"text":"Chest"}'),
                "Items": ListTag([CompoundTag({
                    "Slot": ByteTag(0), "id": StringTag("minecraft:apple"), "count": IntTag(2),
                })]),
            }),
        })]),
        "entities": ListTag([CompoundTag({
            "pos": ListTag([DoubleTag(.25), DoubleTag(1), DoubleTag(.75)]),
            "blockPos": ListTag([IntTag(0), IntTag(1), IntTag(0)]),
            "nbt": CompoundTag({
                "id": StringTag("minecraft:item"),
                "Pos": ListTag([DoubleTag(99)] * 3),
                "Item": CompoundTag({"id": StringTag("minecraft:diamond"), "count": IntTag(3)}),
            }),
        })]),
    })
    path = tmp_path / "source.nbt"
    write_root(root, path)
    return Structure(path)


def test_sponge_v2_uses_named_root_and_preserves_payloads(tmp_path):
    src = source(tmp_path)
    before = deepcopy(src.entities)
    output = export_schematic(src, tmp_path / "scene.schem")
    named = load(str(output))
    root = named.compound

    assert named.name == "Schematic"
    assert root["Version"] == IntTag(2)
    assert "Schematic" not in root
    chest = root["BlockEntities"][0]
    assert chest["Id"] == StringTag("minecraft:chest")
    assert chest["Pos"] == IntArrayTag([0, 0, 0])
    assert chest["Items"][0]["count"] == IntTag(2)
    assert chest["CustomName"] == StringTag('{"text":"Chest"}')
    assert "Extra" not in chest
    entity = root["Entities"][0]
    assert entity["Id"] == StringTag("minecraft:item")
    assert entity["Pos"] == src.entities[0]["pos"]
    assert entity["Item"]["id"] == StringTag("minecraft:diamond")
    assert src.entities == before


def test_block_data_order_and_multibyte_palette_indices(tmp_path):
    src = source(tmp_path, size=(130, 1, 2))
    src.palette_raw[:] = [CompoundTag({"Name": StringTag(f"test:block_{i}")}) for i in range(130)]
    src.present = {(x, 0, z): x for z in range(2) for x in range(130)}
    src.block_nbt = {}
    payload = schematic_root(src)
    encoded = bytes(payload["BlockData"].np_array.astype("uint8"))
    # Independent decoder: boundaries 127/128 and full XZY ordering.
    decoded, value, shift = [], 0, 0
    for byte in encoded:
        value |= (byte & 127) << shift
        if byte & 128:
            shift += 7
        else:
            decoded.append(value)
            value, shift = 0, 0
    assert decoded == list(range(130)) * 2


def test_out_of_range_dimensions_are_rejected_before_dense_allocation(tmp_path):
    src = source(tmp_path)
    src.size = (65536, 1, 1)
    with pytest.raises(ValueError, match="unsigned short"):
        schematic_root(src)


def test_missing_entity_id_does_not_silently_drop_entity(tmp_path):
    src = source(tmp_path)
    del src.entities[0]["nbt"]["id"]
    with pytest.raises(ValueError, match="entity has no id"):
        export_schematic(src, tmp_path / "invalid.schem")
    assert not (tmp_path / "invalid.schem").exists()


@pytest.mark.parametrize("width", [32767, 32768, 65535])
def test_sponge_unsigned_short_dimensions_keep_their_bits(tmp_path, width):
    src = source(tmp_path, size=(width, 1, 1))
    output = export_schematic(src, tmp_path / "wide.schem")
    payload = load(str(output)).compound
    assert int(payload["Width"]) & 0xffff == width
    assert len(payload["BlockData"]) == width


@pytest.mark.parametrize("block_entity", [False, True])
def test_invalid_entity_id_does_not_create_malformed_output(tmp_path, block_entity):
    src = source(tmp_path)
    nbt = src.block_nbt[(0, 0, 0)] if block_entity else src.entities[0]["nbt"]
    nbt["id"] = IntTag(42)
    with pytest.raises(ValueError, match="string id"):
        export_schematic(src, tmp_path / "invalid.schem")
    assert not (tmp_path / "invalid.schem").exists()
