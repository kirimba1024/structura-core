from copy import deepcopy
from pathlib import Path
import warnings

import pytest
from amulet_nbt import ByteArrayTag, CompoundTag, IntArrayTag, IntTag, ListTag, ShortTag, StringTag

from structura_core import ConversionWarning, Mcstructure, Schematic, Structure, convert_structure, load_structure, parse_state, state_key
from structura_core.nbt import load_root


def structure(states=("minecraft:stone",), size=(3, 2, 4)):
    src = Structure.from_root(CompoundTag({
        "DataVersion": IntTag(3955), "size": ListTag([IntTag(value) for value in size]),
        "palette": ListTag([parse_state(state) for state in states]), "blocks": ListTag(), "entities": ListTag(),
    }))
    src.present = {(index, 0, 0): index for index in range(len(states))}
    return src


def bedrock_root():
    return CompoundTag({
        "format_version": IntTag(1), "size": ListTag([IntTag(v) for v in (1, 1, 2)]),
        "structure_world_origin": ListTag([IntTag(v) for v in (-12, 7, 4)]),
        "future": StringTag("Привет 🌍\x00"),
        "structure": CompoundTag({
            "block_indices": ListTag([ListTag([IntTag(0), IntTag(-1)]), ListTag([IntTag(-1), IntTag(-1)])]),
            "entities": ListTag([CompoundTag({"identifier": StringTag("minecraft:pig"), "Unknown": IntTag(9)})]),
            "palette": CompoundTag({"default": CompoundTag({
                "block_palette": ListTag([CompoundTag({"name": StringTag("minecraft:stone"), "states": CompoundTag(),
                                                        "version": IntTag(18153475)})]),
                "block_position_data": CompoundTag({"0": CompoundTag({"future": StringTag("keep")})}),
            })}),
        }),
    })


def test_snbt_roundtrip_preserves_variants_metadata_entities_and_types(tmp_path):
    src = structure()
    src._root["custom"] = CompoundTag({"byte_array": ByteArrayTag([1, -2]), "int_array": IntArrayTag([3, 4]),
                                        "name": StringTag("Привет 🌍")})
    src.palettes_raw.append([parse_state("minecraft:gold_block")])
    src._root["palettes"] = ListTag([ListTag(values) for values in src.palettes_raw])
    src.block_nbt[0, 0, 0] = CompoundTag({"Custom": StringTag("retained")})
    binary, text, restored = [tmp_path / name for name in ("in.nbt", "out.snbt", "restored.nbt")]
    convert_structure(src, binary, strict=True)
    convert_structure(binary, text, strict=True)
    convert_structure(text, restored, strict=True)
    assert text.read_text(encoding="utf-8").startswith("{")
    assert load_root(binary) == load_root(restored)
    assert load_structure(text, palette_index=1).name_at((0, 0, 0)) == "minecraft:gold_block"


@pytest.mark.parametrize("data", [b"broken", b"[1,2,3]", b"{bad", b"\xff", b"{}{}", b"{} trailing"])
def test_invalid_snbt_never_overwrites_destination(tmp_path, data):
    source, output = tmp_path / "bad.snbt", tmp_path / "out.nbt"
    source.write_bytes(data)
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="SNBT"):
        convert_structure(source, output)
    assert output.read_bytes() == b"previous"


def test_snbt_limit_is_checked_before_parse(tmp_path):
    source = tmp_path / "large.snbt"
    source.write_bytes(b" " * 100)
    with pytest.raises(ValueError, match="max_nbt_bytes"):
        load_structure(source, max_nbt_bytes=20)


def test_snbt_nested_compounds_and_quoted_braces_are_complete(tmp_path):
    path = tmp_path / "quoted.snbt"
    path.write_text(' {nested: {text: "braces } { and \\\"quotes\\\""}, other: \'} {\'} \n')
    assert str(load_root(path)["nested"]["text"]) == 'braces } { and "quotes"'


