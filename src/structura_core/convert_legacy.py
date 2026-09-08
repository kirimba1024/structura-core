import argparse

from .legacy_blocks import (
    amulet as amulet,
    block_to_state_compound as block_to_state_compound,
    open_legacy,
    read_blocks,
    structure_root,
)
from .legacy_entities import (
    LEGACY_ENTITIES as LEGACY_ENTITIES,
    LEGACY_ENTITY_ALIASES as LEGACY_ENTITY_ALIASES,
    _entity_data as _entity_data,
    _legacy_entities as _legacy_entities,
    _legacy_tile_text as _legacy_tile_text,
    _schematic_root as _schematic_root,
    _structure_entity as _structure_entity,
    restore_sign_text,
)
from .nbt_io import load_root, write_root
from .validation import int32
from .version import DATA_VERSION, JAVA_VERSION


def _structure_root(data, entities, data_version):
    records = [_structure_entity(position, payload) for position, payload in entities]
    return structure_root(data, records, data_version)


def convert(
    src_path: str,
    dst_path: str,
    data_version: int,
    target_version=JAVA_VERSION,
    quiet_errors: bool = True,
    preserve_all_entities: bool = False,
    *,
    prepare_for_placement: bool = False,
):
    """Translate legacy input while preserving selection geometry and materials."""
    if prepare_for_placement:
        raise ValueError("Placement preparation moved to structura_geo.convert_legacy.convert")
    data_version = int32(data_version, "DataVersion")
    if len(target_version) != 3 or any(part < 0 for part in target_version):
        raise ValueError(f"invalid Java target version: {target_version!r}")
    target_version = tuple(int32(part, "Java version component") for part in target_version)
    with open_legacy(src_path, quiet_errors) as level:
        data = read_blocks(level, ("java", target_version), omit_air=False, replacements={})
        legacy_root = load_root(src_path)
        entities = _legacy_entities(legacy_root, preserve_all_entities)
        legacy_text = _legacy_tile_text(legacy_root)
        restored = restore_sign_text(data.blocks, legacy_text, (0, 0, 0))
        print(f"    sign text restored: {restored}")
        root = _structure_root(data, entities, data_version)
        print(f"    entities carried: {len(root['entities'])}")
        write_root(root, dst_path)
        print(f"OK  {src_path}")
        print(f"    -> {dst_path}")
        print(f"    size: {'x'.join(map(str, data.size))}")
        print(f"    palette entries: {len(data.palette_list)}")
        print(f"    blocks written: {len(data.blocks)}")
        print(f"    block entities: {data.block_entities_count}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="legacy .schematic path")
    ap.add_argument("dst", help="output vanilla structure .nbt path")
    ap.add_argument("--data-version", type=int, default=DATA_VERSION)
    ap.add_argument(
        "--preserve-layout", action="store_true",
        help="retained for compatibility; selection layout is always preserved",
    )
    ap.add_argument("--all-entities", action="store_true", help="retain every source entity")
    ap.add_argument(
        "--target-version",
        default="1.21.1",
        help="Amulet block translation target, for example 1.21.1",
    )
    args = ap.parse_args()
    try:
        target_version = tuple(int(part) for part in args.target_version.split("."))
    except ValueError:
        ap.error("--target-version must contain three integers, for example 1.21.1")
    if len(target_version) != 3:
        ap.error("--target-version must contain three integers, for example 1.21.1")
    convert(
        args.src, args.dst, args.data_version, target_version,
        preserve_all_entities=args.all_entities,
        prepare_for_placement=False,
    )


if __name__ == "__main__":
    main()
