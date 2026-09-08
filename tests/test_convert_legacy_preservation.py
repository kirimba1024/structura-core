import json
import logging

import numpy as np
import pytest
from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, IntTag, ListTag, ShortTag, StringTag,
)

pytest.importorskip("amulet")

from structura_core import Structure
from structura_core.convert_legacy import convert
from structura_core.export_schematic import export_schematic
from structura_core.nbt import load_root, write_root


def legacy_file(tmp_path):
    blocks = np.zeros(27, dtype=np.int8)
    blocks[12:15] = [54, 1, 7]  # chest, stone, bedrock in XZY order
    root = CompoundTag({
        "Width": ShortTag(3), "Height": ShortTag(3), "Length": ShortTag(3),
        "Materials": StringTag("Alpha"), "Blocks": ByteArrayTag(blocks),
        "Data": ByteArrayTag(np.zeros(27, dtype=np.int8)),
        "TileEntities": ListTag([CompoundTag({
            "id": StringTag("minecraft:chest"),
            "x": IntTag(0), "y": IntTag(1), "z": IntTag(1),
            "Items": ListTag([CompoundTag({
                "Slot": ByteTag(0), "id": StringTag("minecraft:apple"), "Count": ByteTag(2),
            })]),
        })]),
        "Entities": ListTag([CompoundTag({
            "id": StringTag("example:item_frame"),
            "Pos": ListTag([DoubleTag(1.25), DoubleTag(.5), DoubleTag(1.75)]),
            "label": StringTag("custom entity, not a vanilla frame"),
        })]),
    })
    path = tmp_path / "source.schematic"
    write_root(root, path, name="Schematic")
    return path


def test_preserving_conversion_keeps_layout_materials_and_exportable_block_nbt(tmp_path, monkeypatch):
    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "cache"))
    source = legacy_file(tmp_path)
    output = tmp_path / "preserved.nbt"
    convert(str(source), str(output), 3955, preserve_all_entities=True)
    structure = Structure(output)

    assert structure.size == (3, 3, 3)
    assert len(structure.present) == 27
    assert sum(structure.is_air(pos) for pos in structure.present) == 24
    assert structure.name_at((2, 1, 1)) == "minecraft:bedrock"
    chest = structure.block_nbt[(0, 1, 1)]
    assert chest["id"] == StringTag("minecraft:chest")
    assert len(chest["Items"]) == 1
    assert structure.entities[0]["nbt"]["id"] == StringTag("example:item_frame")
    assert [float(value) for value in structure.entities[0]["pos"]] == [1.25, .5, 1.75]

    schematic = load_root(export_schematic(structure, tmp_path / "converted.schem"))
    assert schematic["BlockEntities"][0]["Id"] == StringTag("minecraft:chest")
    assert schematic["Entities"][0]["Id"] == StringTag("example:item_frame")


def test_placement_preparation_points_to_geo_without_writing(tmp_path):
    output = tmp_path / "unchanged.nbt"
    output.write_bytes(b"keep")
    with pytest.raises(ValueError, match="structura_geo"):
        convert("missing", str(output), 3955, prepare_for_placement=True)
    assert output.read_bytes() == b"keep"


def test_conversion_preserves_formatted_legacy_sign_text(tmp_path, monkeypatch):
    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "cache"))
    source = legacy_file(tmp_path)
    root = load_root(source)
    blocks = root["Blocks"].np_array.copy()
    blocks[12] = 63
    root["Blocks"] = ByteArrayTag(blocks)
    root["TileEntities"] = ListTag([CompoundTag({
        "id": StringTag("Sign"), "x": IntTag(0), "y": IntTag(1), "z": IntTag(1),
        "Text1": StringTag('{"text":"Welcome","color":"red"}'),
        "Text2": StringTag("Plain text"), "Text3": StringTag(""), "Text4": StringTag(""),
    })])
    write_root(root, source, name="Schematic")
    output = tmp_path / "sign.nbt"

    convert(str(source), str(output), 3955)

    messages = Structure(output).block_nbt[(0, 1, 1)]["front_text"]["messages"]
    assert [json.loads(str(message)) for message in messages] == [
        {"text": "Welcome", "color": "red"}, {"text": "Plain text"}, {"text": ""}, {"text": ""},
    ]


def test_failed_conversion_restores_amulet_logger(tmp_path, monkeypatch):
    from structura_core import convert_legacy

    def fail(_path):
        raise OSError("cannot open source")

    monkeypatch.setattr(convert_legacy.amulet, "load_level", fail)
    logger = logging.getLogger("amulet")
    original = logger.level
    with pytest.raises(OSError, match="cannot open"):
        convert("missing", str(tmp_path / "output.nbt"), 3955)
    assert logger.level == original


def test_shared_loader_preserves_legacy_entities_and_enforces_limits(tmp_path, monkeypatch):
    from structura_core import convert_structure, load_structure
    from structura_core.conversion_losses import ConversionWarning

    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "cache"))
    path = legacy_file(tmp_path)
    original = path.read_bytes()
    with pytest.warns(ConversionWarning, match="Legacy schematic"):
        source = load_structure(path)
    assert source.size == (3, 3, 3)
    assert source.name_at((2, 1, 1)) == "minecraft:bedrock"
    assert len(source.block_nbt[(0, 1, 1)]["Items"]) == 1
    assert str(source.entities[0]["nbt"]["id"]) == "example:item_frame"
    with pytest.raises(ValueError, match="Legacy schematic"):
        load_structure(path, strict=True)
    output = tmp_path / "strict.nbt"
    output.write_bytes(b"keep")
    with pytest.raises(ValueError, match="Legacy schematic"):
        convert_structure(path, output, strict=True)
    assert output.read_bytes() == b"keep"
    with pytest.warns(ConversionWarning), pytest.raises(ValueError, match="max_blocks"):
        load_structure(path, max_blocks=26)
    assert path.read_bytes() == original
