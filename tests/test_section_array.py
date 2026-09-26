from copy import deepcopy
import pickle
import struct
import tracemalloc

import numpy as np
import pytest

from structura_core.block_array import BlockArray
from structura_core.section_array import SectionArray
from structura_core.section_page import SectionPage


@pytest.mark.parametrize('count,states', [(0, 1), (1, 1), (200, 3), (4096, 1), (4096, 17), (4096, 4096)])
def test_section_encoding_preserves_absence_and_all_palette_indices(count, states):
    array = np.full((16, 16, 16), -1, np.int32)
    array.ravel()[:count] = np.arange(count) % states
    page = SectionPage.decode(SectionPage.from_array(array).encode())
    assert page.count == count
    assert len(page.encode()) <= 16 * 1024 + 7
    assert np.array_equal(page.array(), array)
    assert [page.at(i) for i in range(4096)] == array.ravel().tolist()
    owned = page.array()
    owned.fill(123)
    assert np.array_equal(page.array(), array)


@pytest.mark.parametrize('body', [b'', b'SCS1', b'badbody', struct.pack('<4sBH', b'SCS1', 8, 0),
                                   struct.pack('<4sBH', b'SCS1', 1, 4096),
                                   struct.pack('<4sBHH', b'SCS1', 3, 1, 4097),
                                   struct.pack('<4sBHHHi', b'SCS1', 2, 1, 5000, 0, 0)])
def test_corrupt_section_payload_is_rejected(body):
    with pytest.raises(ValueError):
        SectionPage.decode(body)


@pytest.mark.parametrize('dense', [False, True])
def test_section_storage_random_edits_copies_and_regions_match_dense_reference(dense):
    generator = np.random.default_rng(83)
    array = generator.integers(-1, 19, (35, 19, 33), dtype=np.int32)
    source = BlockArray(array.copy()) if dense else dict(BlockArray(array.copy()).items())
    values = SectionArray.from_blocks(source, array.shape)
    copies = []
    for iteration in range(400):
        position = tuple(int(generator.integers(n)) for n in array.shape)
        if iteration % 51 == 0:
            copies.append((deepcopy(values), array.copy()))
        if iteration % 3 and array[position] >= 0:
            del values[position]
            array[position] = -1
        else:
            value = int(generator.integers(20))
            values[position] = value
            array[position] = value
        assert values.get(position) == (int(array[position]) if array[position] >= 0 else None)
    values.validate(array.shape, 20)
    assert dict(values) == dict(BlockArray(array).items())
    assert values.counts() == BlockArray(array).counts()
    assert np.array_equal(values.region((15, 1, 15), (33, 19, 33)), array[15:33, 1:19, 15:33])
    restored = pickle.loads(pickle.dumps(values, protocol=5))
    assert np.array_equal(restored.region((0, 0, 0), array.shape), array)
    for copy, reference in copies:
        assert np.array_equal(copy.region((0, 0, 0), array.shape), reference)


def test_sparse_distant_sections_do_not_allocate_their_bounding_box():
    values = SectionArray.from_blocks({(0, 0, 0): 0, (1_000_000, 8, 7): 1}, (1_000_001, 16, 16))
    assert len(values) == 2 and len(list(values.sections())) == 2
    assert values.region((-1, 0, 0), (2, 1, 1)).ravel().tolist() == [-1, 0, -1]
    del values[(1_000_000, 8, 7)]
    assert len(list(values.sections())) == 1
    values.validate(values.size, 2)


def test_copy_shares_section_index_and_mutation_keeps_other_pages():
    values = SectionArray.from_blocks(BlockArray(np.zeros((128, 64, 128), np.int32)), (128, 64, 128))
    untouched = values._page((7, 3, 7))
    tracemalloc.start()
    try:
        branch = values.copy()
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert branch._pages is values._pages and peak < 8192
    branch[(16, 16, 16)] = 9
    branch.copy()
    assert values[(16, 16, 16)] == 0 and branch[(16, 16, 16)] == 9
    assert branch._page((7, 3, 7)) is untouched


