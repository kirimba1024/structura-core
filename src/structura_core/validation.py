import math
from numbers import Integral, Real

from amulet_nbt import CompoundTag, ListTag


def int32(value, label):
    value = getattr(value, "py_data", value)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an integer, got {value!r}")
    if not -(2 ** 31) <= value < 2 ** 31:
        raise ValueError(f"{label} must fit a signed 32-bit integer, got {value!r}")
    return int(value)


def vector(values, label, *, integer=True):
    try:
        values = tuple(values)
    except TypeError as error:
        raise ValueError(f"{label} must contain three coordinates") from error
    if len(values) != 3:
        raise ValueError(f"{label} must contain three coordinates, got {values!r}")
    if integer:
        return tuple(int32(value, label) for value in values)
    result = tuple(getattr(value, "py_data", value) for value in values)
    if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in result):
        raise ValueError(f"{label} must contain finite numeric coordinates")
    return tuple(float(value) for value in result)


def compound(value, label):
    if not isinstance(value, CompoundTag):
        raise ValueError(f"{label} must be a compound")
    return value


def compound_list(value, label):
    if not isinstance(value, ListTag) or any(not isinstance(entry, CompoundTag) for entry in value):
        raise ValueError(f"{label} must be a list of compounds")
    return value
