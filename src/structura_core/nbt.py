import gzip
import math
import os
import re
import tempfile
import zlib
from collections.abc import Iterable, Mapping
from copy import deepcopy
from io import BytesIO
from numbers import Integral, Real
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple, Union
from os import PathLike

from .limits import DEFAULT_MAX_NBT_BYTES

from amulet_nbt import (
    CompoundTag,
    DoubleTag,
    IntTag,
    ListTag,
    NamedTag,
    NBTLoadError,
    SNBTParseError,
    StringTag,
    from_snbt,
    utf8_escape_decoder,
    utf8_escape_encoder,
)
from amulet_nbt import (
    load as load_nbt,
)

PathInput = Union[str, PathLike[str]]

AIR_NAMES = frozenset({"minecraft:air", "minecraft:cave_air", "minecraft:void_air"})
Position = Tuple[int, int, int]
State = Union[int, str]
_RESOURCE_LOCATION = re.compile(r"[a-z0-9_.-]+:[a-z0-9_./-]+\Z")


def _integer(value, label):
    value = getattr(value, "py_data", value)
    if isinstance(value, bool) or not isinstance(value, Integral):
        raise ValueError(f"{label} must be an integer, got {value!r}")
    if not -(2 ** 31) <= value < 2 ** 31:
        raise ValueError(f"{label} must fit a signed 32-bit integer, got {value!r}")
    return int(value)


def _vector(values, label, *, integer=True):
    try:
        values = tuple(values)
    except TypeError as error:
        raise ValueError(f"{label} must contain three coordinates") from error
    if len(values) != 3:
        raise ValueError(f"{label} must contain three coordinates, got {values!r}")
    if integer:
        return tuple(_integer(value, label) for value in values)
    result = tuple(getattr(value, "py_data", value) for value in values)
    if any(isinstance(v, bool) or not isinstance(v, Real) or not math.isfinite(v) for v in result):
        raise ValueError(f"{label} must contain finite numeric coordinates")
    return tuple(float(value) for value in result)


def _check_byte_limit(limit):
    if isinstance(limit, bool) or not isinstance(limit, int) or limit <= 0:
        raise ValueError("max_nbt_bytes must be a positive integer")


def _bounded_read(stream, limit):
    data = stream.read(limit + 1)
    if len(data) > limit:
        raise ValueError(f"NBT data exceeds max_nbt_bytes={limit:,}")
    return data


def read_root(data: bytes, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
              little_endian: bool = False) -> CompoundTag:
    _check_byte_limit(max_nbt_bytes)
    if len(data) > max_nbt_bytes:
        raise ValueError(f"NBT input exceeds max_nbt_bytes={max_nbt_bytes:,}")
    if data.startswith(b"\x1f\x8b"):
        try:
            with gzip.GzipFile(fileobj=BytesIO(data)) as stream:
                data = _bounded_read(stream, max_nbt_bytes)
        except (gzip.BadGzipFile, EOFError, zlib.error) as error:
            raise ValueError("invalid gzip-compressed NBT") from error
    try:
        options = {"string_decoder": utf8_escape_decoder} if little_endian else {}
        return load_nbt(data, compressed=False, little_endian=little_endian, **options).compound
    except (NBTLoadError, EOFError, TypeError) as error:
        raise ValueError(f"invalid NBT: {error}") from error


def load_root(path: PathInput, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
              little_endian: bool = False) -> CompoundTag:
    _check_byte_limit(max_nbt_bytes)
    with Path(path).open("rb") as stream:
        data = _bounded_read(stream, max_nbt_bytes)
    if Path(path).suffix.lower() == ".snbt":
        try:
            text = data.decode("utf-8").strip()
            root = from_snbt(text)
        except (SNBTParseError, UnicodeError, RecursionError) as error:
            raise ValueError(f"invalid SNBT: {error}") from error
        if not isinstance(root, CompoundTag):
            raise ValueError("SNBT root must be a compound")
        _check_snbt_end(text)
        return root
    return read_root(data, max_nbt_bytes=max_nbt_bytes, little_endian=little_endian)


def _check_snbt_end(text):
    depth, quote, escaped = 0, None, False
    for index, character in enumerate(text):
        if quote is not None:
            if escaped:
                escaped = False
            elif character == "\\":
                escaped = True
            elif character == quote:
                quote = None
        elif character in "\"'":
            quote = character
        elif character == "{":
            depth += 1
        elif character == "}":
            depth -= 1
            if depth == 0 and index != len(text) - 1:
                raise ValueError("invalid SNBT: trailing data after root compound")


