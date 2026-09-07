from pathlib import Path

import pytest
from amulet_nbt import IntTag, ListTag, StringTag

from structura_core import Litematic, Structure, export_litematic, load_structure
from structura_core.convert import main
from structura_core.nbt import load_root, save_structure

FIXTURE = Path(__file__).parent / "fixtures/signed-regions.litematic"


@pytest.mark.parametrize("suffix", ["nbt", "schem", "litematic"])
def test_native_converter_writes_supported_formats(tmp_path, suffix):
    output = tmp_path / f"result.{suffix}"
    main([str(FIXTURE), str(output), "--region", "negative"])
    root = load_root(output)
    assert root
    if suffix == "nbt":
        assert Structure(output).size == (5, 3, 7)
    elif suffix == "litematic":
        assert Litematic(output).to_structure().size == (5, 3, 7)
    else:
        assert root["Width"].py_data == 5


def test_native_copy_keeps_all_regions(tmp_path):
    output = tmp_path / "copy.litematic"
    main([str(FIXTURE), str(output)])
    assert load_root(output) == load_root(FIXTURE)


def test_structure_roundtrip_preserves_selected_palette(tmp_path):
    original = load_structure(FIXTURE, region="positive")
    nbt = tmp_path / "input.nbt"
    save_structure(original, nbt, original.size)
    output = tmp_path / "output.litematic"
    main([str(nbt), str(output)])
    assert load_structure(output).palette == original.palette


def test_sparse_metadata_counts_no_placement_markers(tmp_path):
    output = export_litematic(load_structure(FIXTURE), tmp_path / "output.litematic")
    src = load_structure(output)
    total = sum(src.palette[i] != "minecraft:air" for i in src.present.values())
    assert load_root(output)["Metadata"]["TotalBlocks"].py_data == total


def test_entity_positions_are_encoded_as_doubles(tmp_path):
    src = load_structure(FIXTURE, region="negative")
    src.entities[0]["pos"] = ListTag([IntTag(1), IntTag(2), IntTag(3)])
    output = export_litematic(src, tmp_path / "output.litematic")
    entity = next(iter(load_root(output)["Regions"].values()))["Entities"][0]
    assert entity["Pos"].list_data_type == 6


@pytest.mark.parametrize("invalid_id", [None, IntTag(1), StringTag("")])
def test_unusable_entity_ids_fail_before_writing(tmp_path, invalid_id):
    src = load_structure(FIXTURE, region="negative")
    nbt = src.entities[0]["nbt"]
    nbt.pop("id")
    if invalid_id is not None:
        nbt["id"] = invalid_id
    with pytest.raises(ValueError, match="nonempty string id"):
        export_litematic(src, tmp_path / "output.litematic")
    assert not (tmp_path / "output.litematic").exists()
