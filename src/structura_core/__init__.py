"""Reusable Minecraft structure processing primitives."""

from .conversion_losses import ConversionWarning
from .formats import load_structure
from .litematic import Litematic, export_litematic
from .nbt import AIR_NAMES, Structure, parse_state, save_structure, state_key
from .schematic import Schematic

__all__ = [
    "AIR_NAMES", "Structure", "Litematic", "Schematic", "load_structure", "export_litematic",
    "parse_state", "save_structure", "state_key", "convert_structure", "ConversionWarning",
]
__version__ = "0.5.0"


def __getattr__(name):
    if name == "convert_structure":
        from .convert import convert_structure

        return convert_structure
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
