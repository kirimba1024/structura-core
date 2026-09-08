"""Convert Structure NBT/SNBT, Litematic, Sponge and optional Bedrock block data."""

import argparse
import math
import warnings
from os import PathLike
from pathlib import Path
from typing import Optional, Tuple, Union

from .bedrock import Mcstructure, export_mcstructure
from .conversion_losses import ConversionWarning, conversion_losses, document_losses
from .export_schematic import export_schematic
from .formats import load_structure
from .limits import DEFAULT_MAX_BLOCKS, DEFAULT_MAX_NBT_BYTES, check_volume
from .litematic import Litematic, export_litematic
from .schematic import Schematic
from .structure import Structure
from .structure_writer import save_structure


def convert_structure(source: Union[str, PathLike[str], Structure], output: Union[str, PathLike[str]], *,
                      region: Optional[str] = None, palette_index: int = 0, strict: bool = False,
                      max_blocks: int = DEFAULT_MAX_BLOCKS,
                      max_nbt_bytes: int = DEFAULT_MAX_NBT_BYTES,
                      source_data_version: Optional[int] = None,
                      target_version: Optional[Tuple[int, int, int]] = None) -> Path:
    """Convert native formats; warn about data loss or reject it before writing with strict=True."""
    output = Path(output).expanduser().resolve()
    target = output.suffix.lower()
    if target not in {".nbt", ".snbt", ".litematic", ".schem", ".mcstructure"}:
        raise ValueError("output must end in .nbt, .snbt, .litematic, .schem or .mcstructure")
    check_volume(0, max_blocks)
    if source_data_version is not None and (isinstance(source, Structure) or Path(source).suffix.lower() != ".schem"):
        raise ValueError("source_data_version applies only to Sponge input")
    from_bedrock = not isinstance(source, Structure) and Path(source).suffix.lower() == ".mcstructure"
    if target_version is not None and not (from_bedrock or target == ".mcstructure"):
        raise ValueError("target_version applies only to cross-edition Bedrock conversions")
    document = None
    if isinstance(source, Structure):
        if region is not None or palette_index != 0:
            raise ValueError("region and palette_index apply to file inputs; Structure uses its active palette")
        src = source
    else:
        source = Path(source).expanduser()
        suffix = source.suffix.lower()
        if suffix == ".mcstructure":
            if region is not None or palette_index != 0:
                raise ValueError("Bedrock input has no named regions or Java palette variants")
            bedrock = Mcstructure(source, max_blocks=max_blocks, max_nbt_bytes=max_nbt_bytes)
            if suffix == target:
                if target_version is not None:
                    raise ValueError("native Bedrock copies do not translate game versions")
                return bedrock.save(output, max_blocks=max_blocks)
            src = bedrock.to_structure(target_version=target_version if target_version is not None else (1, 21, 0),
                                      strict=strict, max_blocks=max_blocks)
        elif suffix in {".litematic", ".schem"}:
            if palette_index != 0 or (suffix == ".schem" and region is not None):
                raise ValueError("palette_index applies only to Structure NBT; region only to Litematic")
            reader = Litematic if suffix == ".litematic" else Schematic
            document = reader(source, max_nbt_bytes=max_nbt_bytes)
            if suffix == target and region is None:
                return document.save(output)
            src = (document.to_structure(region=region, max_blocks=max_blocks) if isinstance(document, Litematic)
                   else document.to_structure(max_blocks=max_blocks, data_version=source_data_version))
        else:
            src = load_structure(source, region=region, palette_index=palette_index,
                                 max_blocks=max_blocks, max_nbt_bytes=max_nbt_bytes)
    losses = (document_losses(document, region) if target == ".mcstructure" else
              conversion_losses(document, src, ".nbt" if target == ".snbt" else target, region))
    if target not in {".nbt", ".snbt"}:
        check_volume(math.prod(src.size), max_blocks)
    if losses:
        message = "Conversion omits: " + "; ".join(losses)
        if strict:
            raise ValueError(message)
        warnings.warn(message, ConversionWarning, stacklevel=2)
    if target == ".mcstructure":
        export_mcstructure(src, output, target_version=target_version if target_version is not None else (1, 21, 0),
                           strict=strict, max_blocks=max_blocks)
    elif target in {".nbt", ".snbt"}:
        save_structure(src, output, src.size)
    elif target == ".litematic":
        export_litematic(src, output, max_blocks=max_blocks)
    else:
        export_schematic(src, output)
    return output


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--region", help="one named Litematic region")
    parser.add_argument("--palette", type=int, default=0, help="Structure NBT palette index")
    parser.add_argument("--max-blocks", type=int, default=DEFAULT_MAX_BLOCKS)
    parser.add_argument("--max-nbt-bytes", type=int, default=DEFAULT_MAX_NBT_BYTES)
    parser.add_argument("--source-data-version", type=int, help="explicit Minecraft DataVersion for Sponge v1")
    parser.add_argument("--target-version", help="exact Java/Bedrock translation schema, e.g. 1.21.0; only for Bedrock conversion")
    parser.add_argument("--strict", action="store_true", help="reject data loss before writing")
    args = parser.parse_args(argv)
    try:
        target_version = tuple(int(value) for value in args.target_version.split(".")) if args.target_version else None
        with warnings.catch_warnings(record=True) as notices:
            warnings.simplefilter("always", ConversionWarning)
            convert_structure(args.src, args.output, region=args.region, palette_index=args.palette,
                              strict=args.strict, max_blocks=args.max_blocks, max_nbt_bytes=args.max_nbt_bytes,
                              source_data_version=args.source_data_version, target_version=target_version)
        for notice in notices:
            parser._print_message(f"warning: {notice.message}\n")
    except (ValueError, OSError, ImportError) as error:
        parser.error(str(error))
    print(args.output)


if __name__ == "__main__":
    main()
