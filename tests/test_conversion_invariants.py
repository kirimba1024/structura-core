"""Compare format contracts independently of palette layout and warning wording."""

import warnings
from copy import deepcopy
from itertools import product

import pytest
from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, FloatTag, IntArrayTag, IntTag,
    ListTag, LongArrayTag, LongTag, ShortTag, StringTag,
)

from structura_core import ConversionWarning, Structure, convert_structure, load_structure

FORMATS = (".nbt", ".snbt", ".litematic", ".schem")


@pytest.fixture
def structure():
    palette = [CompoundTag({"Name": StringTag(f"minecraft:{name}")}) for name in (
        "air", "stone", "oak_stairs", "chest", "structure_void", "stone",
    )]
    palette[2]["Properties"] = CompoundTag({key: StringTag(value) for key, value in {
        "facing": "east", "half": "top", "shape": "straight", "waterlogged": "true",
    }.items()})
    payload = CompoundTag({
        "id": StringTag("minecraft:chest"), "x": IntTag(1), "y": IntTag(0), "z": IntTag(2),
        "CustomName": StringTag('"Сундук 🌍"'),
        "Items": ListTag([CompoundTag({"Slot": ByteTag(0), "id": StringTag("minecraft:diamond"), "count": IntTag(3)})]),
        "Typed": CompoundTag({
            "byte": ByteTag(1), "short": ShortTag(1), "int": IntTag(1), "long": LongTag(1),
            "float": FloatTag(.125), "double": DoubleTag(-.625),
            "bytes": ByteArrayTag([-128, 0, 127]), "ints": IntArrayTag([-2**31, 0, 2**31 - 1]),
            "longs": LongArrayTag([-2**63, 0, 2**63 - 1]),
        }),
    })
    blocks = ListTag()
    for x, y, z in product(range(3), range(2), range(5)):
        record = CompoundTag({
            "pos": ListTag([IntTag(value) for value in (x, y, z)]),
            "state": IntTag((x + 3 * y + 7 * z) % len(palette)),
        })
        if (x, y, z) == (1, 0, 2):
            record.update({"state": IntTag(3), "nbt": payload})
        blocks.append(record)
    position = ListTag([DoubleTag(value) for value in (1.25, .5, 2.75)])
    entity = CompoundTag({
        "pos": position, "blockPos": ListTag([IntTag(value) for value in (1, 0, 2)]),
        "nbt": CompoundTag({"id": StringTag("minecraft:armor_stand"), "Pos": deepcopy(position),
                            "Invisible": ByteTag(1), "Rotation": ListTag([FloatTag(45.5), FloatTag(-12)])}),
    })
    visible = deepcopy(entity)
    visible["nbt"]["Invisible"] = ByteTag(0)
    return Structure.from_root(CompoundTag({
        "DataVersion": IntTag(3955), "size": ListTag([IntTag(value) for value in (3, 2, 5)]),
        "palette": ListTag(palette), "blocks": blocks,
        "entities": ListTag([entity, deepcopy(entity), visible]),
    }))


@pytest.mark.parametrize("first", FORMATS)
@pytest.mark.parametrize("second", FORMATS)
def test_java_routes_preserve_common_data_over_repeated_cycles(tmp_path, structure, structure_snapshot, first, second):
    """Generated document metadata is format-specific; common data must remain intact."""
    expected = structure_snapshot(structure)
    current = convert_structure(structure, tmp_path / f"start{first}", strict=True)
    assert structure_snapshot(load_structure(current)) == expected
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConversionWarning)
        for cycle in range(3):
            for step, suffix in enumerate((second, first)):
                current = convert_structure(current, tmp_path / f"cycle-{cycle}-{step}{suffix}")
                assert structure_snapshot(load_structure(current)) == expected
    assert structure_snapshot(structure) == expected


@pytest.mark.parametrize("suffix,missing_state", [
    (".nbt", None), (".snbt", None), (".litematic", "minecraft:structure_void"), (".schem", "minecraft:air"),
])
def test_sparse_normalization_is_explicit_and_stable(tmp_path, structure, structure_snapshot, suffix, missing_state):
    hole = (2, 1, 4)
    del structure.present[hole]
    original = structure_snapshot(structure)
    expected = deepcopy(original)
    if missing_state is not None:
        expected["blocks"][hole] = ((missing_state, ()), None)
    output = tmp_path / f"sparse{suffix}"
    if suffix == ".schem":
        output.write_bytes(b"previous")
        with pytest.raises(ValueError):
            convert_structure(structure, output, strict=True)
        assert output.read_bytes() == b"previous"
        with pytest.warns(ConversionWarning):
            convert_structure(structure, output)
    else:
        convert_structure(structure, output, strict=True)
    for _ in range(3):
        restored = load_structure(output)
        assert structure_snapshot(restored) == expected
        convert_structure(restored, output, strict=True)
    assert structure_snapshot(load_structure(output)) == expected
    assert structure_snapshot(structure) == original


def test_snapshot_ignores_palette_and_record_order(structure, structure_snapshot):
    root = deepcopy(structure._root)
    root["palette"] = ListTag(list(reversed(root["palette"])))
    root["blocks"] = ListTag(list(reversed(root["blocks"])))
    root["entities"] = ListTag(list(reversed(root["entities"])))
    for record in root["blocks"]:
        record["state"] = IntTag(len(root["palette"]) - 1 - int(record["state"]))
    assert structure_snapshot(Structure.from_root(root)) == structure_snapshot(structure)


@pytest.mark.parametrize("change", ["nbt_type", "array_type", "property", "cell", "entity", "origin", "version"])
def test_snapshot_detects_data_changes(structure, structure_snapshot, change):
    before = structure_snapshot(structure)
    if change == "nbt_type":
        structure.block_nbt[1, 0, 2]["Typed"]["byte"] = IntTag(1)
    elif change == "array_type":
        structure.block_nbt[1, 0, 2]["Typed"]["bytes"] = IntArrayTag([-128, 0, 127])
    elif change == "property":
        structure.palette_raw[2]["Properties"]["facing"] = StringTag("west")
    elif change == "cell":
        del structure.present[0, 0, 0]
    elif change == "entity":
        structure.entities.pop(0)
    elif change == "origin":
        structure.source_origin = (-12, 5, 9)
    else:
        structure.data_version += 1
    assert structure_snapshot(structure) != before