def test_sponge_v1_native_copy_and_explicit_source_version(tmp_path):
    root = CompoundTag({"Version": IntTag(1), "Width": ShortTag(1), "Height": ShortTag(1), "Length": ShortTag(1),
                        "Palette": CompoundTag({"minecraft:chest[facing=north]": IntTag(0)}),
                        "BlockData": ByteArrayTag([0]), "TileEntities": ListTag([CompoundTag({
                            "Id": StringTag("minecraft:chest"), "Pos": IntArrayTag([0, 0, 0]),
                            "ContentVersion": IntTag(1), "Items": ListTag(), "Custom": StringTag("keep")})])})
    source, copy, normalized = [tmp_path / name for name in ("v1.schem", "copy.schem", "copy.nbt")]
    document = Schematic.from_root(root)
    document.save(source)
    convert_structure(source, copy, strict=True)
    assert load_root(copy) == root
    with pytest.raises(ValueError, match="DataVersion"):
        load_structure(source)
    convert_structure(source, normalized, source_data_version=1343, strict=True)
    src = load_structure(normalized)
    assert src.data_version == 1343
    assert str(src.block_nbt[0, 0, 0]["Custom"]) == "keep"
    assert str(src.block_nbt[0, 0, 0]["id"]) == "minecraft:chest"
    with pytest.raises(ValueError, match="disagrees"):
        document.root["DataVersion"] = IntTag(1343)
        document.to_structure(data_version=3955)


def test_native_bedrock_copy_preserves_unknown_data_utf8_and_layers(tmp_path):
    root = bedrock_root()
    source, output = tmp_path / "in.mcstructure", tmp_path / "out.mcstructure"
    document = Mcstructure.from_root(root)
    document.root["future"] = StringTag("owned")
    assert root == bedrock_root()
    Mcstructure.from_root(root).save(source)
    convert_structure(source, output, strict=True)
    assert Mcstructure(output).root == root
    assert source.read_bytes() == output.read_bytes()


@pytest.mark.parametrize("kind", ["size", "layers", "index", "position", "version"])
def test_invalid_bedrock_rejected_before_write(tmp_path, kind):
    document = Mcstructure.from_root(bedrock_root())
    output = tmp_path / "out.mcstructure"
    output.write_bytes(b"previous")
    if kind == "size":
        document.root["size"][0] = IntTag(10_000_000)
    elif kind == "layers":
        document.structure["block_indices"].pop()
    elif kind == "index":
        document.layers[0][0] = IntTag(5)
    elif kind == "position":
        document.position_data["-1"] = CompoundTag()
    else:
        document.root["format_version"] = IntTag(2)
    with pytest.raises(ValueError):
        document.save(output)
    assert output.read_bytes() == b"previous"


def test_bedrock_translation_waterlogging_air_and_sparse_cells(tmp_path):
    pytest.importorskip("amulet")
    src = structure(("minecraft:stone", "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=true]",
                     "minecraft:air"))
    before = deepcopy(src.present)
    path = convert_structure(src, tmp_path / "water.mcstructure", strict=True)
    document = Mcstructure(path)
    assert document.layers[1][8] != IntTag(-1)
    assert document.layers[0][1] == IntTag(-1)
    restored = load_structure(path, strict=True)
    assert restored.present.keys() == src.present.keys()
    for pos in src.present:
        assert state_key(restored.palette_raw[restored.present[pos]]) == state_key(src.palette_raw[src.present[pos]])
    assert restored.data_version == 3953
    assert src.present == before


def test_bedrock_unknown_blocks_future_versions_and_entities_are_explicit(tmp_path):
    pytest.importorskip("amulet")
    src = structure(("custom:unknown",))
    output = tmp_path / "out.mcstructure"
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="translation"):
        convert_structure(src, output)
    src = structure()
    src.data_version = 999999
    with pytest.raises(ValueError, match="does not cover"):
        convert_structure(src, output)
    assert output.read_bytes() == b"previous"
    document = Mcstructure.from_root(bedrock_root())
    with pytest.raises(ValueError, match="entities omitted"):
        document.to_structure(strict=True)
    with pytest.warns(ConversionWarning, match="entities omitted"):
        converted = document.to_structure()
    assert converted.source_origin == (-12, 7, 4)
    assert converted.name_at((0, 0, 0)) == "minecraft:stone"


