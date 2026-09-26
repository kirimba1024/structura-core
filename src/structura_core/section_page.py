from dataclasses import dataclass
from struct import error as StructError, pack, unpack_from

import numpy as np


SPAN = 16
CELLS = SPAN ** 3


@dataclass(frozen=True)
class SectionPage:
    kind: str
    data: bytes
    count: int

    @classmethod
    def from_array(cls, values):
        array = np.asarray(values)
        if array.shape != (SPAN, SPAN, SPAN) or not np.issubdtype(array.dtype, np.integer):
            raise ValueError("A section requires a 16×16×16 integer array")
        if np.any(array < -1) or np.any(array >= 2 ** 31):
            raise ValueError("Section indices must be -1 or nonnegative int32")
        flat = array.astype('<i4', copy=False).ravel()
        occupied = np.flatnonzero(flat >= 0)
        count = len(occupied)
        if not count:
            return cls('empty', b'', 0)
        palette, indices = np.unique(flat, return_inverse=True)
        if len(palette) == 1:
            return cls('uniform', pack('<i', int(palette[0])), CELLS)
        candidates = [('dense', flat.tobytes())]
        candidates.append(('sparse', occupied.astype('<u2').tobytes() + flat[occupied].tobytes()))
        width = 1 if len(palette) <= 256 else 2
        candidates.append(('paletted', pack('<H', len(palette)) + palette.astype('<i4', copy=False).tobytes()
                           + indices.astype('u1' if width == 1 else '<u2').tobytes()))
        kind, data = min(candidates, key=lambda item: len(item[1]))
        return cls(kind, data, count)

    def array(self):
        if self.kind == 'empty':
            flat = np.full(CELLS, -1, dtype=np.int32)
        elif self.kind == 'uniform':
            flat = np.full(CELLS, unpack_from('<i', self.data)[0], dtype=np.int32)
        elif self.kind == 'dense':
            flat = np.frombuffer(self.data, dtype='<i4').copy()
        elif self.kind == 'sparse':
            flat = np.full(CELLS, -1, dtype=np.int32)
            indices = np.frombuffer(self.data, dtype='<u2', count=self.count)
            flat[indices] = np.frombuffer(self.data, dtype='<i4', offset=2 * self.count)
        elif self.kind == 'paletted':
            length = unpack_from('<H', self.data)[0]
            palette = np.frombuffer(self.data, dtype='<i4', count=length, offset=2)
            indices = np.frombuffer(self.data, dtype='u1' if length <= 256 else '<u2', offset=2 + length * 4)
            flat = palette[indices]
        else:
            raise ValueError("Unsupported section representation")
        return flat.reshape(SPAN, SPAN, SPAN)

    def at(self, index):
        if self.kind == 'empty':
            return -1
        if self.kind == 'uniform':
            return unpack_from('<i', self.data)[0]
        if self.kind == 'dense':
            return unpack_from('<i', self.data, index * 4)[0]
        if self.kind == 'paletted':
            length = unpack_from('<H', self.data)[0]
            offset = 2 + length * 4
            slot = self.data[offset + index] if length <= 256 else unpack_from('<H', self.data, offset + index * 2)[0]
            return unpack_from('<i', self.data, 2 + slot * 4)[0]
        indices = np.frombuffer(self.data, dtype='<u2', count=self.count)
        slot = int(np.searchsorted(indices, index))
        return unpack_from('<i', self.data, 2 * self.count + slot * 4)[0] if slot < self.count and indices[slot] == index else -1

    def encode(self):
        kinds = ('empty', 'uniform', 'sparse', 'paletted', 'dense')
        return pack('<4sBH', b'SCS1', kinds.index(self.kind), self.count) + self.data

    @classmethod
    def decode(cls, body):
        if not isinstance(body, bytes) or not 7 <= len(body) <= 7 + CELLS * 4:
            raise ValueError("Invalid section payload size")
        magic, kind, count = unpack_from('<4sBH', body)
        if magic != b'SCS1' or kind > 4 or count > CELLS:
            raise ValueError("Invalid section header")
        page = cls(('empty', 'uniform', 'sparse', 'paletted', 'dense')[kind], body[7:], count)
        try:
            data = page.data
            expected = {'empty': 0, 'uniform': 4, 'sparse': 6 * count, 'dense': 4 * CELLS}.get(page.kind)
            if page.kind == 'paletted':
                length = unpack_from('<H', data)[0]
                if not 2 <= length <= CELLS:
                    raise ValueError("Invalid section palette")
                expected = 2 + 4 * length + CELLS * (1 if length <= 256 else 2)
            if len(data) != expected:
                raise ValueError("Invalid section body size")
            if page.kind == 'sparse':
                indices = np.frombuffer(data, dtype='<u2', count=count)
                if count and (indices[-1] >= CELLS or np.any(indices[1:] <= indices[:-1])):
                    raise ValueError("Invalid sparse section positions")
            array = page.array()
            if np.any(array < -1) or int(np.count_nonzero(array >= 0)) != count:
                raise ValueError("Invalid section contents")
        except (IndexError, TypeError, ValueError, OverflowError, StructError) as error:
            raise ValueError("Invalid section payload") from error
        return page


EMPTY_PAGE = SectionPage('empty', b'', 0)
