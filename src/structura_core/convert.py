"""Convert native .nbt and .litematic inputs to .nbt, .litematic or Sponge .schem."""

import argparse
from pathlib import Path

from .export_schematic import export_schematic
from .formats import load_structure
from .litematic import DEFAULT_MAX_BLOCKS, Litematic, export_litematic
from .nbt import save_structure


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("src", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--region", help="one named Litematic region")
    parser.add_argument("--palette", type=int, default=0, help="Structure NBT palette index")
    parser.add_argument("--max-blocks", type=int, default=DEFAULT_MAX_BLOCKS)
    args = parser.parse_args(argv)
    suffix = args.output.suffix.lower()
    if suffix not in {".nbt", ".litematic", ".schem"}:
        parser.error("output must end in .nbt, .litematic or .schem")
    try:
        if args.src.suffix.lower() == suffix == ".litematic" and args.region is None:
            if args.palette != 0:
                parser.error("--palette applies only to Structure NBT")
            Litematic(args.src).save(args.output)
        else:
            src = load_structure(args.src, region=args.region, palette_index=args.palette, max_blocks=args.max_blocks)
            if suffix == ".nbt":
                save_structure(src, args.output, src.size)
            elif suffix == ".litematic":
                export_litematic(src, args.output, max_blocks=args.max_blocks)
            else:
                if src.size[0] * src.size[1] * src.size[2] > args.max_blocks:
                    raise ValueError("Sponge output volume exceeds --max-blocks")
                export_schematic(src, args.output)
    except (ValueError, OSError) as error:
        parser.error(str(error))
    print(args.output)


if __name__ == "__main__":
    main()
