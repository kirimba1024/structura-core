from collections.abc import Iterable
from copy import deepcopy
from itertools import chain
from numbers import Integral
from typing import Tuple

from amulet_nbt import CompoundTag, IntTag, ListTag

from .blockstates import parse_state, state_key
from .entity_positions import block_entity_at, shift_entity
from .nbt_io import PathInput, write_root
from .structure import Position, State, Structure
from .validation import int32, vector


def _checked_state(state, palette_size):
    if isinstance(state, str):
        return state_key(parse_state(state))
    index = int32(state, "block state index")
    if not 0 <= index < palette_size:
        raise ValueError(f"palette index out of range: {index}")
    return index


def _collect_changes(entries, label, palette_size):
    result = {}
    for raw_pos, state in entries:
        pos = vector(raw_pos, f"{label} position")
        state = _checked_state(state, palette_size)
        if pos in result and result[pos] != state:
            raise ValueError(f"conflicting {label} states at {pos}: {result[pos]!r} and {state!r}")
        result.setdefault(pos, state)
    return result


def _require_bounds(pos, size):
    if len(pos) != 3 or not all(0 <= value < limit for value, limit in zip(pos, size)):
        raise ValueError(f"output block {pos} is outside {size}")


def _write_blocks(src, size, shift, palettes, additions, replacements):
    palette = palettes[getattr(src, "palette_index", 0)]
    palette_index = {
        state_key(entry): index for index, entry in enumerate(palette)
        if all(state_key(other[index]) == state_key(entry) for other in palettes)
    }

    def index_for(state):
        if isinstance(state, Integral) and not isinstance(state, bool):
            if not 0 <= state < len(palette):
                raise ValueError(f"palette index out of range: {state}")
            return state
        if state not in palette_index:
            palette_index[state] = len(palette)
            for other in palettes:
                other.append(parse_state(state))
        return palette_index[state]

    blocks = ListTag()
    written = set()
    for pos, index in src.present.items():
        target = tuple(value + delta for value, delta in zip(pos, shift))
        _require_bounds(target, size)
        if target in replacements:
            continue
        block = deepcopy(getattr(src, "_block_records", {}).get(pos, CompoundTag()))
        block["pos"] = ListTag([IntTag(value) for value in target])
        block["state"] = IntTag(index)
        block.pop("nbt", None)
        if pos in src.block_nbt:
            payload = src.block_nbt[pos]
            block["nbt"] = block_entity_at(payload, target) if any(shift) else deepcopy(payload)
        blocks.append(block)
        written.add(target)
    for pos, state in chain(replacements.items(), additions.items()):
        _require_bounds(pos, size)
        if pos in written:
            continue
        blocks.append(CompoundTag({
            "pos": ListTag([IntTag(value) for value in pos]), "state": IntTag(index_for(state)),
        }))
        written.add(pos)
    return blocks


def structure_root(src, size, shift=(0, 0, 0), additions=(), replacements=()):
    size = vector(size, "output size")
    shift = vector(shift, "shift")
    if any(value <= 0 for value in size):
        raise ValueError(f"invalid output size: {size}")
    if hasattr(src, "validate"):
        src.validate()
    palettes = [ListTag(deepcopy(p)) for p in getattr(src, "palettes_raw", [src.palette_raw])]
    palette = palettes[getattr(src, "palette_index", 0)]
    addition_map = _collect_changes(additions, "addition", len(palette))
    replacement_map = _collect_changes(replacements, "replacement", len(palette))
    for pos in addition_map.keys() & replacement_map.keys():
        if addition_map[pos] != replacement_map[pos]:
            raise ValueError(f"addition and replacement disagree at {pos}: "
                             f"{addition_map[pos]!r} and {replacement_map[pos]!r}")
    blocks = _write_blocks(src, size, shift, palettes, addition_map, replacement_map)
    entities = ListTag([shift_entity(record, shift) for record in src.entities])
    root = CompoundTag({
        key: deepcopy(value) for key, value in getattr(src, "_root", {}).items()
        if key not in {"DataVersion", "size", "blocks", "entities", "palettes", "palette"}
    })
    root.update({
        "DataVersion": IntTag(src.data_version),
        "size": ListTag([IntTag(value) for value in size]),
        "blocks": blocks,
        "entities": entities,
    })
    if "palettes" in getattr(src, "_root", {}):
        root["palettes"] = ListTag(palettes)
        if "palette" in src._root:
            root["palette"] = deepcopy(src._root["palette"])
    else:
        root["palette"] = palette
    return root


def save_structure(
    src: Structure,
    dst: PathInput,
    size: Position,
    shift: Position = (0, 0, 0),
    additions: Iterable[Tuple[Position, State]] = (),
    replacements: Iterable[Tuple[Position, State]] = (),
) -> int:
    """Save without discarding palettes or metadata.

    Additions preserve every authored cell, including air. String states are
    literal in all palettes; integer states select the corresponding variant
    in each palette. Replacements explicitly replace a cell and its block NBT.
    """

    root = structure_root(src, size, shift, additions, replacements)
    write_root(root, dst)
    return len(root["blocks"])