def write_root(root: CompoundTag, path: PathInput, compressed: bool = True, *, name: str = "",
               little_endian: bool = False) -> None:
    """Atomically write NBT, with reproducible gzip bytes when compressed."""
    if Path(path).suffix.lower() == ".snbt":
        data = (root.to_snbt(indent=2) + "\n").encode("utf-8")
    else:
        options = {"string_encoder": utf8_escape_encoder} if little_endian else {}
        data = NamedTag(root, name).save_to(compressed=False, little_endian=little_endian, **options)
    if compressed and Path(path).suffix.lower() != ".snbt":
        output = BytesIO()
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as stream:
            stream.write(data)
        data = output.getvalue()
    atomic_write(path, data)


def atomic_write(path: PathInput, data: bytes) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, prefix=f".{destination.name}.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(data)
        os.replace(temporary, destination)
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def state_key(entry: Mapping) -> str:
    """Return a stable ``namespace:block[prop=value,...]`` palette key."""
    name = str(entry["Name"])
    properties = entry.get("Properties")
    if not properties:
        return name
    values = ",".join(f"{key}={value}" for key, value in sorted(properties.items()))
    return f"{name}[{values}]"


def parse_state(value: str) -> CompoundTag:
    """Parse the compact state syntax accepted by generation helpers."""
    if not isinstance(value, str):
        raise ValueError(f"block state must be a string, got {value!r}")
    name, properties = value, None
    if "[" in value:
        if not value.endswith("]"):
            raise ValueError(f"invalid block state: {value!r}")
        name, raw = value[:-1].split("[", 1)
        parsed = {}
        for pair in raw.split(","):
            if not pair or "=" not in pair:
                raise ValueError(f"invalid block state property: {value!r}")
            key, item = pair.split("=", 1)
            if (not key or not item or key in parsed
                    or any(c in key + item for c in "[]=, \t\r\n")):
                raise ValueError(f"invalid block state property: {value!r}")
            parsed[key] = StringTag(item)
        properties = CompoundTag(parsed)
    if not _RESOURCE_LOCATION.fullmatch(name):
        raise ValueError(f"block state needs a valid namespace and name: {value!r}")
    entry = CompoundTag({"Name": StringTag(name)})
    if properties:
        entry["Properties"] = properties
    return entry


def _validate_palette(palette, label):
    for entry in palette:
        if not isinstance(entry, CompoundTag) or not isinstance(entry.get("Name"), StringTag):
            raise ValueError(f"invalid palette entry in {label}")
        properties = entry.get("Properties")
        if properties is not None and (not isinstance(properties, CompoundTag)
                or any(not isinstance(v, StringTag) for v in properties.values())):
            raise ValueError(f"invalid palette properties in {label}")
        parse_state(state_key(entry))


