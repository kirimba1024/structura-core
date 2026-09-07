"""Data that the selected native conversion cannot carry to its destination."""

import math

from .litematic import Litematic
from .schematic import Schematic


class ConversionWarning(UserWarning):
    """An otherwise valid conversion omits source data."""


def _fields(mapping, retained):
    names = sorted(mapping.keys() - set(retained))
    shown = ", ".join(repr(name) for name in names[:5])
    return shown + (f" (+{len(names) - 5} more)" if len(names) > 5 else "")


def document_losses(document, region):
    losses = []
    if isinstance(document, Litematic):
        names = document.region_names if region is None else (region,)
        losses.append(f"Litematic region names/layout ({len(names)} selected region(s))")
        if document.root.get("Metadata"):
            losses.append("Litematic document metadata")
        for key in ("PendingBlockTicks", "PendingFluidTicks"):
            if any(document.root["Regions"][name].get(key) for name in names):
                losses.append(f"Litematic {key}")
        unknown = _fields(document.root, ("Version", "SubVersion", "MinecraftDataVersion", "Metadata", "Regions"))
        if unknown:
            losses.append(f"Litematic fields: {unknown}")
        if any(_fields(document.root["Regions"][name], (
            "Position", "Size", "BlockStatePalette", "BlockStates", "TileEntities", "Entities",
            "PendingBlockTicks", "PendingFluidTicks",
        )) for name in names):
            losses.append("additional Litematic region fields")
    elif isinstance(document, Schematic):
        root = document.root
        if any(key in root for key in ("Biomes", "BiomeData", "BiomePalette")):
            losses.append("Sponge biomes")
        if root.get("Metadata"):
            losses.append("Sponge document metadata")
        unknown = _fields(root, (
            "Version", "DataVersion", "Width", "Height", "Length", "Offset", "Metadata",
            "Blocks", "Palette", "PaletteMax", "BlockData", "BlockEntities", "TileEntities", "Entities",
            "Biomes", "BiomeData", "BiomePalette", "BiomePaletteMax",
        ))
        if unknown:
            losses.append(f"Sponge fields: {unknown}")
        if root is not document._document and _fields(document._document, ("Schematic",)):
            losses.append("additional Sponge document fields")
        if document.version == 3:
            blocks = root.get("Blocks", {})
            if _fields(blocks, ("Palette", "Data", "BlockEntities")) or any(
                _fields(record, ("Id", "Pos", "Data"))
                for records in (root.get("Entities", ()), blocks.get("BlockEntities", ()))
                for record in records
            ):
                losses.append("additional Sponge v3 container fields")
    return losses


def conversion_losses(document, src, target, region):
    losses = document_losses(document, region)
    if any(getattr(src, "source_origin", (0, 0, 0))):
        losses.append(f"source origin/offset {src.source_origin}")
    if target == ".nbt":
        return losses
    if len(src.palettes_raw) > 1:
        losses.append(f"{len(src.palettes_raw) - 1} alternative palette(s)")
    unknown = _fields(src._root, ("DataVersion", "size", "palette", "palettes", "blocks", "entities"))
    if unknown:
        losses.append(f"Structure metadata: {unknown}")
    if any(_fields(record, ("pos", "state", "nbt")) for record in src._block_records.values()):
        losses.append("additional Structure block-record fields")
    if any(_fields(record, ("pos", "blockPos", "nbt")) or tuple(int(v) for v in record["blockPos"]) !=
           tuple(math.floor(float(v)) for v in record["pos"]) for record in src.entities):
        losses.append("Structure entity-record fields or independent blockPos")
    if target == ".mcstructure" and any(src.palette[index] == "minecraft:structure_void" for index in src.present.values()):
        losses.append("explicit structure_void cells become omitted cells")
    if target == ".schem":
        if len(src.present) < math.prod(src.size):
            losses.append(f"{math.prod(src.size) - len(src.present)} omitted cell(s) become air")
    if target in {".schem", ".mcstructure"} and any(_fields(entry, ("Name", "Properties")) for entry in src.palette_raw):
        losses.append("additional palette-entry fields")
    return losses
