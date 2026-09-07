"""Native structure formats without legacy translation dependencies."""

from pathlib import Path
from typing import Optional

from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES
from .litematic import Litematic
from .nbt import PathInput, Structure
from .schematic import Schematic


def load_structure(path: PathInput, *, region: Optional[str] = None, palette_index: int = 0,
                   max_blocks: int = DEFAULT_MAX_BLOCKS, max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES) -> Structure:
    """Read Structure NBT, Litematic or Sponge, retaining the source Minecraft version."""
    path = Path(path)
    if path.suffix.lower() == ".litematic":
        if palette_index != 0:
            raise ValueError("Litematic has one palette per region; palette_index must be 0")
        return Litematic(path, max_nbt_bytes=max_nbt_bytes).to_structure(region=region, max_blocks=max_blocks)
    if path.suffix.lower() == ".schem":
        if region is not None or palette_index != 0:
            raise ValueError("Sponge input has one palette and no named regions")
        return Schematic(path, max_nbt_bytes=max_nbt_bytes).to_structure(max_blocks=max_blocks)
    if path.suffix.lower() != ".nbt":
        raise ValueError(f"unsupported native input {path.suffix!r}; expected .nbt, .litematic or .schem")
    if region is not None:
        raise ValueError("region applies only to Litematic input")
    return Structure(path, palette_index=palette_index, max_nbt_bytes=max_nbt_bytes)
