from __future__ import annotations

from pathlib import Path
import warnings
from structura_core import ConversionWarning, Litematic, Mcstructure, Schematic, Structure, convert_structure, export_litematic, export_mcstructure, load_structure, save_structure


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
        written: int = save_structure(structure, "copy.nbt", structure.size)
        assert written >= 0
    result = convert_structure(structure, "copy.schem", strict=True)
    export_litematic(structure, "copy.litematic")
    result = convert_structure(structure, "copy.snbt", strict=True)
    structure = schematic.to_structure(data_version=1343)
    bedrock = Mcstructure(source, max_blocks=1000)
    origin: tuple[int, int, int] = bedrock.origin
    structure = bedrock.to_structure(target_version=(1, 21, 0), strict=True)
    if origin == (0, 0, 0):
        export_mcstructure(structure, "copy.mcstructure", target_version=(1, 21, 0), strict=True)
    return result, structure
