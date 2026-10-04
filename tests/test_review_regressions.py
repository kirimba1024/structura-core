import os
import random
from pathlib import Path

import numpy as np
import pytest
from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, FloatTag, IntArrayTag,
    IntTag, ListTag, LongArrayTag, LongTag, ShortTag, StringTag, from_snbt,
)

from structura_core.nbt_io import atomic_write
from structura_core.snbt_reader import load_snbt
from structura_core.world_staging import StagedWorld, restore_backup


@pytest.mark.parametrize("text", [
    '{}', '{"": "", integer: 2147483648, byte: 128b}',
    '{double:"quoted \\\" text"}',
    r'{text:"braces } [ ] { ; slash \\ and literal \n",path:foo.bar+bar-baz}',
    '{byte:-2B,short:3s,long:5L,float:1e3f,double:.5d,plain:5.,exponent:1e3}',
    '{true:TRUE,false:false,array:[B;1b,-2b],ints:[I;1,-2],longs:[L;1L,-2L]}',
    '{nested:[{value:[1,2,]},{value:[]}],trailing:1,}',
])
def test_linear_snbt_matches_supported_amulet_types(text):
    assert load_snbt(text) == from_snbt(text)


def test_linear_snbt_roundtrips_random_nbt_without_changing_types():
    rng = random.Random(17)
    constructors = (ByteTag, ShortTag, IntTag, LongTag, FloatTag, DoubleTag)
    for _ in range(100):
        values = {str(index): constructor(rng.randint(-100, 100)) for index, constructor in enumerate(constructors)}
        values.update({
            'text': StringTag('Привет 🌍 "quotes" \\ newline\n'),
            'bytes': ByteArrayTag([-128, -1, 0, 127]),
            'ints': IntArrayTag([-2**31, 0, 2**31-1]),
            'longs': LongArrayTag([-2**63, 0, 2**63-1]),
            'nested': CompoundTag({'list': ListTag([IntTag(rng.randint(-100, 100)) for _ in range(12)])}),
        })
        original = CompoundTag(values)
        assert load_snbt(original.to_snbt(indent=2)) == original


def test_single_quoted_snbt_unescapes_its_quote():
    assert load_snbt("{text:'quoted \\\' text'}")['text'] == StringTag("quoted ' text")


@pytest.mark.parametrize("text", ['{} {}', '{} trailing', '{x:[1,2b]}', '{x:[B;1]}', '{x:"unterminated}', '{x:}', '{x:[I;1l]}'])
def test_linear_snbt_rejects_invalid_input(text):
    with pytest.raises(ValueError):
        load_snbt(text)


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permission bits')
def test_atomic_write_and_world_save_preserve_existing_permissions(tmp_path):
    file = tmp_path / 'structure.nbt'
    file.write_bytes(b'old')
    file.chmod(0o640)
    atomic_write(file, b'new')
    assert file.stat().st_mode & 0o777 == 0o640
    world = tmp_path / 'world'
    world.mkdir()
    target = world / 'level.dat'
    target.write_bytes(b'old')
    target.chmod(0o644)
    staged = StagedWorld(world, tmp_path / 'staged')
    staged.file(target).write_bytes(b'new')
    staged.changed.add(Path('level.dat'))
    backup = staged.install()
    assert target.stat().st_mode & 0o777 == 0o644
    target.unlink()
    restore_backup(world, backup)
    assert target.stat().st_mode & 0o777 == 0o644


@pytest.mark.skipif(os.name != 'posix', reason='POSIX permission bits')
def test_new_atomic_file_uses_the_process_umask(tmp_path):
    reference = tmp_path / 'reference'
    reference.write_bytes(b'ordinary file')
    target = tmp_path / 'atomic'
    atomic_write(target, b'new')
    assert target.stat().st_mode & 0o777 == reference.stat().st_mode & 0o777


