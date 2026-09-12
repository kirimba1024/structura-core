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
