import gzip
import warnings
from copy import deepcopy
from pathlib import Path

import pytest
from amulet_nbt import CompoundTag, IntTag, ListTag, NamedTag, StringTag

from structura_core import ConversionWarning, Litematic, Schematic, Structure, convert_structure, load_structure
from structura_core.convert import main
from structura_core.nbt import load_root

FIXTURE = Path(__file__).parent / "fixtures/signed-regions.litematic"


def structure():
    return Structure.from_root(CompoundTag({
        "DataVersion": IntTag(3955), "size": ListTag([IntTag(1)] * 3),
        "palette": ListTag([CompoundTag({"Name": StringTag("minecraft:stone")})]),
        "blocks": ListTag([CompoundTag({"pos": ListTag([IntTag(0)] * 3), "state": IntTag(0)})]),
        "entities": ListTag(),
    }))


@pytest.mark.parametrize("suffix", [".nbt", ".litematic", ".schem"])
def test_python_conversion_preserves_source_and_matches_cli(tmp_path, suffix):
    src = structure()
    before = deepcopy(src.__dict__)
    output = convert_structure(src, tmp_path / f"api{suffix}", strict=True)
    assert output.is_absolute()
    assert src.__dict__ == before
    native = convert_structure(src, tmp_path / "source.nbt")
    main([str(native), str(tmp_path / f"cli{suffix}"), "--strict"])
    restored = load_structure(output)
    assert {pos: restored.name_at(pos) for pos in restored.present} == {pos: src.name_at(pos) for pos in src.present}
    assert restored.present == load_structure(tmp_path / f"cli{suffix}").present


@pytest.mark.parametrize("suffix", [".nbt", ".litematic", ".schem"])
def test_strict_native_conversion_rejects_losses_without_touching_output(tmp_path, suffix):
    output = tmp_path / f"existing{suffix}"
    output.write_bytes(b"previous")
    with pytest.raises(ValueError, match="region names/layout"):
        convert_structure(FIXTURE, output, region="negative", strict=True)
    assert output.read_bytes() == b"previous"
    with pytest.warns(ConversionWarning, match="source origin/offset") as notices:
        convert_structure(FIXTURE, output, region="negative")
    assert len(notices) == 1
    assert load_structure(output).size == (5, 3, 7)


@pytest.mark.parametrize("fixture", ["signed-regions.litematic", "amulet-v2.schem", "amulet-v3.schem"])
def test_strict_document_copy_is_lossless_and_quiet(tmp_path, fixture):
    source = FIXTURE.parent / fixture
    with warnings.catch_warnings(record=True) as notices:
        output = convert_structure(source, tmp_path / fixture, strict=True)
    assert not notices and load_root(output) == load_root(source)


def test_only_present_losses_are_reported(tmp_path):
    src = structure()
    src._root["Author"] = StringTag("Builder")
    src.palettes_raw.append(deepcopy(src.palette_raw))
    src.present.clear()
    src._block_records.clear()
    with pytest.warns(ConversionWarning) as notices:
        convert_structure(src, tmp_path / "result.schem")
    message = str(notices[0].message)
    assert "Author" in message and "alternative palette" in message and "omitted cell" in message
    assert "biomes" not in message and "Litematic" not in message


def test_cli_loss_notice_goes_to_stderr(tmp_path, capsys):
    main([str(FIXTURE), str(tmp_path / "result.nbt")])
    result = capsys.readouterr()
    assert "warning: Conversion omits:" in result.err
    assert "warning" not in result.out and "result.nbt" in result.out


def test_bounded_raw_and_gzip_nbt_use_the_same_parser_contract(tmp_path):
    root = structure()._root
    root["Extra"] = StringTag("x" * 4096)
    raw = NamedTag(root).save_to(compressed=False)
    for data in (raw, gzip.compress(raw)):
        output = tmp_path / "bounded.nbt"
        output.write_bytes(data)
        assert load_root(output, max_nbt_bytes=len(raw)) == root
        assert Structure.from_bytes(data, max_nbt_bytes=len(raw)).size == (1, 1, 1)
        with pytest.raises(ValueError, match="max_nbt_bytes"):
            load_root(output, max_nbt_bytes=len(raw) - 1)
        with pytest.raises(ValueError, match="max_nbt_bytes"):
            Structure.from_bytes(data, max_nbt_bytes=len(raw) - 1)


def test_expansion_limit_rejects_before_parser(monkeypatch):
    from structura_core import nbt

    def unexpected_parser(*args, **kwargs):
        pytest.fail("oversized data reached NBT parser")

    monkeypatch.setattr(nbt, "load_nbt", unexpected_parser)
    with pytest.raises(ValueError, match="max_nbt_bytes"):
        Structure.from_bytes(gzip.compress(b"x" * 100_000), max_nbt_bytes=1024)


@pytest.mark.parametrize("limit", [0, -1, True, 1.5])
def test_invalid_byte_limits_are_rejected(limit):
    with pytest.raises(ValueError, match="max_nbt_bytes"):
        Structure.from_bytes(b"", max_nbt_bytes=limit)


@pytest.mark.parametrize("reader,fixture", [(Litematic, "signed-regions.litematic"), (Schematic, "amulet-v3.schem")])
def test_native_documents_honor_byte_limit(reader, fixture):
    with pytest.raises(ValueError, match="max_nbt_bytes"):
        reader(FIXTURE.parent / fixture, max_nbt_bytes=16)


def test_truncated_gzip_is_an_actionable_value_error():
    with pytest.raises(ValueError, match="gzip"):
        Structure.from_bytes(gzip.compress(b"NBT")[:-4])


@pytest.mark.parametrize("data", [b"", b"wrong", b"\x0a\x00\x00"])
def test_malformed_nbt_is_an_actionable_value_error(data):
    with pytest.raises(ValueError, match="invalid NBT"):
        Structure.from_bytes(data)
