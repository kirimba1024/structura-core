#!/usr/bin/env python3
"""
Milestone 1: convert a legacy .schematic into a vanilla Structure NBT
(data/<ns>/structure/*.nbt) for a target Java Edition version.

Uses amulet-core purely for its legacy numeric-id+meta -> modern blockstate
translation table (PyMCTranslate). We do NOT use amulet's own save/format
wrappers, because amulet-core has no writer for the vanilla Java structure
NBT format (only schematic/sponge_schem/construction/mcstructure) -- so we
serialize the palette/blocks/entities ourselves, by hand, matching the
format documented in docs/milestone-1-plan.md.
"""
import argparse
import gzip
import logging
from pathlib import Path

import amulet
from amulet_nbt import CompoundTag, ListTag, IntTag, StringTag, NamedTag

from .version import DATA_VERSION, JAVA_VERSION

# Blocks that are never a deliberate material choice in a curated
# structure -- replaced unconditionally at conversion time, every asset,
# no per-file opt-in. bedrock: unbreakable, and its only realistic source
# is a WorldEdit selection reaching the world floor -- not flagged for
# review, just swapped, since any other stone would have looked the same
# to the original builder (see structura_core.analyze.bedrock_fraction
# and info.txt CURATION for the asset that prompted this).
FORCED_REPLACEMENTS = {
    ("minecraft", "bedrock"): ("minecraft", "cobblestone"),
}


# Target DataVersion for 1.21.1 (Java Edition release). Update if you target
# a different patch version.
def block_to_state_compound(block):
    """amulet Block -> {Name, Properties?} compound for the palette."""
    comp = CompoundTag()
    comp["Name"] = StringTag(f"{block.namespace}:{block.base_name}")
    if block.properties:
        props = CompoundTag()
        for k, v in block.properties.items():
            # amulet stores property values as amulet_nbt string/byte/int tags;
            # structure NBT palette properties are always strings.
            props[k] = StringTag(str(v.py_data if hasattr(v, "py_data") else v))
        comp["Properties"] = props
    return comp


def _split_exterior_interior_air(air_positions, solid_positions, size_x, size_y, size_z):
    """Classify each air cell as "exterior" (open padding -- omit, so it
    doesn't carve craters into destination terrain) or "interior" (a real
    room -- place explicitly so it's hollowed out even when embedded in a
    hill).

    Recipe: binary_closing with radius 1 seals 1-block windows/doors, then
    binary_fill_holes marks cavities the border flood can't reach. Interior
    air is those cavities, plus the sealed openings that actually touch a
    cavity (the window/door cells themselves).

    An earlier version used a 7x7x7 kernel (radius 3) and then took
    `fill_holes(closed) & ~solid`. That second term includes the whole
    morphological skin closing added around the outside of the building,
    so most of the "interior" was actually a 1-3 block air shell around
    the walls -- which /place then carves into the destination terrain
    as a crater. Radius 3 also sealed 3-block eaves/yards into fake rooms.
    Radius 1 matches the gaps we actually want to seal; keeping only
    holes plus hole-adjacent sealed cells drops the exterior skin.

    border_value=1: scipy's erosion (the second half of closing) treats
    the outside of the array as empty by default, so a wall sitting flush
    against any face of the schematic gets eaten. Treating the outside as
    solid keeps those walls intact. fill_holes still sees the array
    border as true exterior -- only the closing step needs this.
    """
    import numpy as np
    from scipy import ndimage

    solid = np.zeros((size_x, size_y, size_z), dtype=bool)
    for pos in solid_positions:
        solid[pos] = True

    closed = ndimage.binary_closing(
        solid, structure=np.ones((3, 3, 3), dtype=bool), border_value=1
    )
    holes = ndimage.binary_fill_holes(closed) & ~closed
    sealed = closed & ~solid
    windows = sealed & ndimage.binary_dilation(holes)
    interior_mask = holes | windows

    interior = {tuple(p) for p in np.argwhere(interior_mask)} & air_positions
    exterior = air_positions - interior
    return exterior, interior


_DOOR_FACING = {
    "north": (0, 0, -1), "south": (0, 0, 1),
    "east": (1, 0, 0), "west": (-1, 0, 0),
}


