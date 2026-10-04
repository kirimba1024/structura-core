import re

from amulet_nbt import (
    ByteArrayTag, ByteTag, CompoundTag, DoubleTag, FloatTag, IntArrayTag,
    IntTag, ListTag, LongArrayTag, LongTag, ShortTag, StringTag,
)

_SPACE = re.compile(r"\s*")
_WORD = re.compile(r"[A-Za-z0-9_.+\-]+")
_QUOTED = {
    '"': re.compile(r'"((?:\\.|[^"\\])*)"'),
    "'": re.compile(r"'((?:\\.|[^'\\])*)'"),
}
_INTEGER = re.compile(r"[+-]?\d+")
_DECIMAL = re.compile(r"[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?")
_FLOAT = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?")
_NUMBERS = {"b": ByteTag, "s": ShortTag, "l": LongTag, "f": FloatTag, "d": DoubleTag}
_ARRAYS = {"B": (ByteTag, ByteArrayTag), "I": (IntTag, IntArrayTag), "L": (LongTag, LongArrayTag)}


class _Reader:
    def __init__(self, text):
        self.text = text
        self.index = 0

    def peek(self):
        self.index = _SPACE.match(self.text, self.index).end()
        return self.text[self.index] if self.index < len(self.text) else ""

    def require(self, character):
        if self.peek() != character:
            raise ValueError(f"expected {character!r} at position {self.index}")
        self.index += 1

    def word(self):
        character = self.peek()
        if character in _QUOTED:
            match = _QUOTED[character].match(self.text, self.index)
            if match is None:
                raise ValueError(f"unterminated string at position {self.index}")
            self.index = match.end()
            return re.sub(r"\\([\\" + character + r"])", r"\1", match.group(1)), True
        match = _WORD.match(self.text, self.index)
        if match is None:
            raise ValueError(f"expected a value at position {self.index}")
        self.index = match.end()
        return match.group(), False

    def value(self, depth=0):
        if depth >= 512:
            raise ValueError("SNBT nesting exceeds 512 levels")
        character = self.peek()
        if character == "{":
            return self.compound(depth + 1)
        if character == "[":
            return self.sequence(depth + 1)
        word, quoted = self.word()
        if not quoted:
            lower = word.lower()
            if lower in ("true", "false"):
                return ByteTag(lower == "true")
            suffix = lower[-1]
            if suffix in _NUMBERS:
                value = word[:-1]
                numeric = _FLOAT if suffix in "fd" else _INTEGER
                if numeric.fullmatch(value):
                    return _NUMBERS[suffix](float(value) if suffix in "fd" else int(value))
            if _INTEGER.fullmatch(word):
                return IntTag(int(word))
            if _DECIMAL.fullmatch(word):
                return DoubleTag(float(word))
        return StringTag(word)

    def compound(self, depth):
        self.require("{")
        result = CompoundTag()
        while self.peek() != "}":
            key, _ = self.word()
            self.require(":")
            result[key] = self.value(depth)
            if self.peek() != ",":
                break
            self.index += 1
        self.require("}")
        return result

    def sequence(self, depth):
        self.require("[")
        typed = None
        if self.peek() in _ARRAYS and self.index + 1 < len(self.text) and self.text[self.index + 1] == ";":
            typed = _ARRAYS[self.text[self.index]]
            self.index += 2
        values = []
        while self.peek() != "]":
            value = self.value(depth)
            if typed is not None and type(value) is not typed[0]:
                raise ValueError(f"wrong array value type at position {self.index}")
            if typed is None and values and type(value) is not type(values[0]):
                raise ValueError(f"mixed list value types at position {self.index}")
            values.append(value)
            if self.peek() != ",":
                break
            self.index += 1
        self.require("]")
        return typed[1]([int(value) for value in values]) if typed else ListTag(values)


def load_snbt(text):
    reader = _Reader(text)
    result = reader.value()
    if reader.peek():
        raise ValueError(f"trailing data at position {reader.index}")
    return result
