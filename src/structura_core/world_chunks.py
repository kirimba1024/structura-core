from copy import deepcopy

import numpy as np
from amulet_nbt import IntTag

from .blockstates import AIR_NAMES, state_key, validate_palette
from .validation import compound_list, int32, vector
from .block_array import BlockArray


def _section_states(section, version, decode_states):
    states = section.get("block_states", {})
    entries = states.get("palette", section.get("Palette"))
    if entries is None:
        return None
    compound_list(entries, "section palette")
    if not entries:
        raise ValueError("Empty block palette in section")
    validate_palette(entries, "section palette")
    packed = states.get("data", section.get("BlockStates"))
    if packed is None:
        if len(entries) != 1:
            raise ValueError("Missing packed block states")
        indices = np.zeros(4096, dtype=np.uint16)
    else:
        indices = decode_states(packed.np_array, 4096, max(4, (len(entries) - 1).bit_length()), dense=version < 2529)
    if indices.max() >= len(entries):
        raise ValueError("Block palette index out of range")
    return entries, indices


def append_chunk(source, root, cx, cz, palette, max_blocks, decode_states):
    version = int32(root.get("DataVersion", source.data_version), "chunk DataVersion")
    if version < 1451:
        raise ValueError("World viewing currently requires Java 1.13 or newer")
    body = root.get("Level", root)
    if int32(body.get("xPos", cx), "chunk xPos") != cx or int32(body.get("zPos", cz), "chunk zPos") != cz:
        raise ValueError("Chunk coordinates do not match the region index")
    origin = source.source_origin
    top = origin[1] + source.size[1]
    seen = set()
    for section in body.get("sections", body.get("Sections", ())):
        y = int32(section["Y"], "section Y") * 16
        if y + 16 <= origin[1] or y >= top:
            continue
        if y in seen:
            raise ValueError(f"Duplicate section Y in chunk {cx}, {cz}")
        seen.add(y)
        decoded = _section_states(section, version, decode_states)
        if decoded is None:
            continue
        entries, indices = decoded
        remap = []
        for entry in entries:
            state = state_key(entry)
            if state not in palette:
                palette[state] = len(source.palette_raw)
                source.palette_raw.append(deepcopy(entry))
            remap.append(palette[state])
        visible = np.array([str(entry["Name"]) not in AIR_NAMES for entry in entries])[indices]
        if len(source.present) + int(visible.sum()) > max_blocks:
            raise ValueError("World view exceeds the block budget; reduce the radius")
        mapped = np.asarray(remap, dtype=np.int32)[indices]
        if isinstance(source.present, BlockArray):
            grid = np.where(visible, mapped, -1).reshape(16, 16, 16).transpose(2, 0, 1)
            lower = (cx * 16 - origin[0], y - origin[1], cz * 16 - origin[2])
            source.present.set_region(lower, grid)
            continue
        for index in np.flatnonzero(visible).tolist():
            pos = (cx * 16 + index % 16 - origin[0], y + index // 256 - origin[1],
                   cz * 16 + index // 16 % 16 - origin[2])
            source.present[pos] = int(mapped[index])
    for payload in body.get("block_entities", body.get("TileEntities", ())):
        world_pos = vector((payload[axis] for axis in "xyz"), "block entity position")
        pos = tuple(value - offset for value, offset in zip(world_pos, origin))
        if pos in source.present:
            if pos in source.block_nbt:
                raise ValueError(f"Duplicate block entity at {world_pos}")
            nbt = deepcopy(payload)
            nbt.update({axis: IntTag(coordinate) for axis, coordinate in zip("xyz", pos)})
            source.block_nbt[pos] = nbt
    return body
