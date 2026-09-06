import pytest
from amulet_nbt import CompoundTag, DoubleTag, IntTag, ListTag, StringTag

from structura_core.nbt import Structure, load_root, save_structure, write_root


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
