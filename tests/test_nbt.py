import pytest
from amulet_nbt import CompoundTag, DoubleTag, IntTag, ListTag, LongArrayTag, StringTag

from structura_core.nbt import Structure, load_root, save_structure, write_root
from amulet_nbt import NamedTag


def structure_root(*, palettes=False):
    stone = CompoundTag({"Name": StringTag("minecraft:stone")})
    dirt = CompoundTag({"Name": StringTag("minecraft:dirt")})
    root = CompoundTag(
        {
            "DataVersion": IntTag(3955),
            "size": ListTag([IntTag(1), IntTag(1), IntTag(1)]),
            "blocks": ListTag(
                [
                    CompoundTag(
                        {
                            "pos": ListTag([IntTag(0), IntTag(0), IntTag(0)]),
                            "state": IntTag(0),
                        }
                    )
                ]
            ),
            "entities": ListTag(),
        }
    )
    if palettes:
        root["palettes"] = ListTag([ListTag([stone]), ListTag([dirt])])
    else:
        root["palette"] = ListTag([stone])
    return root


def test_memory_root_is_owned_and_uses_the_same_validation():
    root = structure_root(palettes=True)
    src = Structure.from_root(root, palette_index=1)
    assert src.name_at((0, 0, 0)) == "minecraft:dirt"
    root["palettes"][1][0]["Name"] = StringTag("minecraft:air")
    assert str(src.palette_raw[0]["Name"]) == "minecraft:dirt"
    with pytest.raises(ValueError, match="root must be"):
        Structure.from_root(ListTag())


@pytest.mark.parametrize("compressed", [False, True])
def test_memory_bytes_read_raw_and_gzip(compressed):
    data = NamedTag(structure_root()).save_to(compressed=compressed)
    assert Structure.from_bytes(data).name_at((0, 0, 0)) == "minecraft:stone"


@pytest.mark.parametrize("compressed", [False, True])
def test_structure_reads_raw_and_gzip_nbt(tmp_path, compressed):
    path = tmp_path / f"structure-{compressed}.nbt"
    write_root(structure_root(), path, compressed=compressed)

    structure = Structure(path)

    assert structure.name_at((0, 0, 0)) == "minecraft:stone"


def test_structure_selects_a_palette_from_multi_palette_files(tmp_path):
    path = tmp_path / "palettes.nbt"
    write_root(structure_root(palettes=True), path)

    assert Structure(path).name_at((0, 0, 0)) == "minecraft:stone"
    assert Structure(path, palette_index=1).name_at((0, 0, 0)) == "minecraft:dirt"
    with pytest.raises(ValueError, match="palette 2 is unavailable"):
        Structure(path, palette_index=2)


def test_save_is_reproducible_and_shifts_entity_coordinates(tmp_path):
    source_path = tmp_path / "source.nbt"
    root = structure_root()
    root["entities"] = ListTag(
        [
            CompoundTag(
                {
                    "pos": ListTag([DoubleTag(0.5), DoubleTag(0), DoubleTag(0.5)]),
                    "blockPos": ListTag([IntTag(0), IntTag(0), IntTag(0)]),
                    "nbt": CompoundTag({"id": StringTag("minecraft:item")}),
                }
            )
        ]
    )
    write_root(root, source_path)
    source = Structure(source_path)
    first = tmp_path / "first.nbt"
    second = tmp_path / "second.nbt"

    save_structure(source, first, (2, 1, 1), shift=(1, 0, 0))
    save_structure(source, second, (2, 1, 1), shift=(1, 0, 0))

    assert first.read_bytes() == second.read_bytes()
    entity = load_root(first)["entities"][0]
    assert [float(value.py_data) for value in entity["pos"]] == [1.5, 0, 0.5]
    assert [int(value.py_data) for value in entity["blockPos"]] == [1, 0, 0]


def test_additions_never_replace_authored_air(tmp_path):
    source_path = tmp_path / "source.nbt"
    root = structure_root()
    root["palette"].append(CompoundTag({"Name": StringTag("minecraft:air")}))
    root["blocks"][0]["state"] = IntTag(1)
    write_root(root, source_path)
    output = tmp_path / "output.nbt"

    save_structure(
        Structure(source_path), output, (1, 1, 1),
        additions=[((0, 0, 0), "minecraft:dirt")],
    )

    assert Structure(output).name_at((0, 0, 0)) == "minecraft:air"


def test_save_preserves_all_palettes_and_unknown_nbt_fields(tmp_path):
    path = tmp_path / "source.nbt"
    root = structure_root(palettes=True)
    root["author"] = StringTag("Builder")
    root["custom"] = CompoundTag({"values": LongArrayTag([1, 2, 3])})
    root["blocks"][0]["custom"] = StringTag("block metadata")
    write_root(root, path)

    source = Structure(path, palette_index=1)
    output = tmp_path / "saved.nbt"
    save_structure(source, output, source.size)

    assert load_root(output) == root
    assert Structure(output, palette_index=0).name_at((0, 0, 0)) == "minecraft:stone"
    assert Structure(output, palette_index=1).name_at((0, 0, 0)) == "minecraft:dirt"


def test_literal_additions_have_the_same_state_in_every_palette(tmp_path):
    path = tmp_path / "source.nbt"
    root = structure_root(palettes=True)
    write_root(root, path)
    source = Structure(path)
    output = tmp_path / "saved.nbt"

    save_structure(source, output, (2, 1, 1), additions=[((1, 0, 0), "minecraft:stone")])

    assert Structure(output, palette_index=1).name_at((0, 0, 0)) == "minecraft:dirt"
    for index in (0, 1):
        assert Structure(output, palette_index=index).name_at((1, 0, 0)) == "minecraft:stone"
    assert load_root(path) == root


