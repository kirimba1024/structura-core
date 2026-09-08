"""Native Java structures and optional Bedrock block translation."""

from pathlib import Path
from typing import Optional, Tuple
import warnings

from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES
from .litematic import Litematic
from .nbt_io import PathInput
from .schematic import Schematic
from .structure import Structure
from .version import JAVA_VERSION

STRUCTURE_SUFFIXES = (".nbt", ".snbt", ".litematic", ".schem", ".mcstructure", ".schematic")


def load_structure(path: PathInput, *, region: Optional[str] = None, palette_index: int = 0,
                   max_blocks: int = DEFAULT_MAX_BLOCKS, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
                   source_data_version: Optional[int] = None,
                   target_version: Optional[Tuple[int, int, int]] = None, strict: bool = False) -> Structure:
    """Read Java formats without changing game versions, or translate Bedrock to Java."""
    path = Path(path)
    if source_data_version is not None and path.suffix.lower() != ".schem":
        raise ValueError("source_data_version applies only to Sponge input")
    if target_version is not None and path.suffix.lower() != ".mcstructure":
        raise ValueError("target_version applies only to Bedrock input")
    if path.suffix.lower() == ".schematic":
        from .conversion_losses import ConversionWarning

        if region is not None or palette_index != 0:
            raise ValueError("Legacy input has one palette and no named regions")
        version = ".".join(map(str, JAVA_VERSION))
        message = f"Legacy schematic is normalized to Java {version}; legacy format metadata is not retained"
        if strict:
            raise ValueError(message)
        try:
            from .convert_legacy import read_legacy
        except ImportError as error:
            raise ImportError("Legacy .schematic input requires structura-core[legacy]") from error
        warnings.warn(message, ConversionWarning, stacklevel=2)
        root, _ = read_legacy(str(path), max_blocks=max_blocks, max_nbt_bytes=max_nbt_bytes)
        return Structure.from_root(root)
    if path.suffix.lower() == ".mcstructure":
        from .bedrock import Mcstructure

        if region is not None or palette_index != 0:
            raise ValueError("Bedrock input has no named regions or Java palette variants")
        return Mcstructure(path, max_blocks=max_blocks, max_nbt_bytes=max_nbt_bytes).to_structure(
            target_version=target_version if target_version is not None else (1, 21, 0), strict=strict, max_blocks=max_blocks)
    if path.suffix.lower() == ".litematic":
        if palette_index != 0:
            raise ValueError("Litematic has one palette per region; palette_index must be 0")
        return Litematic(path, max_nbt_bytes=max_nbt_bytes).to_structure(region=region, max_blocks=max_blocks)
    if path.suffix.lower() == ".schem":
        if region is not None or palette_index != 0:
            raise ValueError("Sponge input has one palette and no named regions")
        return Schematic(path, max_nbt_bytes=max_nbt_bytes).to_structure(max_blocks=max_blocks, data_version=source_data_version)
    if path.suffix.lower() not in {".nbt", ".snbt"}:
        raise ValueError(f"unsupported input {path.suffix!r}; expected {', '.join(STRUCTURE_SUFFIXES)}")
    if region is not None:
        raise ValueError("region applies only to Litematic input")
    return Structure(path, palette_index=palette_index, max_nbt_bytes=max_nbt_bytes)
