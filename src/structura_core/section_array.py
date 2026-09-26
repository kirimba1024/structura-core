from collections import Counter
from collections.abc import MutableMapping
from itertools import product

from immutables import Map
import numpy as np

from .block_array import BlockArray
from .section_page import EMPTY_PAGE, SPAN, SectionPage
from .validation import vector


class SectionArray(MutableMapping):
    def __init__(self, size, *, source=None):
        self.size = tuple(size)
        self._source = source
        self._pages = Map()
        self._pending = {}
        self._count = source.count if source is not None else 0
        self._validation = None
        self._counts = None

    @classmethod
    def from_blocks(cls, blocks, size):
        size = tuple(size)
        if isinstance(blocks, cls):
            if blocks.size != size:
                raise ValueError("Section storage does not match the structure size")
            return blocks.copy()
        result = cls(size)
        if isinstance(blocks, BlockArray):
            if blocks.array.shape != size:
                raise ValueError("Block storage does not match the structure size")
            for address in product(*(range((n + SPAN - 1) // SPAN) for n in size)):
                lower = tuple(p * SPAN for p in address)
                array = np.full((SPAN,) * 3, -1, np.int32)
                view = blocks.array[tuple(slice(lo, lo + SPAN) for lo in lower)]
                array[tuple(slice(0, n) for n in view.shape)] = view
                page = SectionPage.from_array(array)
                if page.count:
                    result._pages = result._pages.set(address, page)
                    result._count += page.count
        else:
            for position, index in blocks.items():
                address, slot = result._address(position)
                result._check_index(index)
                result._pending.setdefault(address, {})[slot] = index
                result._count += 1
            result._seal()
        return result

    def _address(self, position):
        if not isinstance(position, tuple) or len(position) != 3:
            raise KeyError(position)
        x, y, z = position
        sx, sy, sz = self.size
        if (not isinstance(x, (int, np.integer)) or not isinstance(y, (int, np.integer))
                or not isinstance(z, (int, np.integer)) or not (0 <= x < sx and 0 <= y < sy and 0 <= z < sz)):
            raise KeyError(position)
        x, y, z = int(x), int(y), int(z)
        return (x // SPAN, y // SPAN, z // SPAN), (x % SPAN) * SPAN * SPAN + (y % SPAN) * SPAN + z % SPAN

    def _page(self, address):
        page = self._pages.get(address)
        if page is not None:
            return page
        return self._source.page(address) if self._source is not None else EMPTY_PAGE

    def _seal(self):
        for address, changes in self._pending.items():
            array = self._page(address).array()
            array.ravel()[list(changes)] = list(changes.values())
            page = SectionPage.from_array(array)
            if not page.count and self._source is None:
                if address in self._pages:
                    self._pages = self._pages.delete(address)
            else:
                self._pages = self._pages.set(address, page)
        self._pending.clear()

    def get(self, position, default=None):
        try:
            address, slot = self._address(position)
        except KeyError:
            return default
        value = self._value(address, slot)
        return int(value) if value >= 0 else default

    def _value(self, address, slot):
        changes = self._pending.get(address)
        return changes[slot] if changes is not None and slot in changes else self._page(address).at(slot)

    def __getitem__(self, position):
        value = self.get(position)
        if value is None:
            raise KeyError(position)
        return value

    def __setitem__(self, position, value):
        address, slot = self._address(position)
        self._check_index(value)
        self._count += self._value(address, slot) < 0
        self._pending.setdefault(address, {})[slot] = int(value)

    @staticmethod
    def _check_index(value):
        if not isinstance(value, (int, np.integer)) or not 0 <= value < 2 ** 31:
            raise ValueError("Block state index must be a nonnegative int32")

    def __delitem__(self, position):
        address, slot = self._address(position)
        if self._value(address, slot) < 0:
            raise KeyError(position)
        self._pending.setdefault(address, {})[slot] = -1
        self._count -= 1

    def __len__(self):
        return self._count

    def addresses(self):
        self._seal()
        yield from self._pages
        if self._source is not None:
            for address in self._source.addresses():
                if address not in self._pages:
                    yield address

    @property
    def source(self):
        return self._source

    def owned_sections(self):
        self._seal()
        yield from self._pages.items()

    def sections(self):
        self._seal()
        for address, page in self._pages.items():
            if page.count:
                yield address, page
        if self._source is not None:
            for address in self._source.addresses():
                if address not in self._pages:
                    yield address, self._source.page(address)

    def __iter__(self):
        for position, _ in self.items():
            yield position

    def items(self):
        for address, page in self.sections():
            array = page.array()
            for slot in np.flatnonzero(array.ravel() >= 0):
                x, rest = divmod(int(slot), SPAN ** 2)
                y, z = divmod(rest, SPAN)
                yield tuple(p * SPAN + local for p, local in zip(address, (x, y, z))), int(array[x, y, z])

    def values(self):
        for _, page in self.sections():
            array = page.array()
            yield from map(int, array[array >= 0])

    def copy(self):
        self._seal()
        result = type(self)(self.size, source=self._source)
        result._pages, result._count = self._pages, self._count
        result._validation, result._counts = self._validation, self._counts
        return result

    def __deepcopy__(self, memo):
        result = self.copy()
        memo[id(self)] = result
        return result

    def region(self, lower, upper):
        self._seal()
        size = tuple(hi - lo for lo, hi in zip(lower, upper))
        array = np.full(size, -1, np.int32)
        start = tuple(max(0, lo) for lo in lower)
        stop = tuple(min(n, hi) for n, hi in zip(self.size, upper))
        if any(lo >= hi for lo, hi in zip(start, stop)):
            return array
        for address in product(*(range(lo // SPAN, (hi - 1) // SPAN + 1) for lo, hi in zip(start, stop))):
            origin = tuple(p * SPAN for p in address)
            lo = tuple(max(p, bound) for p, bound in zip(origin, start))
            hi = tuple(min(p + SPAN, bound) for p, bound in zip(origin, stop))
            page = self._page(address)
            target = tuple(slice(p - base, q - base) for p, q, base in zip(lo, hi, lower))
            source = tuple(slice(p - base, q - base) for p, q, base in zip(lo, hi, origin))
            if page.kind == 'uniform':
                array[target] = page.at(0)
            elif page.count:
                array[target] = page.array()[source]
        return array

    def set_region(self, lower, array):
        lower = vector(lower, 'region origin')
        array = np.asarray(array)
        upper = tuple(lo + n for lo, n in zip(lower, array.shape))
        if array.ndim != 3 or any(lo < 0 or hi > n for lo, hi, n in zip(lower, upper, self.size)):
            raise ValueError('Region is outside section storage')
        if array.dtype.kind not in 'iu' or np.any(array < -1) or np.any(array >= 2 ** 31):
            raise ValueError('Region block indices must be int32 values or -1')
        if not array.size:
            return
        self._seal()
        for address in product(*(range(lo // SPAN, (hi + SPAN - 1) // SPAN) for lo, hi in zip(lower, upper))):
            origin = tuple(p * SPAN for p in address)
            start = tuple(max(p, lo) for p, lo in zip(origin, lower))
            stop = tuple(min(p + SPAN, hi) for p, hi in zip(origin, upper))
            previous = self._page(address)
            page = previous.array()
            target = tuple(slice(lo - p, hi - p) for lo, hi, p in zip(start, stop, origin))
            source = tuple(slice(lo - p, hi - p) for lo, hi, p in zip(start, stop, lower))
            page[target] = array[source]
            updated = SectionPage.from_array(page)
            if not updated.count and self._source is None:
                if address in self._pages:
                    self._pages = self._pages.delete(address)
            else:
                self._pages = self._pages.set(address, updated)
            self._count += updated.count - previous.count

    def counts(self):
        self._seal()
        if self._counts is not None and self._counts[0] is self._pages:
            return self._counts[1].copy()
        result = Counter()
        for _, page in self.sections():
            if page.kind == 'uniform':
                result[page.at(0)] += page.count
                continue
            values, counts = np.unique(page.array(), return_counts=True)
            result.update({int(value): int(count) for value, count in zip(values, counts) if value >= 0})
        self._counts = self._pages, dict(result)
        return self._counts[1].copy()

    def validate(self, size, palette_size):
        if tuple(size) != self.size:
            raise ValueError("Section storage does not match the structure size")
        self._seal()
        if (self._validation is not None and self._validation[0] is self._pages
                and self._validation[1:] == (self.size, self._count, palette_size)):
            return
        count = 0
        for address, page in self.sections():
            array = page.array()
            count += page.count
            if np.any(array >= palette_size):
                raise ValueError("Section palette index is outside the structure palette")
            for axis, (p, n) in enumerate(zip(address, self.size)):
                valid = max(0, min(SPAN, n - p * SPAN))
                outside = [slice(None)] * 3
                outside[axis] = slice(valid, None)
                if p < 0 or np.any(array[tuple(outside)] >= 0):
                    raise ValueError("Section contains blocks outside the structure bounds")
        if count != self._count:
            raise ValueError("Section storage count does not match its contents")
        self._validation = self._pages, self.size, self._count, palette_size
