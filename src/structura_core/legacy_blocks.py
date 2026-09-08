import logging
from contextlib import contextmanager
from dataclasses import dataclass

import amulet
from amulet_nbt import CompoundTag, IntTag, ListTag, StringTag


@dataclass
class LegacyBlocks:
    size: tuple
    palette_index: dict
    palette_list: list
    blocks: list
    air_positions: set
    block_entities_count: int


@contextmanager
def open_legacy(path, quiet_errors):
    logger = logging.getLogger("amulet")
    previous_level = logger.level
    level = None
    if quiet_errors:
        logger.setLevel(logging.CRITICAL)
    try:
        level = amulet.load_level(path)
        yield level
    finally:
        try:
            if level is not None:
                level.close()
        finally:
            if quiet_errors:
                logger.setLevel(previous_level)


def block_to_state_compound(block):
    """amulet Block -> {Name, Properties?} compound for the palette."""
    comp = CompoundTag()
    comp["Name"] = StringTag(f"{block.namespace}:{block.base_name}")
    if block.properties:
        props = CompoundTag()
        for k, v in block.properties.items():

            props[k] = StringTag(str(v.py_data if hasattr(v, "py_data") else v))
        comp["Properties"] = props
    return comp


def read_blocks(level, version, *, omit_air, replacements):
    dim = level.dimensions[0]
    bounds = level.bounds(dim)
    (minx, miny, minz), (maxx, maxy, maxz) = bounds.min, bounds.max
    size_x, size_y, size_z = maxx - minx, maxy - miny, maxz - minz

    palette_index = {}
    palette_list = []
    blocks = []
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

                if block.base_name == "air" and block.namespace in {"minecraft", "universal_minecraft"}:
                    if not omit_air:
                        block = amulet.Block("minecraft", "air")
                    else:
                        air_positions.add(pos)
                        continue
                replacement = replacements.get(
                    (block.namespace, block.base_name)
                )
                if replacement is not None:
                    block = amulet.Block(*replacement)
                if block.namespace == "universal_minecraft":
                    raise ValueError(
                        f"untranslated universal block at {(x, y, z)}: {block}"
                    )

                state_key = f"{block.namespace}:{block.base_name}" + (
                    "["
                    + ",".join(
                        f"{k}={v}"
                        for k, v in sorted(
                            (k, (v.py_data if hasattr(v, "py_data") else v))
                            for k, v in block.properties.items()
                        )
                    )
                    + "]"
                    if block.properties
                    else ""
                )

                idx = palette_index.get(state_key)
                if idx is None:
                    idx = len(palette_list)
                    palette_index[state_key] = idx
                    palette_list.append(block_to_state_compound(block))

                entry_nbt = None
                if block_entity is not None:
                    entry_nbt = block_entity.nbt.compound.copy()
                    entry_nbt["id"] = StringTag(block_entity.namespaced_name)
                    block_entities_count += 1

                blocks.append((pos, idx, entry_nbt))

    return LegacyBlocks((size_x, size_y, size_z), palette_index, palette_list, blocks, air_positions, block_entities_count)


def structure_root(data, entities, data_version):
    blocks = ListTag()
    for pos, index, nbt in data.blocks:
        block = CompoundTag({"pos": ListTag([IntTag(value) for value in pos]), "state": IntTag(index)})
        if nbt is not None:
            block["nbt"] = nbt
        blocks.append(block)
    return CompoundTag({
        "DataVersion": IntTag(data_version), "size": ListTag([IntTag(value) for value in data.size]),
        "palette": ListTag(data.palette_list), "blocks": blocks, "entities": ListTag(entities),
    })
