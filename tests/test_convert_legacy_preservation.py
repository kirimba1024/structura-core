import logging

import numpy as np
import pytest
from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, IntTag, ListTag, ShortTag, StringTag,
)

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
    convert(str(source), str(output), 3955, preserve_all_entities=True, prepare_for_placement=False)
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


def test_historical_placement_cleanup_remains_available(tmp_path, monkeypatch):
    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "cache"))
    output = tmp_path / "prepared.nbt"
    convert(str(legacy_file(tmp_path)), str(output), 3955)
    structure = Structure(output)

    assert structure.size == (3, 1, 1)
    assert structure.name_at((2, 0, 0)) == "minecraft:cobblestone"
    assert structure.entities == []


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
