import struct

import pytest

from structura_core.world_terrain import existing_chunks


def header(path, indices):
    data = bytearray(8192)
    for index in indices:
        struct.pack_into(">I", data, index * 4, (2 << 8) | 1)
    path.write_bytes(data)


def test_bounded_index_only_reads_requested_regions(tmp_path):
    header(tmp_path / "r.-1.0.mca", (31, 1023))
    header(tmp_path / "r.0.0.mca", (0, 33))
    (tmp_path / "r.900.900.mca").write_bytes(b"unrelated region")
    assert existing_chunks(tmp_path, regions={(-1, 0), (0, 0), (1, 0)}) == ((-1, 0), (-1, 31), (0, 0), (1, 1))
    assert existing_chunks(tmp_path, regions=()) == ()
    with pytest.raises(ValueError, match="Truncated region header"):
        existing_chunks(tmp_path)


def test_bounded_index_validates_selected_headers(tmp_path):
    (tmp_path / "r.0.0.mca").write_bytes(b"invalid")
    with pytest.raises(ValueError, match="Truncated region header"):
        existing_chunks(tmp_path, regions=((0, 0),))
    with pytest.raises(ValueError):
        existing_chunks(tmp_path, regions=(("../secret", 0),))


@pytest.mark.parametrize('location', [1, 257, 511, 512])
@pytest.mark.parametrize('index', [0, 511, 1023])
def test_index_rejects_invalid_locations_anywhere_in_the_header(tmp_path, location, index):
    path = tmp_path / 'r.-2.3.mca'
    header(path, (0, 511, 1023))
    data = bytearray(path.read_bytes())
    struct.pack_into('>I', data, index * 4, location)
    path.write_bytes(data)
    with pytest.raises(ValueError, match='Invalid chunk location'):
        existing_chunks(tmp_path)


def test_chunk_iterator_reads_one_region_at_a_time(tmp_path):
    from structura_core.world_terrain import iter_chunks

    header(tmp_path / 'r.0.0.mca', (0, 33))
    (tmp_path / 'r.1.0.mca').write_bytes(b'bad later region')
    chunks = iter_chunks(tmp_path)
    assert next(chunks) == (0, 0)
    assert next(chunks) == (1, 1)
    with pytest.raises(ValueError, match='Truncated region header'):
        next(chunks)
