from collections import defaultdict
from copy import deepcopy
from functools import lru_cache

from amulet_nbt import ByteTag, IntTag, ListTag, LongArrayTag, from_snbt

from .blockstates import AIR_NAMES, parse_state, state_key
from .world_chunks import _section_states


def normalized_cell(state, payload):
    if state in AIR_NAMES:
        state = "minecraft:air"
    payload = deepcopy(payload)
    if payload is not None:
        for axis in "xyz":
            payload.pop(axis, None)
    return state, payload


def patch_chunk(root, cx, cz, changes):
    from amulet.utils.world_utils import decode_long_array, encode_long_array

    canonical = lru_cache(maxsize=4096)(lambda state: state_key(parse_state(state)))
    version = int(root.get("DataVersion", 0))
    if version < 2844:
        raise ValueError("World writing requires Java 1.18 or newer")
    if (int(root["xPos"]), int(root["zPos"])) != (cx, cz):
        raise ValueError("Chunk coordinates do not match the region index")
    sections = {int(section["Y"]): section for section in root.get("sections", ())}
    if len(sections) != len(root.get("sections", ())):
        raise ValueError("Duplicate sections in chunk")
    entities = {}
    for entity in root.get("block_entities", ()):
        position = tuple(int(entity[axis]) for axis in "xyz")
        if position in entities:
            raise ValueError(f"Duplicate block entity at {position}")
        entities[position] = entity
    grouped = defaultdict(list)
    for position, pair in changes.items():
        grouped[position[1] // 16].append((position, pair))
    touched = set()
    for cy, entries in grouped.items():
        section = sections.get(cy)
        if section is None or "block_states" not in section:
            raise ValueError(f"Destination section is absent at {cx}, {cy}, {cz}")
        palette, indices = _section_states(section, version, decode_long_array)
        palette = deepcopy(palette)
        indices = indices.copy()
        keys = [state_key(entry) for entry in palette]
        lookup = {key: index for index, key in enumerate(keys)}
        changed = False
        for position, (before, after) in entries:
            x, y, z = position
            index = (x % 16) + 16 * (z % 16) + 256 * (y % 16)
            current = normalized_cell(keys[int(indices[index])], entities.get(position))
            desired = normalized_cell(canonical(after[0]), from_snbt(after[1]) if after[1] else None)
            if current == desired:
                continue
            expected = normalized_cell(canonical(before[0]), from_snbt(before[1]) if before[1] else None)
            if current != expected:
                raise ValueError(f"World changed at {position}; refresh and resolve the conflicting edit before saving")
            state = canonical(after[0])
            if state not in lookup:
                lookup[state] = len(palette)
                palette.append(parse_state(state))
                keys.append(state)
            indices[index] = lookup[state]
            if desired[1] is None:
                entities.pop(position, None)
            else:
                payload = desired[1]
                payload.update({axis: IntTag(value) for axis, value in zip("xyz", position)})
                entities[position] = payload
            touched.add(position)
            changed = True
        if changed:
            states = section["block_states"]
            states["palette"] = palette
            if len(palette) == 1:
                states.pop("data", None)
            else:
                states["data"] = LongArrayTag(encode_long_array(indices, bits_per_entry=max(4, (len(palette) - 1).bit_length()), dense=False))
    if touched:
        root["block_entities"] = ListTag(list(entities.values()))
        root.pop("Heightmaps", None)
        root["isLightOn"] = ByteTag(0)
        for section in sections.values():
            section.pop("SkyLight", None)
            section.pop("BlockLight", None)
        for name in ("block_ticks", "fluid_ticks"):
            if name in root:
                root[name] = ListTag([tick for tick in root[name] if tuple(int(tick[axis]) for axis in "xyz") not in touched])
    return {position[1] // 16 for position in touched}


def invalidate_poi(root, sections):
    changed = False
    for cy in sections:
        section = root.get("Sections", {}).get(str(cy))
        if section is not None:
            section["Valid"] = ByteTag(0)
            changed = True
    return changed
