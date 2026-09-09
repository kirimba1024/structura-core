from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from .validation import vector
from .world import JavaWorld
from .world_io import read_chunk
from .world_patch import invalidate_poi, patch_chunk
from .world_staging import StagedWorld


def save_world_patch(path, patch, *, entities=(), force=False):
    from portalocker import Lock

    if not patch and not entities:
        return None
    world = JavaWorld(path)
    if world.data_version < 2844:
        raise ValueError("World writing requires Java 1.18 or newer")
    grouped = defaultdict(dict)
    for (dimension, x, y, z), pair in patch.items():
        x, y, z = vector((x, y, z), "world position")
        if dimension not in world.dimensions:
            raise ValueError(f"Unknown dimension: {dimension}")
        grouped[dimension, x // 16, z // 16][x, y, z] = pair
    work = world.path / ".structura"
    work.mkdir(exist_ok=True)
    with Lock(str(work / "write.lock"), mode="a+b", timeout=0), TemporaryDirectory(prefix="save-", dir=work) as temporary:
        stage = StagedWorld(world.path, Path(temporary))
        for (dimension, cx, cz), changes in grouped.items():
            directory = world.dimensions[dimension]
            region = stage.region(directory / "region", cx, cz)
            root = read_chunk(region, cx, cz)
            if root is None:
                raise ValueError(f"Destination chunk is absent at {cx}, {cz}")
            sections = patch_chunk(root, cx, cz, changes, force=force)
            if not sections:
                continue
            stage.write(region, cx, cz, root)
            poi = directory / "poi"
            if (poi / f"r.{cx // 32}.{cz // 32}.mca").exists():
                staged_poi = stage.region(poi, cx, cz)
                poi_root = read_chunk(staged_poi, cx, cz)
                if poi_root is not None and invalidate_poi(poi_root, sections):
                    stage.write(staged_poi, cx, cz, poi_root)
        if entities:
            from .world_entity_write import stage_entity_changes

            stage_entity_changes(world, stage, entities)
        return stage.install()


def world_conflicts(path, patch):
    from amulet.utils.world_utils import decode_long_array
    from amulet_nbt import from_snbt

    from .blockstates import parse_state, state_key
    from .world_chunks import _section_states
    from .world_patch import normalized_cell

    world = JavaWorld(path)
    grouped = defaultdict(dict)
    for (dimension, x, y, z), pair in patch.items():
        if dimension not in world.dimensions:
            raise ValueError(f"Unknown dimension: {dimension}")
        grouped[dimension, x // 16, z // 16][x, y, z] = pair
    conflicts = []
    for (dimension, cx, cz), changes in grouped.items():
        root = read_chunk(world.dimensions[dimension] / "region", cx, cz)
        if root is None:
            conflicts.extend((position, pair[0][0], "absent chunk", pair[1][0])
                             for position, pair in sorted(changes.items()))
            continue
        version = int(root.get("DataVersion", 0))
        entities = {tuple(int(entity[axis]) for axis in "xyz"): entity for entity in root.get("block_entities", ())}
        sections = {int(section["Y"]): section for section in root.get("sections", ())}
        by_section = defaultdict(list)
        for position, pair in changes.items():
            by_section[position[1] // 16].append((position, pair))
        for cy, entries in sorted(by_section.items()):
            section = sections.get(cy)
            palette = indices = None
            if section is not None and "block_states" in section:
                palette, indices = _section_states(section, version, decode_long_array)
                keys = [state_key(entry) for entry in palette]
            for position, (before, after) in sorted(entries):
                x, y, z = position
                if indices is None:
                    conflicts.append((position, before[0], "absent section", after[0]))
                    continue
                index = x % 16 + 16 * (z % 16) + 256 * (y % 16)
                current = normalized_cell(keys[int(indices[index])], entities.get(position))
                expected = normalized_cell(state_key(parse_state(before[0])), from_snbt(before[1]) if before[1] else None)
                if current != expected:
                    conflicts.append((position, before[0], current[0], after[0]))
    return conflicts
