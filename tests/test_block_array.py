import pickle

import numpy as np
import pytest

from structura_core.block_array import BlockArray


def test_mapping_edits_and_owned_copies_match_a_dictionary():
    blocks = BlockArray.empty((16, 16, 16))
    expected = {}
    random = np.random.default_rng(2)
    for _ in range(500):
        position = tuple(map(int, random.integers(0, 16, 3)))
        value = int(random.integers(0, 100))
        blocks[position] = value
        expected[position] = value
    assert dict(blocks.items()) == expected and len(blocks) == len(expected)
    copied = pickle.loads(pickle.dumps(blocks.copy(), protocol=5))
    for position in list(expected)[:50]:
        del copied[position]
    assert dict(blocks.items()) == expected and len(copied) == len(expected) - 50
    assert blocks.get((-1, 0, 0)) is None
    with pytest.raises(KeyError):
        blocks[(-1, 0, 0)] = 1


def test_numeric_section_replacement_updates_counts_and_palette_validation():
    blocks = BlockArray.empty((32, 16, 16))
    values = np.full((16, 16, 16), 5, np.int32)
    blocks.set_region((16, 0, 0), values)
    assert blocks.counts() == {5: 4096} and len(blocks) == 4096
    blocks.set_region((16, 0, 0), np.full_like(values, -1))
    assert not blocks
    blocks.validate((32, 16, 16), 6)
    for lower in ((-32, 0, 0), (17, 0, 0), (0, 0)):
        with pytest.raises(ValueError):
            blocks.set_region(lower, values)
