import warnings
from itertools import product

import pytest
from amulet_nbt import ByteArrayTag, CompoundTag, ListTag, ShortTag, StringTag

from structura_core import ConversionWarning, convert_structure, load_structure
from structura_core.nbt import write_root

JAVA_FORMATS = (".nbt", ".snbt", ".litematic", ".schem")
WRITABLE_FORMATS = (*JAVA_FORMATS, ".mcstructure")


@pytest.fixture
def common_structure(make_structure):
    states = (
        "minecraft:stone", "minecraft:dirt", "minecraft:bedrock", "minecraft:air",
        "minecraft:oak_stairs[facing=east,half=bottom,shape=straight,waterlogged=true]",
    )
    source = make_structure(
        [(pos, (pos[0] + 3 * pos[1] + 7 * pos[2]) % len(states))
         for pos in product(range(3), range(2), range(5))],
        size=(3, 2, 5), palette=states,
    )
    source.data_version = 3953
    return source


@pytest.fixture
def legacy_source(tmp_path, monkeypatch):
    pytest.importorskip("amulet")
    monkeypatch.setenv("AMULET_LEVEL_CACHE_DIR", str(tmp_path / "amulet-cache"))
    source = tmp_path / "legacy.schematic"
    write_root(CompoundTag({
        "Width": ShortTag(3), "Height": ShortTag(2), "Length": ShortTag(4),
        "Materials": StringTag("Alpha"),
        "Blocks": ByteArrayTag([1, 3, 7, 0] * 6),
        "Data": ByteArrayTag([0] * 24),
        "TileEntities": ListTag(), "Entities": ListTag(),
    }), source, name="Schematic")
    return source


@pytest.mark.parametrize("first,second", [
    pair for pair in product(WRITABLE_FORMATS, repeat=2) if ".mcstructure" in pair
])
def test_bedrock_routes_preserve_common_states_over_repeated_cycles(
    tmp_path, common_structure, structure_snapshot, first, second,
):
    pytest.importorskip("amulet")
    expected = structure_snapshot(common_structure)
    current = convert_structure(common_structure, tmp_path / f"start{first}", strict=True)
    assert structure_snapshot(load_structure(current, strict=True)) == expected
    original = current.read_bytes()
    initial = current
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConversionWarning)
        for cycle in range(3):
            for step, suffix in enumerate((second, first)):
                current = convert_structure(current, tmp_path / f"cycle-{cycle}-{step}{suffix}")
                assert structure_snapshot(load_structure(current, strict=True)) == expected
    assert initial.read_bytes() == original
    assert structure_snapshot(common_structure) == expected


@pytest.mark.parametrize("target", WRITABLE_FORMATS)
def test_legacy_import_reaches_every_writer_without_changing_common_blocks(
    tmp_path, legacy_source, structure_snapshot, target,
):
    original = legacy_source.read_bytes()
    output = tmp_path / f"converted{target}"
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="Legacy schematic"):
        convert_structure(legacy_source, output, strict=True)
    assert output.read_bytes() == b"previous"
    with pytest.warns(ConversionWarning, match="Legacy schematic"):
        convert_structure(legacy_source, output)
    restored = load_structure(output, strict=True)
    states = ("minecraft:stone", "minecraft:dirt", "minecraft:bedrock", "minecraft:air")
    assert restored.size == (3, 2, 4)
    assert restored.data_version == (3953 if target == ".mcstructure" else 3955)
    assert restored.block_nbt == {} and restored.entities == []
    assert {pos: restored.name_at(pos) for pos in restored.present} == {
        (x, y, z): states[(x + 3 * z + 12 * y) % len(states)]
        for x, y, z in product(range(3), range(2), range(4))
    }
    expected = structure_snapshot(restored)
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", ConversionWarning)
        intermediate = convert_structure(output, tmp_path / "normalized.nbt")
        convert_structure(intermediate, output, strict=True)
    assert structure_snapshot(load_structure(output, strict=True)) == expected
    assert legacy_source.read_bytes() == original


@pytest.mark.parametrize("source_suffix", (*WRITABLE_FORMATS, ".schematic"))
def test_legacy_output_is_explicitly_unsupported_without_touching_files(tmp_path, source_suffix):
    source = tmp_path / f"input{source_suffix}"
    output = tmp_path / "output.schematic"
    source.write_bytes(b"source must not be read")
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="output must end in"):
        convert_structure(source, output)
    assert source.read_bytes() == b"source must not be read"
    assert output.read_bytes() == b"previous"