def test_backup_stays_restorable_after_world_is_moved(tmp_path):
    world = tmp_path / 'world'
    world.mkdir()
    target = world / 'level.dat'
    target.write_bytes(b'old')
    staged = StagedWorld(world, tmp_path / 'staged')
    staged.file(target).write_bytes(b'new')
    staged.changed.add(Path('level.dat'))
    backup = staged.install()
    moved = tmp_path / 'renamed'
    world.rename(moved)
    restore_backup(moved, moved / backup.relative_to(world))
    assert (moved / 'level.dat').read_bytes() == b'old'


def test_large_region_backups_share_unchanged_pages_and_restore_after_a_move(tmp_path):
    from structura_core.world_backup import verify_backup
    world = tmp_path / 'world'
    target = world / 'region' / 'r.0.0.mca'
    target.parent.mkdir(parents=True)
    original = random.Random(8).randbytes(1024 * 1024 + 700)
    target.write_bytes(original)
    backups = []
    for index in range(5):
        staged = StagedWorld(world, tmp_path / f'staged-{index}')
        destination = staged.file(target)
        data = bytearray(destination.read_bytes())
        data[100 + index] ^= 1
        destination.write_bytes(data)
        staged.changed.add(Path('region/r.0.0.mca'))
        backups.append(staged.install())
    assert all(verify_backup(backup) for backup in backups)
    stored_bytes = sum(file.stat().st_size for file in (world / '.structura').rglob('*') if file.is_file())
    assert stored_bytes < len(original) * 1.5
    moved = tmp_path / 'moved'
    world.rename(moved)
    restore_backup(moved, moved / backups[0].relative_to(world))
    assert (moved / 'region/r.0.0.mca').read_bytes() == original


def test_corrupt_shared_backup_page_is_rejected_before_the_world_changes(tmp_path):
    from structura_core.world_backup import verify_backup
    world = tmp_path / 'world'
    world.mkdir()
    target = world / 'region.mca'
    target.write_bytes(b'a' * (1024 * 1024 + 1))
    staged = StagedWorld(world, tmp_path / 'staged')
    staged.file(target).write_bytes(b'b' * (1024 * 1024 + 1))
    staged.changed.add(Path('region.mca'))
    backup = staged.install()
    next((world / '.structura' / 'backup-blobs').iterdir()).write_bytes(b'corrupt')
    assert not verify_backup(backup)
    with pytest.raises(ValueError, match='manifest hashes'):
        restore_backup(world, backup)
    assert target.read_bytes() == b'b' * (1024 * 1024 + 1)


def test_litematic_unpack_uses_all_crossing_bit_widths():
    from structura_core.litematic import _pack, _unpack
    for bits in range(2, 22):
        palette = 1 << bits
        expected = np.random.default_rng(bits).integers(0, palette, size=127, dtype=np.int32)
        assert np.array_equal(_unpack(_pack(expected, len(expected), palette), len(expected), palette), expected)


@pytest.mark.parametrize('command', ['convert', 'export_schematic', 'convert_legacy'])
def test_cli_runtime_errors_have_one_message_and_no_traceback(tmp_path, capsys, command):
    import importlib
    module = importlib.import_module('structura_core.' + command)
    with pytest.raises(SystemExit) as result:
        module.main([str(tmp_path / 'missing.nbt'), str(tmp_path / 'out.nbt')])
    assert result.value.code == 1
    output = capsys.readouterr()
    assert 'error:' in output.err and 'Traceback' not in output.err
    assert not (tmp_path / 'out.nbt').exists()
@pytest.mark.parametrize('source,target,expected', [
    ('minecraft:warped_stem[axis=x]', 'minecraft:mushroom_stem', 'minecraft:mushroom_stem'),
    ('minecraft:mushroom_stem[east=false]', 'minecraft:crimson_stem', 'minecraft:crimson_stem'),
    ('minecraft:warped_stem[axis=z]', 'minecraft:crimson_stem', 'minecraft:crimson_stem[axis=z]'),
])
def test_material_replacement_does_not_confuse_mushroom_faces_with_stem_axis(source, target, expected):
    from structura_core.blockstates import replace_material

    assert replace_material(source, target) == expected
