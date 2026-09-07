from copy import deepcopy

import pytest
from amulet_nbt import (
    ByteArrayTag,
    CompoundTag,
    DoubleTag,
    IntArrayTag,
    IntTag,
    ListTag,
    ShortTag,
    StringTag,
)

from structura_core import Schematic, load_structure, save_structure
from structura_core.convert import main
from structura_core.export_schematic import export_schematic
from structura_core.nbt import load_root


def fixture(version=3):
    payload = CompoundTag({'CustomName': StringTag('fixture'), 'Items': ListTag()})
    block_entity = CompoundTag({'Id': StringTag('minecraft:chest'), 'Pos': IntArrayTag([1, 1, 2])})
    entity = CompoundTag({'Id': StringTag('minecraft:armor_stand'),
                          'Pos': ListTag([DoubleTag(v) for v in (1.25, 1.75, 2.5)])})
    for record in (block_entity, entity):
        if version == 3:
            record['Data'] = deepcopy(payload)
        else:
            record.update(deepcopy(payload))
    root = CompoundTag({
        'Version': IntTag(version), 'DataVersion': IntTag(3700),
        'Width': ShortTag(2), 'Height': ShortTag(3), 'Length': ShortTag(4),
        'Offset': IntArrayTag([-12, 5, 9]), 'Metadata': CompoundTag({'Author': StringTag('tester')}),
        'Entities': ListTag([entity]), 'Future': StringTag('keep'),
    })
    blocks = CompoundTag({
        'Palette': CompoundTag({'minecraft:air': IntTag(0), 'minecraft:chest[facing=north]': IntTag(130)}),
        'Data': ByteArrayTag([item for index in range(24) for item in ([-126, 1] if index % 2 else [0])]),
        'BlockEntities': ListTag([block_entity]),
    })
    biomes = CompoundTag({'Palette': CompoundTag({'minecraft:plains': IntTag(0)}), 'Data': ByteArrayTag([0] * 24)})
    if version == 2:
        root['Palette'] = blocks['Palette']
        root['PaletteMax'] = IntTag(131)
        root['BlockData'] = blocks['Data']
        root['BlockEntities'] = blocks['BlockEntities']
        root['BiomePalette'] = biomes['Palette']
        root['BiomeData'] = ByteArrayTag([0] * 8)
        return root
    root['Blocks'] = blocks
    root['Biomes'] = biomes
    return CompoundTag({'Schematic': root, 'WrapperField': StringTag('preserved')})


@pytest.mark.parametrize('version', [2, 3])
def test_sponge_coordinates_states_nbt_and_native_preservation(tmp_path, version):
    source = fixture(version)
    document = Schematic.from_root(source)
    src = document.to_structure()
    assert src.size == (2, 3, 4) and src.data_version == 3700
    assert src.source_origin == (-12, 5, 9)
    assert len(src.present) == 24
    for x in range(2):
        for y in range(3):
            for z in range(4):
                assert src.name_at((x, y, z)) == ('minecraft:air' if x == 0 else 'minecraft:chest')
    assert str(src.palette_raw[1]['Properties']['facing']) == 'north'
    assert str(src.block_nbt[1, 1, 2]['CustomName']) == 'fixture'
    assert str(src.block_nbt[1, 1, 2]['id']) == 'minecraft:chest'
    assert [float(v) for v in src.entities[0]['pos']] == [1.25, 1.75, 2.5]
    assert str(src.entities[0]['nbt']['CustomName']) == 'fixture'
    output = tmp_path / 'copy.schem'
    document.save(output)
    assert load_root(output) == source
    assert source == fixture(version)
    converted = tmp_path / 'copy.nbt'
    save_structure(src, converted, src.size)
    restored = load_structure(converted)
    assert restored.present == src.present
    assert restored.block_nbt == src.block_nbt
    assert restored.entities == src.entities
    assert load_structure(output).present == src.present
    export_schematic(src, tmp_path / 'v2.schem')
    assert load_structure(tmp_path / 'v2.schem').present == src.present