def _door_clearance(blocks, palette_list, size, solid_positions, interior_air):
    """Force explicit air 2 steps on both sides of every door.

    Interior rooms already have air from the classifier. Exterior door
    faces would otherwise be omitted, and destination terrain would plug
    the opening. Facing says which way the leaf swings, not which side
    is outside -- so both directions get cleared. Never overwrites solid.
    """
    sx, sy, sz = size
    extra = set()
    for pos, idx, _ in blocks:
        name = str(palette_list[idx]["Name"])
        if not name.endswith("_door"):
            continue
        props = palette_list[idx].get("Properties")
        if props is None or str(props.get("half", "")) != "lower":
            continue
        if "facing" not in props:
            continue
        vec = _DOOR_FACING.get(str(props["facing"]))
        if vec is None:
            continue
        x, y, z = pos
        dx, _, dz = vec
        for sign in (1, -1):
            for step in (1, 2):
                for dy in (0, 1):
                    p = (x + dx * step * sign, y + dy, z + dz * step * sign)
                    px, py, pz = p
                    if not (0 <= px < sx and 0 <= py < sy and 0 <= pz < sz):
                        continue
                    if p in solid_positions or p in interior_air:
                        continue
                    extra.add(p)
    return extra


def convert(
    src_path: str,
    dst_path: str,
    data_version: int,
    target_version=JAVA_VERSION,
    quiet_errors: bool = True,
):
    if len(target_version) != 3 or any(part < 0 for part in target_version):
        raise ValueError(f"invalid Java target version: {target_version!r}")
    if quiet_errors:
        logging.getLogger("amulet").setLevel(logging.CRITICAL)

    level = amulet.load_level(src_path)
    try:
        dim = level.dimensions[0]
        bounds = level.bounds(dim)
        (minx, miny, minz), (maxx, maxy, maxz) = bounds.min, bounds.max
        size_x, size_y, size_z = maxx - minx, maxy - miny, maxz - minz

        version = ("java", tuple(target_version))

        palette_index = {}  # blockstate-string -> index
        palette_list = []   # CompoundTag list, in index order
        blocks = []          # list of (pos, state_index, nbt_or_None)
        air_positions = set()
        block_entities_count = 0
        for x in range(minx, maxx):
            for y in range(miny, maxy):
                for z in range(minz, maxz):
                    try:
                        block, block_entity = level.get_version_block(
                            x, y, z, dim, version
                        )
                    except Exception as error:
                        raise RuntimeError(
                            f"failed to translate block at {(x, y, z)} to {version}"
                        ) from error

                    pos = (x - minx, y - miny, z - minz)

                    # universal air with stray legacy block_data properties
                    # (WorldEdit metadata leftovers) collapses to plain air.
                    if block.base_name == "air":
                        air_positions.add(pos)
                        continue
                    replacement = FORCED_REPLACEMENTS.get((block.namespace, block.base_name))
                    if replacement is not None:
                        block = amulet.Block(*replacement)
                    if block.namespace == "universal_minecraft":
                        raise ValueError(
                            f"untranslated universal block at {(x, y, z)}: {block}"
                        )

                    state_key = f"{block.namespace}:{block.base_name}" + (
                        "[" + ",".join(f"{k}={v}" for k, v in sorted(
                            (k, (v.py_data if hasattr(v, 'py_data') else v))
                            for k, v in block.properties.items()
                        )) + "]" if block.properties else ""
                    )

                    idx = palette_index.get(state_key)
                    if idx is None:
                        idx = len(palette_list)
                        palette_index[state_key] = idx
                        palette_list.append(block_to_state_compound(block))

                    entry_nbt = None
                    if block_entity is not None:
                        entry_nbt = block_entity.nbt.compound.copy()
                        block_entities_count += 1

                    blocks.append((pos, idx, entry_nbt))

        # Trim the bounding box to the actual building. The source
        # .schematic's WorldEdit selection is usually padded well beyond the
        # real structure (the original builder eyeballing a region), and
        # `size` isn't just cosmetic -- terrain_adaptation's skirt and
        # dimension_padding both operate over the full declared footprint,
        # so a loose bounding box drags the terrain-blending staircase out
        # across empty margin where there's no building at all.
        if not blocks:
            raise ValueError(f"source contains no non-air blocks: {src_path}")

        bx = [p[0] for p, _, _ in blocks]
        by = [p[1] for p, _, _ in blocks]
        bz = [p[2] for p, _, _ in blocks]
        ox, oy, oz = min(bx), min(by), min(bz)
        new_size_x, new_size_y, new_size_z = max(bx) - ox + 1, max(by) - oy + 1, max(bz) - oz + 1
        if (ox, oy, oz) != (0, 0, 0) or (new_size_x, new_size_y, new_size_z) != (size_x, size_y, size_z):
            print(f"    trimmed bounding box: {size_x}x{size_y}x{size_z} -> "
                  f"{new_size_x}x{new_size_y}x{new_size_z} (offset {ox},{oy},{oz})")
            blocks = [((x - ox, y - oy, z - oz), idx, nbt) for (x, y, z), idx, nbt in blocks]
            air_positions = {
                (x - ox, y - oy, z - oz) for (x, y, z) in air_positions
                if ox <= x <= ox + new_size_x - 1 and oy <= y <= oy + new_size_y - 1
                and oz <= z <= oz + new_size_z - 1
            }
            size_x, size_y, size_z = new_size_x, new_size_y, new_size_z

        # Air: exterior (open padding around the building) is omitted so it
        # doesn't carve a crater into destination terrain; interior (fully
        # enclosed pockets -- real rooms) is placed explicitly so those
        # rooms get hollowed out even when the piece lands partway inside a
        # hill and would otherwise show raw terrain poking through.
        solid_positions = {pos for pos, _, _ in blocks}
        exterior_air, interior_air = _split_exterior_interior_air(
            air_positions, solid_positions, size_x, size_y, size_z
        )

        door_air = _door_clearance(
            blocks, palette_list, (size_x, size_y, size_z),
            solid_positions, interior_air,
        )
        air_to_place = interior_air | door_air
        if air_to_place:
            air_idx = palette_index.get("minecraft:air")
            if air_idx is None:
                air_idx = len(palette_list)
                palette_index["minecraft:air"] = air_idx
                comp = CompoundTag()
                comp["Name"] = StringTag("minecraft:air")
                palette_list.append(comp)
            for pos in air_to_place:
                blocks.append((pos, air_idx, None))
        print(f"    air: {len(exterior_air)} exterior (omitted), "
              f"{len(interior_air)} interior, "
              f"{len(door_air)} door-clearance (placed explicitly)")

        # Build the structure NBT root compound.
        root = CompoundTag()
        root["DataVersion"] = IntTag(data_version)
        root["size"] = ListTag([IntTag(size_x), IntTag(size_y), IntTag(size_z)])
        root["palette"] = ListTag(palette_list)

        blocks_tag = ListTag()
        for (bx, by, bz), idx, entry_nbt in blocks:
            comp = CompoundTag()
            comp["pos"] = ListTag([IntTag(bx), IntTag(by), IntTag(bz)])
            comp["state"] = IntTag(idx)
            if entry_nbt is not None:
                comp["nbt"] = entry_nbt
            blocks_tag.append(comp)
        root["blocks"] = blocks_tag

        root["entities"] = ListTag()  # milestone 1: no entity migration yet

        destination = Path(dst_path)
        destination.parent.mkdir(parents=True, exist_ok=True)
        raw = NamedTag(root, "").save_to(compressed=False)
        destination.write_bytes(gzip.compress(raw, mtime=0))

        print(f"OK  {src_path}")
        print(f"    -> {dst_path}")
        print(f"    size: {size_x}x{size_y}x{size_z}")
        print(f"    palette entries: {len(palette_list)}")
        print(f"    blocks written: {len(blocks)}")
        print(f"    block entities: {block_entities_count}")
    finally:
        level.close()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("src", help="legacy .schematic path")
    ap.add_argument("dst", help="output vanilla structure .nbt path")
    ap.add_argument("--data-version", type=int, default=DATA_VERSION)
    ap.add_argument(
        "--target-version", default="1.21.1",
        help="Amulet block translation target, for example 1.21.1",
    )
    args = ap.parse_args()
    try:
        target_version = tuple(int(part) for part in args.target_version.split("."))
    except ValueError:
        ap.error("--target-version must contain three integers, for example 1.21.1")
    if len(target_version) != 3:
        ap.error("--target-version must contain three integers, for example 1.21.1")
    convert(args.src, args.dst, args.data_version, target_version)


if __name__ == "__main__":
    main()