def test_section_validation_rejects_invalid_bounds_and_palette():
    values = SectionArray.from_blocks({(16, 0, 0): 3}, (17, 1, 1))
    with pytest.raises(ValueError, match='palette'):
        values.validate(values.size, 3)
    values.size = (16, 1, 1)
    with pytest.raises(ValueError, match='bounds'):
        values.validate(values.size, 4)


def test_validation_and_counts_follow_immutable_state_and_size(monkeypatch):
    values = SectionArray.from_blocks({(16, 0, 0): 3}, (17, 1, 1))
    values.validate(values.size, 4)
    assert values.counts() == {3: 1}
    branch = values.copy()
    with monkeypatch.context() as patch:
        patch.setattr(SectionArray, 'sections', lambda _: pytest.fail('An unchanged copy scanned all sections'))
        branch.validate(branch.size, 4)
        counts = branch.counts()
        counts.clear()
        assert branch.counts() == {3: 1}
    branch[(0, 0, 0)] = 4
    with pytest.raises(ValueError, match='palette'):
        branch.validate(branch.size, 4)
    assert branch.counts() == {3: 1, 4: 1}
    branch.validate(branch.size, 5)
    del branch[(16, 0, 0)]
    branch.size = (1, 1, 1)
    branch.validate(branch.size, 5)
    assert branch.counts() == {4: 1} and values.counts() == {3: 1}


@pytest.mark.parametrize('position', [(-1, 0, 0), (1, 0, 0), (0, 0), [0, 0, 0], (0.5, 0, 0), ('0', 0, 0)])
def test_invalid_section_coordinates_are_not_truncated(position):
    values = SectionArray.from_blocks({(0, 0, 0): 0}, (1, 1, 1))
    assert values.get(position) is None
    with pytest.raises(KeyError):
        values[position] = 0


@pytest.mark.parametrize('value', [-1, -2, 0.5, 2 ** 31, 2 ** 32, '1'])
def test_section_construction_rejects_indices_before_numeric_conversion(value):
    with pytest.raises(ValueError, match='nonnegative int32'):
        SectionArray.from_blocks({(0, 0, 0): value}, (1, 1, 1))


@pytest.mark.parametrize('kind', ['dense', 'sections'])
def test_section_construction_rejects_size_mismatch(kind):
    source = BlockArray(np.zeros((2, 1, 1), np.int32))
    if kind == 'sections':
        source = SectionArray.from_blocks(source, (2, 1, 1))
    with pytest.raises(ValueError, match='size'):
        SectionArray.from_blocks(source, (1, 1, 1))


def test_region_assignment_crosses_pages_preserves_copies_and_releases_empty_pages():
    source = SectionArray((48, 32, 48))
    values = np.arange(17 * 20 * 17, dtype=np.int32).reshape(17, 20, 17)
    source.set_region((15, 4, 15), values)
    frozen = source.copy()
    assert np.array_equal(source.region((15, 4, 15), (32, 24, 32)), values)
    assert len(source) == values.size
    source.set_region((15, 4, 15), np.full(values.shape, -1, np.int32))
    assert not source and not list(source.addresses())
    assert len(frozen) == values.size
    frozen.validate(frozen.size, values.size)


@pytest.mark.parametrize('lower,array', [((0, 0), np.zeros((1, 1, 1), np.int32)),
    ((0, 0, 0), np.full((17, 1, 1), 2 ** 32, np.int64)),
    ((0, 0, 0), np.full((17, 1, 1), -2, np.int32)),
    ((0, 0, 0), np.full((17, 1, 1), 1.2)), ((20, 0, 0), np.zeros((17, 1, 1), np.int32))])
def test_invalid_region_assignment_is_atomic(lower, array):
    source = SectionArray.from_blocks({(0, 0, 0): 3}, (32, 16, 16))
    with pytest.raises(ValueError):
        source.set_region(lower, array)
    assert dict(source.items()) == {(0, 0, 0): 3}
