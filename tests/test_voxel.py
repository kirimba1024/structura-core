import numpy as np

from structura_core.voxel import dilation


def test_dilating_empty_space_does_not_grow_a_corner():
    empty = np.zeros((9, 9), dtype=bool)

    assert not dilation(empty, 4).any()
