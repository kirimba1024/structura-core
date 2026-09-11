from dataclasses import dataclass
from numbers import Integral


IDENTITY = ((1, 0, 0), (0, 1, 0), (0, 0, 1))
DIRECTIONS = {"east": (1, 0, 0), "west": (-1, 0, 0), "up": (0, 1, 0),
              "down": (0, -1, 0), "south": (0, 0, 1), "north": (0, 0, -1)}
QUARTERS = {"x": ((1, 0, 0), (0, 0, 1), (0, -1, 0)),
            "y": ((0, 0, -1), (0, 1, 0), (1, 0, 0)),
            "z": ((0, 1, 0), (-1, 0, 0), (0, 0, 1))}


@dataclass(frozen=True)
class GridTransform:
    matrix: tuple = IDENTITY

    def __post_init__(self):
        rows = self.matrix
        if (not isinstance(rows, tuple) or len(rows) != 3
                or any(not isinstance(row, tuple) or len(row) != 3 for row in rows)
                or any(type(v) is not int or v not in (-1, 0, 1) for row in rows for v in row)
                or any(sum(abs(v) for v in row) != 1 for row in rows)
                or any(sum(abs(rows[i][j]) for i in range(3)) != 1 for j in range(3))):
            raise ValueError("Transform must be an orthogonal signed permutation")

    @classmethod
    def operation(cls, *, turns=0, axis="y", flip=None):
        if isinstance(turns, bool) or not isinstance(turns, Integral) or axis not in QUARTERS or flip not in (None, "x", "y", "z"):
            raise ValueError("Use integer quarter turns and X, Y or Z axes")
        result = cls()
        if flip is not None:
            selected = "xyz".index(flip)
            result = cls(tuple(tuple(-v if i == selected else v for v in row) for i, row in enumerate(IDENTITY)))
        quarter = cls(QUARTERS[axis])
        for _ in range(turns % 4):
            result = quarter.compose(result)
        return result

    def compose(self, previous):
        return GridTransform(tuple(tuple(sum(self.matrix[i][k] * previous.matrix[k][j] for k in range(3))
                                         for j in range(3)) for i in range(3)))

    def inverse(self):
        return GridTransform(tuple(zip(*self.matrix)))

    def vector(self, vector):
        return tuple(sum(sign * value for sign, value in zip(row, vector)) for row in self.matrix)

    def size(self, size):
        return tuple(sum(abs(sign) * value for sign, value in zip(row, size)) for row in self.matrix)

    def point(self, position, size, *, cell=False):
        limits = tuple(v - 1 if cell else v for v in size)
        return tuple(value + sum(limit for sign, limit in zip(row, limits) if sign < 0)
                     for value, row in zip(self.vector(position), self.matrix))

    def direction(self, name):
        vector = self.vector(DIRECTIONS[name])
        return next(key for key, value in DIRECTIONS.items() if value == vector)

    def horizontal(self):
        if self.direction("up") != "up":
            return None
        for flip in (None, "x"):
            for turns in range(4):
                if self == self.operation(turns=turns, flip=flip):
                    return turns, flip
        return None
