from copy import deepcopy
from pathlib import Path
from typing import Dict, List, MutableMapping, Optional, Set, Tuple, Union

from amulet_nbt import CompoundTag, ListTag

from .blockstates import (
    AIR_NAMES as AIR_NAMES,
    _RESOURCE_LOCATION as _RESOURCE_LOCATION,
    parse_state as parse_state,
    state_key as state_key,
    validate_palette as _validate_palette,
)
from .limits import DEFAULT_MAX_NBT_BYTES
from .nbt_io import PathInput, load_root, read_root
from .validation import int32 as _integer, vector as _vector
from .block_array import BlockArray

Position = Tuple[int, int, int]
State = Union[int, str]


class Structure:
    """In-memory Structure NBT with eagerly checked structural invariants."""

    path: Path
    data_version: int
    size: Position
    palette_index: int
    palette: List[str]
    palettes_raw: List[List[CompoundTag]]
    present: MutableMapping[Position, int]
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
        sx, sy, sz = self.size
        palette_size = min(len(self.palette), 2 ** 31)
        if isinstance(self.present, BlockArray):
            self.present.validate(self.size, palette_size)
        for pos, index in (() if isinstance(self.present, BlockArray) else self.present.items()):
            if type(pos) is tuple and len(pos) == 3:
                x, y, z = pos
                if (type(x) is int and type(y) is int and type(z) is int and type(index) is int
                        and 0 <= x < sx and 0 <= y < sy and 0 <= z < sz
                        and 0 <= index < palette_size):
                    continue
            _vector(pos, "block position")
            _integer(index, "block state index")
            if len(pos) != 3 or not all(
                0 <= value < limit for value, limit in zip(pos, self.size)
            ):
                raise ValueError(f"block {pos} is outside {self.size} in {self.path}")
            if not 0 <= index < len(self.palette):
                raise ValueError(f"palette index {index} is invalid in {self.path}")
        dangling = {position for position in self.block_nbt if position not in self.present}
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
