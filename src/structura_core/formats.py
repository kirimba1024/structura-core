"""Native structure formats without legacy translation dependencies."""

from pathlib import Path

from .litematic import DEFAULT_MAX_BLOCKS, Litematic
from .nbt import Structure


def load_structure(path, *, region=None, palette_index=0, max_blocks=DEFAULT_MAX_BLOCKS):
    """Read Structure NBT or Litematic, retaining the source Minecraft version."""
    path = Path(path)
    if path.suffix.lower() == ".litematic":
        if palette_index != 0:
            raise ValueError("Litematic has one palette per region; palette_index must be 0")
        return Litematic(path).to_structure(region=region, max_blocks=max_blocks)
    if path.suffix.lower() != ".nbt":
        raise ValueError(f"unsupported native input {path.suffix!r}; expected .nbt or .litematic")
    if region is not None:
        raise ValueError("region applies only to Litematic input")
    return Structure(path, palette_index=palette_index)
