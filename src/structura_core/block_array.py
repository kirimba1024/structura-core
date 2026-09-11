from collections.abc import MutableMapping

import numpy as np


class BlockArray(MutableMapping):
    def __init__(self, array):
        if array.ndim != 3 or array.dtype != np.int32:
            raise ValueError("Block array must be a three-dimensional int32 array")
        self.array = array
        self._count = int(np.count_nonzero(array >= 0))

    @classmethod
    def empty(cls, size):
        return cls(np.full(size, -1, dtype=np.int32))

    def _inside(self, position):
        return (isinstance(position, tuple) and len(position) == 3
                and all(isinstance(p, (int, np.integer)) and 0 <= p < s
                        for p, s in zip(position, self.array.shape)))

    def get(self, position, default=None):
        if not self._inside(position):
            return default
        value = int(self.array[position])
        return default if value < 0 else value

    def __getitem__(self, position):
        value = self.get(position)
        if value is None:
            raise KeyError(position)
        return value

    def __setitem__(self, position, value):
        if not self._inside(position):
            raise KeyError(position)
        if not isinstance(value, (int, np.integer)) or not 0 <= value < 2**31:
            raise ValueError("Block state index must be a nonnegative int32")
        self._count += int(self.array[position] < 0)
        self.array[position] = value

    def __delitem__(self, position):
        self[position]
        self.array[position] = -1
        self._count -= 1

    def __len__(self):
        return self._count

    def __iter__(self):
        sy, sz = self.array.shape[1:]
        for index in np.flatnonzero(self.array.ravel() >= 0):
            x, rest = divmod(int(index), sy * sz)
            y, z = divmod(rest, sz)
            yield x, y, z

    def values(self):
        return map(int, self.array[self.array >= 0])

    def items(self):
        return zip(self, self.values())

    def copy(self):
        return type(self)(self.array.copy())

    def set_region(self, lower, values):
        if (len(lower) != 3 or not all(isinstance(p, (int, np.integer)) and p >= 0 for p in lower)
                or values.ndim != 3 or values.dtype != np.int32 or np.any(values < -1)):
            raise ValueError("Block region requires nonnegative coordinates and int32 state indices")
        region = self.array[tuple(slice(lo, lo + size) for lo, size in zip(lower, values.shape))]
        if region.shape != values.shape:
            raise ValueError("Block region is outside the array")
        self._count += int(np.count_nonzero(values >= 0)) - int(np.count_nonzero(region >= 0))
        region[:] = values

    def counts(self):
        values, counts = np.unique(self.array, return_counts=True)
        return {int(value): int(count) for value, count in zip(values, counts) if value >= 0}

    def validate(self, size, palette_size):
        if self.array.shape != tuple(size) or np.any(self.array < -1) or np.any(self.array >= palette_size):
            raise ValueError("Block array does not match the structure size or palette")