def test_integer_additions_refer_to_corresponding_palette_variant(tmp_path):
    path = tmp_path / "source.nbt"
    write_root(structure_root(palettes=True), path)
    output = tmp_path / "saved.nbt"

    save_structure(Structure(path), output, (2, 1, 1), additions=[((1, 0, 0), 0)])

    assert Structure(output, palette_index=1).name_at((1, 0, 0)) == "minecraft:dirt"


@pytest.mark.parametrize("field", ["size", "pos", "state", "DataVersion"])
def test_loading_rejects_non_integer_nbt_fields(tmp_path, field):
    root = structure_root()
    if field in ("size", "pos"):
        values = ListTag([DoubleTag(1.9 if field == "size" else .9)] * 3)
        if field == "size":
            root[field] = values
        else:
            root["blocks"][0][field] = values
    elif field == "state":
        root["blocks"][0][field] = DoubleTag(.9)
    else:
        root[field] = DoubleTag(3955.9)
    path = tmp_path / "invalid.nbt"
    write_root(root, path)

    with pytest.raises(ValueError):
        Structure(path)


@pytest.mark.parametrize("kwargs", [
    {"size": (1.9, 1, 1)},
    {"size": (2 ** 32 + 1, 1, 1)},
    {"shift": (2 ** 32, 0, 0)},
    {"shift": (0.9, 0, 0)},
    {"shift": (0, 0)},
    {"shift": (0, 0, 0, 1)},
    {"replacements": [((0.9, 0, 0), "minecraft:dirt")]},
    {"replacements": [((0, 0, 0), 0.9)]},
    {"additions": [((0, 0, 0), True)]},
])
def test_invalid_save_arguments_leave_existing_destination_untouched(tmp_path, kwargs):
    path = tmp_path / "source.nbt"
    write_root(structure_root(), path)
    output = tmp_path / "existing.nbt"
    output.write_bytes(b"keep existing file")

    with pytest.raises(ValueError):
        save_structure(Structure(path), output, **{"size": (1, 1, 1), **kwargs})

    assert output.read_bytes() == b"keep existing file"


def test_all_palettes_are_validated_even_when_not_selected(tmp_path):
    root = structure_root(palettes=True)
    root["palettes"][1] = ListTag()
    path = tmp_path / "invalid.nbt"
    write_root(root, path)

    with pytest.raises(ValueError, match="palette"):
        Structure(path)


def test_shift_updates_known_entity_coordinates_without_mutating_source(tmp_path):
    root = structure_root()
    root["entities"] = ListTag([CompoundTag({
        "pos": ListTag([DoubleTag(.5), DoubleTag(0), DoubleTag(.5)]),
        "blockPos": ListTag([IntTag(0)] * 3),
        "nbt": CompoundTag({
            "id": StringTag("minecraft:item_frame"),
            "Pos": ListTag([DoubleTag(.5), DoubleTag(0), DoubleTag(.5)]),
            "TileX": IntTag(0), "TileY": IntTag(0), "TileZ": IntTag(0),
            "custom": CompoundTag({"x": IntTag(123)}),
        }),
    })])
    path = tmp_path / "source.nbt"
    write_root(root, path)
    source = Structure(path)
    output = tmp_path / "saved.nbt"

    save_structure(source, output, (2, 1, 1), shift=(1, 0, 0))

    entity = load_root(output)["entities"][0]
    assert entity["nbt"]["Pos"] == entity["pos"]
    assert entity["nbt"]["TileX"] == IntTag(1)
    assert entity["nbt"]["custom"]["x"] == IntTag(123)
    assert source.entities[0] == root["entities"][0]


def test_write_root_failure_preserves_previous_file_and_removes_temporary(tmp_path, monkeypatch):
    from structura_core import nbt

    path = tmp_path / "saved.nbt"
    path.write_bytes(b"original")

    def fail_replace(*args):
        raise OSError("simulated interrupted write")

    monkeypatch.setattr(nbt.os, "replace", fail_replace)
    with pytest.raises(OSError, match="interrupted"):
        write_root(structure_root(), path)

    assert path.read_bytes() == b"original"
    assert list(tmp_path.iterdir()) == [path]


def test_reassigning_active_palette_is_saved(tmp_path):
    path = tmp_path / "source.nbt"
    write_root(structure_root(palettes=True), path)
    source = Structure(path, palette_index=1)
    source.palette_raw = [CompoundTag({"Name": StringTag("minecraft:gold_block")})]
    output = tmp_path / "saved.nbt"

    save_structure(source, output, source.size)

    assert Structure(output, palette_index=1).name_at((0, 0, 0)) == "minecraft:gold_block"
    assert Structure(output, palette_index=0).name_at((0, 0, 0)) == "minecraft:stone"


def test_entity_coordinate_overflow_does_not_wrap_on_save(tmp_path):
    root = structure_root()
    root["entities"] = ListTag([CompoundTag({
        "pos": ListTag([DoubleTag(.5)] * 3),
        "blockPos": ListTag([IntTag(2 ** 31 - 1), IntTag(0), IntTag(0)]),
        "nbt": CompoundTag({"id": StringTag("minecraft:item")}),
    })])
    path = tmp_path / "source.nbt"
    write_root(root, path)
    output = tmp_path / "saved.nbt"

    with pytest.raises(ValueError, match="32-bit"):
        save_structure(Structure(path), output, (2, 1, 1), shift=(1, 0, 0))

    assert not output.exists()


@pytest.mark.parametrize("field", ["blocks", "entities", "palettes"])
def test_malformed_record_containers_raise_value_error(tmp_path, field):
    root = structure_root()
    root[field] = IntTag(123)
    path = tmp_path / "invalid.nbt"
    write_root(root, path)

    with pytest.raises(ValueError, match=field):
        Structure(path)
