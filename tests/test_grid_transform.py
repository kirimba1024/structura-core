from itertools import permutations, product

import pytest
from amulet_nbt import from_snbt

from structura_core.block_transform import transform_state
from structura_core.entity_grid_transform import transform_entity
from structura_core.grid_transform import DIRECTIONS, GridTransform


@pytest.mark.parametrize("axis", "xyz")
def test_quarter_turns_have_exact_inverse_and_four_turn_cycle(axis):
    size = (2, 3, 5)
    positions = tuple(product(*(range(v) for v in size)))
    quarter = GridTransform.operation(turns=1, axis=axis)
    transformed = tuple(quarter.point(p, size, cell=True) for p in positions)
    assert len(set(transformed)) == len(positions)
    assert all(all(0 <= v < limit for v, limit in zip(p, quarter.size(size))) for p in transformed)
    assert tuple(quarter.inverse().point(p, quarter.size(size), cell=True) for p in transformed) == positions
    state = GridTransform()
    for _ in range(4):
        state = quarter.compose(state)
    assert state == GridTransform()
    assert quarter.compose(GridTransform.operation(turns=-1, axis=axis)) == GridTransform()
    mirror = GridTransform.operation(flip=axis)
    assert mirror.compose(mirror) == GridTransform()


def test_known_rotations_and_mirrors_have_expected_coordinates():
    size, position = (2, 3, 5), (1, 0, 2)
    assert GridTransform.operation(turns=1, axis="x").point(position, size, cell=True) == (1, 2, 2)
    assert GridTransform.operation(turns=1, axis="y").point(position, size, cell=True) == (2, 0, 1)
    assert GridTransform.operation(turns=1, axis="z").point(position, size, cell=True) == (0, 0, 2)
    assert GridTransform.operation(flip="y").point(position, size, cell=True) == (1, 2, 2)


def test_all_48_orientations_preserve_cells_directions_and_composition():
    size, position = (2, 3, 5), (0, 1, 4)
    transforms = [GridTransform(tuple(tuple(signs[i] if j == order[i] else 0 for j in range(3)) for i in range(3)))
                  for order in permutations(range(3)) for signs in product((-1, 1), repeat=3)]
    assert len(set(transforms)) == 48
    for first in transforms:
        assert first.inverse().point(first.point(position, size, cell=True), first.size(size), cell=True) == position
        assert {first.direction(name) for name in DIRECTIONS} == set(DIRECTIONS)
        for second in transforms:
            combined = second.compose(first)
            assert combined.point(position, size, cell=True) == second.point(first.point(position, size, cell=True), first.size(size), cell=True)
            assert combined.size(size) == second.size(first.size(size))


@pytest.mark.parametrize("operation", [{"turns": 0.5}, {"turns": True}, {"axis": "w"}, {"flip": "w"}])
def test_invalid_operations_are_rejected(operation):
    with pytest.raises(ValueError):
        GridTransform.operation(**operation)


@pytest.mark.parametrize("axis", "xyz")
def test_oriented_blocks_survive_cycles_without_a_clipboard_snapshot(axis):
    defaults = {"axis": "y"}
    allowed = {"axis": ("x", "y", "z")}
    state = original = "minecraft:oak_log[axis=x]"
    for _ in range(4):
        state = transform_state(state, GridTransform.operation(turns=1, axis=axis), defaults=defaults, allowed=allowed)
    assert state == original
    state = original = "minecraft:observer[facing=north]"
    for _ in range(4):
        state = transform_state(state, GridTransform.operation(turns=1, axis=axis),
                                defaults={"facing": "south"}, allowed={"facing": tuple(DIRECTIONS)})
    assert state == original


def test_unrepresentable_block_orientation_fails_before_mutation():
    state = "minecraft:chest[facing=north]"
    with pytest.raises(ValueError, match="Cannot tilt"):
        transform_state(state, GridTransform.operation(turns=1, axis="x"),
                        allowed={"facing": ("north", "south", "west", "east")})


@pytest.mark.parametrize("axis", "xyz")
def test_entity_coordinates_motion_and_unknown_nbt_survive_inverse(axis):
    original = from_snbt('''{pos:[0.25d,1.5d,2.75d],blockPos:[0,1,2],nbt:{id:"mod:entity",UUID:[I;1,2,3,4],
        Motion:[0.125d,-0.5d,0.25d],custom:{value:9L},Passengers:[{id:"mod:rider",Pos:[0.25d,2d,2.75d]}]}}''')
    size = (2, 3, 5)
    operation = GridTransform.operation(turns=1, axis=axis)
    transformed = transform_entity(original, size, operation)
    assert tuple(float(v) for v in transformed["pos"]) == operation.point((0.25, 1.5, 2.75), size)
    assert transformed["nbt"]["custom"] == original["nbt"]["custom"]
    assert transformed["nbt"]["UUID"] == original["nbt"]["UUID"]
    assert transform_entity(transformed, operation.size(size), operation.inverse()) == original
