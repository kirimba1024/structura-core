"""Bedrock structure documents; cross-edition translation is an optional extra."""

import math
from copy import deepcopy
from pathlib import Path
from typing import Tuple

from amulet_nbt import ByteTag, CompoundTag, IntTag, ListTag, StringTag

from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES, check_volume
from .nbt import PathInput, Structure, _integer, _vector, load_root, parse_state, write_root
from .schematic import _compound, _records


class Mcstructure:
    """Own the native little-endian NBT, including both block layers and entities."""

    size: Tuple[int, int, int]
    origin: Tuple[int, int, int]

    def __init__(self, path: PathInput, *, max_blocks: int = DEFAULT_MAX_BLOCKS,
                 max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> None:
        self.path = Path(path)
        self.root = load_root(path, max_nbt_bytes=max_nbt_bytes, little_endian=True)
        self.validate(max_blocks=max_blocks)

    @classmethod
    def from_root(cls, root: CompoundTag, *, max_blocks: int = DEFAULT_MAX_BLOCKS) -> "Mcstructure":
        result = cls.__new__(cls)
        result.path = Path("<memory>")
        result.root = deepcopy(root)
        result.validate(max_blocks=max_blocks)
        return result

    def validate(self, *, max_blocks: int = DEFAULT_MAX_BLOCKS) -> None:
        root = _compound(self.root, "mcstructure")
        if _integer(root.get("format_version"), "format_version") != 1:
            raise ValueError("unsupported mcstructure format_version; expected 1")
        self.size = _vector(root.get("size"), "mcstructure size")
        if any(value < 1 for value in self.size):
            raise ValueError("mcstructure dimensions must be positive")
        volume = math.prod(self.size)
        check_volume(volume, max_blocks)
        self.origin = _vector(root.get("structure_world_origin"), "structure_world_origin")
        self.structure = _compound(root.get("structure"), "structure")
        self.entities = _records(self.structure.get("entities"), "entities")
        palettes = _compound(self.structure.get("palette"), "palette")
        self.palette = _compound(palettes.get("default"), "default palette")
        self.states = _records(self.palette.get("block_palette"), "block_palette")
        for entry in self.states:
            name = entry.get("name")
            if not isinstance(name, StringTag):
                raise ValueError("Bedrock block name must be a string")
            if str(parse_state(str(name))["Name"]) != str(name):
                raise ValueError("Bedrock block names cannot include state properties")
            if "states" in entry:
                states = _compound(entry["states"], "block states")
                if any(not isinstance(value, (ByteTag, IntTag, StringTag)) for value in states.values()):
                    raise ValueError("Bedrock block states must be byte, integer or string tags")
            if "version" in entry:
                _integer(entry["version"], "Bedrock block version")
        self.layers = self.structure.get("block_indices")
        if not isinstance(self.layers, ListTag) or len(self.layers) != 2:
            raise ValueError("mcstructure requires two block-index layers")
        for layer in self.layers:
            if not isinstance(layer, ListTag) or len(layer) != volume:
                raise ValueError(f"each block-index layer must contain {volume} cells")
            if any(not isinstance(value, IntTag) or not -1 <= int(value) < len(self.states) for value in layer):
                raise ValueError("invalid Bedrock palette index")
        self.position_data = _compound(self.palette.get("block_position_data", CompoundTag()), "block_position_data")
        for key, value in self.position_data.items():
            try:
                index = int(key)
            except ValueError as error:
                raise ValueError("invalid block_position_data index") from error
            if str(index) != key or not 0 <= index < volume:
                raise ValueError("out-of-bounds or noncanonical block_position_data index")
            value = _compound(value, "block_position_data record")
            if "block_entity_data" in value:
                _compound(value["block_entity_data"], "block_entity_data")
                if int(self.layers[0][index]) == -1:
                    raise ValueError("block entity without a primary block")

    def save(self, path: PathInput, *, max_blocks: int = DEFAULT_MAX_BLOCKS) -> Path:
        self.validate(max_blocks=max_blocks)
        if Path(path).suffix.lower() != ".mcstructure":
            raise ValueError("native Bedrock output must end in .mcstructure")
        write_root(self.root, path, compressed=False, little_endian=True)
        return Path(path)

    def to_structure(self, *, target_version: Tuple[int, int, int] = (1, 21, 0),
                     strict: bool = False, max_blocks: int = DEFAULT_MAX_BLOCKS) -> Structure:
        """Translate blocks to a known Java schema; report unsupported source data."""
        from .bedrock_translation import import_bedrock

        self.validate(max_blocks=max_blocks)
        return import_bedrock(self, target_version, strict)


def export_mcstructure(src: Structure, output: PathInput, *, target_version: Tuple[int, int, int] = (1, 21, 0),
                       strict: bool = False, max_blocks: int = DEFAULT_MAX_BLOCKS) -> Path:
    from .bedrock_translation import export_bedrock
    from .conversion_losses import conversion_losses, ConversionWarning
    import warnings

    src.validate()
    check_volume(math.prod(src.size), max_blocks)
    losses = conversion_losses(None, src, ".mcstructure", None)
    if losses:
        message = "Conversion omits: " + "; ".join(losses)
        if strict:
            raise ValueError(message)
        warnings.warn(message, ConversionWarning, stacklevel=2)
    root = export_bedrock(src, target_version, strict)
    return Mcstructure.from_root(root, max_blocks=max_blocks).save(output, max_blocks=max_blocks)
