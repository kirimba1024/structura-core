import math
from copy import deepcopy
from pathlib import Path

import pytest
from amulet_nbt import CompoundTag, IntTag, ListTag, LongArrayTag, StringTag

from structura_core import Litematic, Structure, export_litematic, load_structure, state_key
from structura_core.litematic import _unpack
from structura_core.nbt import load_root, save_structure

FIXTURE = Path(__file__).parent / "fixtures/signed-regions.litematic"


def test_independent_litemapy_fixture_handles_signed_regions_and_entities():
    document = Litematic(FIXTURE)
    src = document.to_structure()
    assert src.data_version == 3955
    assert src.size == (8, 3, 7)
    assert src.source_origin == (6, 18, 24)
    assert len(src.present) == 107
    for y in range(3):
        for z in range(7):
            for x in range(5):
                index = (y * 35 + z * 5 + x) % 34
                assert state_key(src.palette_raw[src.present[x, y, z]]) == f"example:block_{index}[variant=a]"
    assert src.name_at((6, 2, 6)) == "minecraft:stone"
    assert src.name_at((7, 2, 6)) == "minecraft:air"
    assert src.name_at((5, 2, 6)) is None
    tile = src.block_nbt[1, 1, 1]
    assert str(tile["CustomName"]) == '"kept"'
    assert tuple(int(tile[a].py_data) for a in "xyz") == (1, 1, 1)
    entity = src.entities[0]
    assert tuple(v.py_data for v in entity["pos"]) == (2.5, 1.75, 3.5)
    assert tuple(v.py_data for v in entity["blockPos"]) == (2, 1, 3)
    assert entity["nbt"]["Pos"] == entity["pos"]
    assert document.region_names == ("negative", "positive")


def test_native_save_retains_metadata_unknown_fields_and_ticks(tmp_path):
    document = Litematic(FIXTURE)
    document.root["Unknown"] = StringTag("keep")
    region = document.root["Regions"]["negative"]
    region["PendingBlockTicks"] = ListTag([CompoundTag({"Time": IntTag(25)})])
    before = deepcopy(document.root)
    src = document.to_structure()
    src.block_nbt[1, 1, 1]["CustomName"] = StringTag("independent")
    first = document.save(tmp_path / "one.litematic")
    second = document.save(tmp_path / "two.litematic")
    assert load_root(first) == before == document.root
    assert first.read_bytes() == second.read_bytes()


@pytest.mark.parametrize("version", [5, 6, 7])
def test_verified_format_versions(version):
    root = load_root(FIXTURE)
    root["Version"] = IntTag(version)
    assert Litematic.from_root(root).to_structure().size == (8, 3, 7)


@pytest.mark.parametrize("version", [1, 4, 8])
def test_unverified_versions_fail_explicitly(version):
    root = load_root(FIXTURE)
    root["Version"] = IntTag(version)
    with pytest.raises(ValueError, match="unsupported Litematic version"):
        Litematic.from_root(root)


def test_named_region_and_native_loader():
    src = load_structure(FIXTURE, region="positive")
    assert src.size == (2, 1, 1)
    assert src.source_origin == (12, 20, 30)
    assert src.entities == []
    with pytest.raises(ValueError, match="unknown Litematic region"):
        load_structure(FIXTURE, region="missing")
    with pytest.raises(ValueError, match="palette_index"):
        load_structure(FIXTURE, palette_index=1)


def test_overlapping_regions_fail_even_for_air():
    root = load_root(FIXTURE)
    root["Regions"]["duplicate"] = deepcopy(root["Regions"]["positive"])
    with pytest.raises(ValueError, match="overlapping Litematic regions"):
        Litematic.from_root(root).to_structure()
    assert Litematic.from_root(root).to_structure(region="negative").size == (5, 3, 7)


@pytest.mark.parametrize("mutation,pattern", [
    (lambda r: r["Size"].__setitem__("x", IntTag(0)), "nonzero"),
    (lambda r: r.__setitem__("BlockStates", LongArrayTag([])), "BlockStates length"),
    (lambda r: r.__setitem__("BlockStatePalette", ListTag()), "empty Litematic palette"),
    (lambda r: r["TileEntities"][0].__setitem__("x", IntTag(-1)), "tile entity outside"),
    (lambda r: r["TileEntities"].append(deepcopy(r["TileEntities"][0])), "duplicate Litematic tile"),
    (lambda r: r["Entities"][0].__setitem__("Pos", ListTag()), "three coordinates"),
])
def test_invalid_regions(mutation, pattern):
    root = load_root(FIXTURE)
    mutation(root["Regions"]["negative"])
    with pytest.raises(ValueError, match=pattern):
        Litematic.from_root(root).to_structure()


@pytest.mark.parametrize("limit", [0, -1, True, 1.2, 106])
def test_volume_limit_is_checked_before_unpacking(limit):
    document = Litematic(FIXTURE)
    document.root["Regions"]["negative"]["BlockStates"] = LongArrayTag([])
    with pytest.raises(ValueError, match="max_blocks"):
        document.to_structure(max_blocks=limit)


@pytest.mark.parametrize("bits", [2, 3, 5, 6, 9])
def test_bitstream_across_signed_word_boundaries(bits):
    count = 100
    palette_size = 1 << bits
    values = [(i * 13 + palette_size - 1) % palette_size for i in range(count)]
    binary = "".join(f"{v:0{bits}b}"[::-1] for v in values)
    words = [int(binary[i:i + 64].ljust(64, "0")[::-1], 2) for i in range(0, len(binary), 64)]
    signed = [v if v < 2 ** 63 else v - 2 ** 64 for v in words]
    assert list(_unpack(LongArrayTag(signed), count, palette_size)) == values


def test_palette_index_out_of_range_is_rejected():
    with pytest.raises(ValueError, match="palette index 3"):
        list(_unpack(LongArrayTag([3]), 1, 3))


def test_export_roundtrip_retains_blocks_properties_entities_and_does_not_mutate(tmp_path):
    src = load_structure(FIXTURE, region="negative")
    before = deepcopy(src.block_nbt), deepcopy(src.entities)
    first = export_litematic(src, tmp_path / "out.litematic", name="region", author="author")
    restored = load_structure(first)
    assert restored.size == src.size
    assert restored.data_version == src.data_version
    assert {p: state_key(restored.palette_raw[i]) for p, i in restored.present.items()} == {
        p: state_key(src.palette_raw[i]) for p, i in src.present.items()
    }
    assert restored.block_nbt == src.block_nbt
    assert restored.entities == src.entities
    assert (src.block_nbt, src.entities) == before
    second = export_litematic(src, tmp_path / "second.litematic", name="region", author="author")
    assert first.read_bytes() == second.read_bytes()
    save_structure(restored, tmp_path / "out.nbt", restored.size)
    assert Structure(tmp_path / "out.nbt").present == restored.present


def test_sparse_input_uses_explicit_structure_void(tmp_path):
    src = load_structure(FIXTURE)
    out = export_litematic(src, tmp_path / "out.litematic")
    restored = load_structure(out)
    assert len(restored.present) == math.prod(src.size)
    assert restored.name_at((5, 2, 6)) == "minecraft:structure_void"
    assert restored.name_at((7, 2, 6)) == "minecraft:air"


def test_failed_export_preserves_destination(tmp_path):
    output = tmp_path / "out.litematic"
    output.write_bytes(b"original")
    with pytest.raises(ValueError, match="max_blocks"):
        export_litematic(load_structure(FIXTURE), output, max_blocks=1)
    assert output.read_bytes() == b"original"
