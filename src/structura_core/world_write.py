from collections import defaultdict
from pathlib import Path
from tempfile import TemporaryDirectory

from .validation import vector
from .world import JavaWorld
from .world_io import read_chunk
from .world_patch import invalidate_poi, patch_chunk
from .world_staging import StagedWorld


def save_world_patch(path, patch, *, entities=()):
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
            sections = patch_chunk(root, cx, cz, changes)
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
