from __future__ import annotations

from pathlib import Path
import warnings
from structura_core import ConversionWarning, Litematic, Schematic, Structure, convert_structure, export_litematic, load_structure, save_structure


def use_api(source: Path, data: bytes) -> tuple[Path, Structure]:
    warnings.filterwarnings("default", category=ConversionWarning)
    structure = Structure.from_bytes(data, max_nbt_bytes=1_000_000)
    document = Litematic(source)
    region: str = document.region_names[0]
    structure = load_structure(source, region=region)
    structure = document.to_structure(region=region)
    schematic = Schematic(source)
    width: int = schematic.size[0]
    block: str | None = structure.name_at((0, 0, 0))
    if block and width > 0:
        save_structure(structure, "copy.nbt", structure.size)
    result = convert_structure(structure, "copy.schem", strict=True)
    export_litematic(structure, "copy.litematic")
    return result, structure