def test_unused_bedrock_palette_entries_do_not_require_translation():
    pytest.importorskip("amulet")
    document = Mcstructure.from_root(bedrock_root())
    document.states.append(CompoundTag({"name": StringTag("custom:unused")}))
    with pytest.warns(ConversionWarning):
        assert document.to_structure().name_at((0, 0, 0)) == "minecraft:stone"


def test_bedrock_name_cannot_hide_java_state_properties():
    root = bedrock_root()
    root["structure"]["palette"]["default"]["block_palette"][0]["name"] = StringTag("minecraft:stone[invalid=true]")
    with pytest.raises(ValueError, match="names cannot include"):
        Mcstructure.from_root(root)


def test_bedrock_structure_losses_are_reported_once(tmp_path):
    pytest.importorskip("amulet")
    src = structure()
    src._root["extra"] = IntTag(1)
    with warnings.catch_warnings(record=True) as notices:
        warnings.simplefilter("always", ConversionWarning)
        convert_structure(src, tmp_path / "model.mcstructure")
    assert sum("Structure metadata" in str(notice.message) for notice in notices) == 1


def test_bedrock_chest_preserves_supported_payload_and_reports_limits(tmp_path):
    pytest.importorskip("amulet")
    src = structure(("minecraft:chest[facing=north,type=single,waterlogged=false]",))
    src.block_nbt[0, 0, 0] = CompoundTag({"id": StringTag("minecraft:chest"), "Items": ListTag(), "CustomName": StringTag('"My chest"')})
    output = tmp_path / "chest.mcstructure"
    with pytest.raises(ValueError, match="NBT fidelity"):
        convert_structure(src, output, strict=True)
    assert not output.exists()
    with pytest.warns(ConversionWarning, match="NBT fidelity"):
        convert_structure(src, output)
    with pytest.warns(ConversionWarning, match="NBT fidelity"):
        restored = load_structure(output)
    assert restored.name_at((0, 0, 0)) == "minecraft:chest"
    assert str(restored.block_nbt[0, 0, 0]["id"]) == "minecraft:chest"


def test_independently_written_bedrock_fixture_has_correct_axes_and_origin(tmp_path):
    document = Mcstructure(Path(__file__).parent / "fixtures/amulet-bedrock.mcstructure")
    assert document.size == (3, 2, 4)
    assert document.origin == (-3, 6, 2)
    for index, state in enumerate(document.layers[0]):
        expected = "minecraft:dirt" if index % 2 else "minecraft:stone"
        assert str(document.states[int(state)]["name"]) == expected
    copy = document.save(tmp_path / "copy.mcstructure")
    assert Mcstructure(copy).root == document.root


def test_exported_bedrock_is_readable_by_independent_amulet_reader(tmp_path):
    pytest.importorskip("amulet")
    from amulet.level.formats.mcstructure.format_wrapper import MCStructureFormatWrapper

    src = structure(("minecraft:stone", "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=true]"))
    path = convert_structure(src, tmp_path / "scene.mcstructure", strict=True)
    wrapper = MCStructureFormatWrapper(str(path))
    try:
        wrapper.open()
        assert wrapper.bounds(wrapper.dimensions[0]).bounds == ((0, 0, 0), src.size)
        data = wrapper._get_raw_chunk_data(0, 0, wrapper.dimensions[0])
        cells = data.palette[data.blocks]
        assert str(cells[0, 0, 0][0]["name"]) == "minecraft:stone"
        assert [str(block["name"]) for block in cells[1, 0, 0]] == ["minecraft:oak_stairs", "minecraft:water"]
    finally:
        wrapper.close()