class Structure:
    """In-memory Structure NBT with eagerly checked structural invariants."""

    path: Path
    data_version: int
    size: Position
    palette_index: int
    palette: List[str]
    palettes_raw: List[List[CompoundTag]]
    present: Dict[Position, int]
    block_nbt: Dict[Position, CompoundTag]
    entities: List[CompoundTag]

    def __init__(self, path: PathInput, palette_index: int = 0, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> None:
        self.path = Path(path)
        self._read(load_root(self.path, max_nbt_bytes=max_nbt_bytes), palette_index)

    @classmethod
    def from_root(cls, root: CompoundTag, palette_index: int = 0) -> "Structure":
        """Read an owned copy of a Structure NBT compound without a temporary file."""
        result = cls.__new__(cls)
        result.path = Path("<memory>")
        result._read(deepcopy(root), palette_index)
        return result

    @classmethod
    def from_bytes(cls, data: bytes, palette_index: int = 0, *, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> "Structure":
        """Read raw or gzip-compressed NBT bytes."""
        result = cls.__new__(cls)
        result.path = Path("<memory>")
        result._read(read_root(data, max_nbt_bytes=max_nbt_bytes), palette_index)
        return result

    def _read(self, root, palette_index):
        if not isinstance(root, CompoundTag):
            raise ValueError("structure root must be an NBT compound")
        self._root = root
        palette_index = _integer(palette_index, "palette index")
        try:
            self.data_version = _integer(root["DataVersion"], "DataVersion")
            self.size = _vector(root["size"], "structure size")
            blocks = root["blocks"]
        except (AttributeError, KeyError, TypeError, ValueError) as error:
            raise ValueError(f"invalid structure header in {self.path}") from error
        palettes = root.get("palettes")
        if not isinstance(blocks, ListTag):
            raise ValueError(f"invalid blocks list in {self.path}")
        if palettes is None:
            if palette_index != 0 or "palette" not in root:
                raise ValueError(
                    f"palette {palette_index} is unavailable in {self.path}"
                )
            palettes = [root["palette"]]
        else:
            if not isinstance(palettes, ListTag):
                raise ValueError(f"invalid palettes in {self.path}")
            if not 0 <= palette_index < len(palettes):
                raise ValueError(
                    f"palette {palette_index} is unavailable in {self.path}"
                )
        self.palette_index = palette_index
        if any(not isinstance(palette, ListTag) for palette in palettes):
            raise ValueError(f"invalid palettes in {self.path}")
        self.palettes_raw = [list(palette) for palette in palettes]
        self.palette_raw = self.palettes_raw[palette_index]
        entities = root.get("entities", ListTag())
        if not isinstance(entities, ListTag):
            raise ValueError(f"invalid entities list in {self.path}")
        self.entities = list(entities)
        self.present = {}
        self.block_nbt = {}
        self._block_records = {}
        for block in blocks:
            if not isinstance(block, CompoundTag) or not {"pos", "state"} <= block.keys():
                raise ValueError(f"invalid block record in {self.path}")
            pos = _vector(block["pos"], "block position")
            if pos in self.present:
                raise ValueError(f"duplicate block position {pos} in {self.path}")
            self.present[pos] = _integer(block["state"], "block state index")
            self._block_records[pos] = block
            if "nbt" in block:
                self.block_nbt[pos] = block["nbt"]
        self.validate()

    @property
    def palette_raw(self) -> List[CompoundTag]:
        return self.palettes_raw[self.palette_index]

    @palette_raw.setter
    def palette_raw(self, value: List[CompoundTag]) -> None:
        self.palettes_raw[self.palette_index] = value

    def validate(self) -> None:
        index = _integer(self.palette_index, "palette index")
        if not 0 <= index < len(self.palettes_raw):
            raise ValueError(f"palette {index} is unavailable in {self.path}")
        _integer(self.data_version, "DataVersion")
        if any(value <= 0 for value in _vector(self.size, "structure size")):
            raise ValueError(f"invalid structure size {self.size} in {self.path}")
        for palette in self.palettes_raw:
            if len(palette) != len(self.palette_raw):
                raise ValueError(f"palettes must have equal lengths in {self.path}")
            _validate_palette(palette, str(self.path))
        self.palette = [str(entry["Name"]) for entry in self.palette_raw]
        for pos, index in self.present.items():
            _vector(pos, "block position")
            _integer(index, "block state index")
            if len(pos) != 3 or not all(
                0 <= value < limit for value, limit in zip(pos, self.size)
            ):
                raise ValueError(f"block {pos} is outside {self.size} in {self.path}")
            if not 0 <= index < len(self.palette):
                raise ValueError(f"palette index {index} is invalid in {self.path}")
        dangling = self.block_nbt.keys() - self.present.keys()
        if dangling:
            raise ValueError(
                f"block entities without blocks in {self.path}: {sorted(dangling)[:3]}"
            )
        if any(not isinstance(value, CompoundTag) for value in self.block_nbt.values()):
            raise ValueError(f"invalid block entity NBT in {self.path}")
        for entity in self.entities:
            if not isinstance(entity, CompoundTag) or not isinstance(entity.get("nbt"), CompoundTag):
                raise ValueError(f"invalid entity record in {self.path}")
            try:
                _vector(entity["pos"], "entity position", integer=False)
                _vector(entity["blockPos"], "entity block position")
            except KeyError as error:
                raise ValueError(f"missing entity position in {self.path}") from error

    def name_at(self, pos: Position) -> Optional[str]:
        index = self.present.get(pos)
        return None if index is None else self.palette[index]

    def is_air(self, pos: Position) -> bool:
        return self.name_at(pos) in AIR_NAMES

    def solid_positions(self) -> Set[Position]:
        return {
            pos
            for pos, index in self.present.items()
            if self.palette[index] not in AIR_NAMES
        }


def save_structure(
    src: Structure,
    dst: PathInput,
    size: Position,
    shift: Position = (0, 0, 0),
    additions: Iterable[Tuple[Position, State]] = (),
    replacements: Iterable[Tuple[Position, State]] = (),
) -> None:
    """Save without discarding palettes or metadata.

    Additions preserve every authored cell, including air. String states are
    literal in all palettes; integer states select the corresponding variant
    in each palette. Replacements explicitly replace a cell and its block NBT.
    """
    size = _vector(size, "output size")
    shift = _vector(shift, "shift")
    if any(value <= 0 for value in size):
        raise ValueError(f"invalid output size: {size}")
    if hasattr(src, "validate"):
        src.validate()

    palettes = [ListTag(deepcopy(p)) for p in getattr(src, "palettes_raw", [src.palette_raw])]
    palette = palettes[getattr(src, "palette_index", 0)]
    palette_index = {
        state_key(entry): index for index, entry in enumerate(palette)
        if all(state_key(other[index]) == state_key(entry) for other in palettes)
    }

    def index_for(state):
        if isinstance(state, Integral) and not isinstance(state, bool):
            if not 0 <= state < len(palette):
                raise ValueError(f"palette index out of range: {state}")
            return state
        if state not in palette_index:
            palette_index[state] = len(palette)
            for other in palettes:
                other.append(parse_state(state))
        return palette_index[state]

    def checked_state(state):
        if isinstance(state, str):
            return state_key(parse_state(state))
        index = _integer(state, "block state index")
        if not 0 <= index < len(palette):
            raise ValueError(f"palette index out of range: {index}")
        return index

    def collect(entries, label):
        result = {}
        for raw_pos, state in entries:
            pos = _vector(raw_pos, f"{label} position")
            state = checked_state(state)
            if pos in result and result[pos] != state:
                raise ValueError(
                    f"conflicting {label} states at {pos}: "
                    f"{result[pos]!r} and {state!r}"
                )
            result.setdefault(pos, state)
        return result

    addition_map = collect(additions, "addition")
    replacement_map = collect(replacements, "replacement")
    for pos in addition_map.keys() & replacement_map.keys():
        if addition_map[pos] != replacement_map[pos]:
            raise ValueError(
                f"addition and replacement disagree at {pos}: "
                f"{addition_map[pos]!r} and {replacement_map[pos]!r}"
            )

    def require_bounds(pos):
        if len(pos) != 3 or not all(
            0 <= value < limit for value, limit in zip(pos, size)
        ):
            raise ValueError(f"output block {pos} is outside {size}")

    blocks = ListTag()
    written = set()
    for pos, index in src.present.items():
        target = tuple(value + delta for value, delta in zip(pos, shift))
        require_bounds(target)
        if target in replacement_map:
            continue
        block = deepcopy(getattr(src, "_block_records", {}).get(pos, CompoundTag()))
        block["pos"] = ListTag([IntTag(value) for value in target])
        block["state"] = IntTag(index)
        block.pop("nbt", None)
        if pos in src.block_nbt:
            block["nbt"] = deepcopy(src.block_nbt[pos])
        blocks.append(block)
        written.add(target)

    for pos, state in (*replacement_map.items(), *addition_map.items()):
        require_bounds(pos)
        if pos in written:
            continue
        blocks.append(
            CompoundTag(
                {
                    "pos": ListTag([IntTag(value) for value in pos]),
                    "state": IntTag(index_for(state)),
                }
            )
        )
        written.add(pos)

    entities = ListTag()
    for raw in src.entities:
        entity = deepcopy(raw)
        if "blockPos" in entity:
            entity["blockPos"] = ListTag(
                [
                    IntTag(_integer(value.py_data + delta, "shifted entity block position"))
                    for value, delta in zip(entity["blockPos"], shift)
                ]
            )
        if "pos" in entity:
            entity["pos"] = ListTag(
                [
                    DoubleTag(float(value.py_data) + delta)
                    for value, delta in zip(entity["pos"], shift)
                ]
            )
        if any(shift) and "nbt" in entity:
            nbt = entity["nbt"]
            if "Pos" in nbt and "pos" in entity:
                nbt["Pos"] = deepcopy(entity["pos"])
            if str(nbt.get("id", "")) in {"minecraft:painting", "minecraft:item_frame", "minecraft:glow_item_frame"}:
                for axis, value in zip(("TileX", "TileY", "TileZ"), entity.get("blockPos", ())):
                    if axis in nbt:
                        nbt[axis] = IntTag(value.py_data)
        entities.append(entity)

    root = CompoundTag({
        key: deepcopy(value) for key, value in getattr(src, "_root", {}).items()
        if key not in {"DataVersion", "size", "blocks", "entities", "palettes", "palette"}
    })
    root.update({
        "DataVersion": IntTag(src.data_version),
        "size": ListTag([IntTag(value) for value in size]),
        "blocks": blocks,
        "entities": entities,
    })
    if "palettes" in getattr(src, "_root", {}):
        root["palettes"] = ListTag(palettes)
        if "palette" in src._root:
            root["palette"] = deepcopy(src._root["palette"])
    else:
        root["palette"] = palette
    write_root(root, dst)
    return len(blocks)
