import pytest
from amulet_nbt import from_snbt

from structura_core.compatibility import transfer_reason, world_write_reason
from structura_core.nbt import write_root
from structura_core.world import JavaWorld
from structura_core.world_entities import player_entities


def test_transfer_versions_and_supported_world_range_are_explicit():
    assert transfer_reason(3955, 2865)
    assert not transfer_reason(3955, 3955)
    assert world_write_reason(3956)
    assert not world_write_reason(3955)
    assert world_write_reason(2230)


@pytest.mark.parametrize('reference', ['[I;1,2,3,4]', '"00000001-0000-0002-0000-000300000004"'])
def test_new_player_storage_and_dimension_can_be_read_without_writes(tmp_path, reference):
    root = from_snbt('{Data:{DataVersion:5000, singleplayer_uuid:' + reference + '}}')
    path = tmp_path / 'players/data/00000001-0000-0002-0000-000300000004.dat'
    write_root(from_snbt('{Pos:[1.5d,72d,3.5d],Dimension:"example:moon",UUID:[I;1,2,3,4]}'), path)
    (tmp_path / 'dimensions/example/moon/region').mkdir(parents=True)
    write_root(root, tmp_path / 'level.dat')
    before = {p: p.read_bytes() for p in tmp_path.rglob('*') if p.is_file()}
    world = JavaWorld(tmp_path)
    assert world.start == (1.5, 72, 3.5) and world.start_dimension == 'example:moon'
    players = list(player_entities(world.path, world.data, located=True))
    assert len(players) == 1 and players[0][1].file.startswith('players/data/')
    assert before == {p: p.read_bytes() for p in before}
