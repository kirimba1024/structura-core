"""Reusable Minecraft structure processing primitives."""

from .bedrock import Mcstructure, export_mcstructure
from .conversion_losses import ConversionWarning
from .formats import load_structure
from .litematic import Litematic, export_litematic
from .schematic import Schematic
from .structure import AIR_NAMES, Structure, parse_state, state_key
from .structure_writer import save_structure

__all__ = [
    "AIR_NAMES", "Structure", "Litematic", "Schematic", "load_structure", "export_litematic",
    "parse_state", "save_structure", "state_key", "convert_structure", "ConversionWarning",
    "Mcstructure", "export_mcstructure",
]
__version__ = "0.6.2"


def __getattr__(name):
    if name == "convert_structure":
        from .convert import convert_structure

        return convert_structure
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