@pytest.mark.parametrize('data', [[-128], [0] * 23, [0] * 25, [1] * 24, [-1] * 5, [-1, -1, -1, -1, 8]])
def test_malformed_varints_are_rejected(data):
    root = fixture()
    root['Schematic']['Blocks']['Data'] = ByteArrayTag(data)
    with pytest.raises(ValueError, match='BlockData'):
        Schematic.from_root(root).to_structure()


@pytest.mark.parametrize('field,value', [
    ('Blocks', ListTag()), ('Width', ShortTag(0)), ('Height', IntTag(3)),
    ('Offset', IntArrayTag([1, 2])), ('Metadata', ListTag()),
    ('Entities', CompoundTag()), ('Version', IntTag(4)),
])
def test_invalid_containers_headers_and_versions(field, value):
    root = fixture()
    root['Schematic'][field] = value
    with pytest.raises(ValueError):
        Schematic.from_root(root).to_structure()


@pytest.mark.parametrize('case', ['duplicate_palette', 'negative_palette', 'duplicate_entity', 'outside_entity', 'missing_id', 'bad_biomes', 'bad_data'])
def test_invalid_palette_entities_and_biomes(case):
    root = fixture()
    blocks = root['Schematic']['Blocks']
    if case == 'duplicate_palette':
        blocks['Palette']['minecraft:stone'] = IntTag(130)
    elif case == 'negative_palette':
        blocks['Palette']['minecraft:stone'] = IntTag(-1)
    elif case == 'duplicate_entity':
        blocks['BlockEntities'].append(deepcopy(blocks['BlockEntities'][0]))
    elif case == 'outside_entity':
        blocks['BlockEntities'][0]['Pos'] = IntArrayTag([2, 1, 2])
    elif case == 'missing_id':
        blocks['BlockEntities'][0].pop('Id')
    elif case == 'bad_biomes':
        root['Schematic']['Biomes']['Data'] = ByteArrayTag([1] * 24)
    else:
        root['Schematic']['Entities'][0]['Data'] = StringTag('wrong')
    with pytest.raises(ValueError):
        Schematic.from_root(root).to_structure()


def test_budget_precedes_decoding_and_unsigned_dimensions_work():
    root = fixture()
    root['Schematic']['Width'] = ShortTag(-32768)
    root['Schematic']['Blocks']['Data'] = ByteArrayTag([-128])
    document = Schematic.from_root(root)
    assert document.size == (32768, 3, 4)
    with pytest.raises(ValueError, match='max_blocks'):
        document.to_structure(max_blocks=10)


def test_v3_without_blocks_does_not_invent_air():
    root = fixture()
    del root['Schematic']['Blocks']
    src = Schematic.from_root(root).to_structure()
    assert not src.present and not src.palette and len(src.entities) == 1


def test_cli_native_copy_retains_biomes_and_cross_format_is_explicit(tmp_path):
    source, copied, nbt = [tmp_path / name for name in ('in.schem', 'out.schem', 'out.nbt')]
    Schematic.from_root(fixture()).save(source)
    main([str(source), str(copied)])
    assert load_root(copied) == load_root(source)
    main([str(source), str(nbt)])
    assert len(load_structure(nbt).present) == 24
    before = nbt.read_bytes()
    with pytest.raises(SystemExit):
        main([str(source), str(nbt), '--max-blocks', '1'])
    assert nbt.read_bytes() == before


@pytest.mark.parametrize('version', [2, 3])
def test_independent_amulet_fixtures_with_multibyte_palette(version):
    from pathlib import Path
    path = Path(__file__).parent / 'fixtures' / f'amulet-v{version}.schem'
    document = Schematic(path)
    src = document.to_structure()
    assert src.size == (5, 3, 13) and len(src.present) == 195
    assert src.source_origin == (-5, 6, 2) and src.data_version == 3700
    for pos, index in src.present.items():
        x, y, z = pos
        assert int(str(src.palette_raw[index]['Properties']['index'])) == ((x * 3 + y) * 13 + z) % 130
    assert str(src.block_nbt[1, 1, 2]['CustomName']) == 'independent'
    assert str(src.block_nbt[1, 1, 2]['id']) == 'fixture:container'
