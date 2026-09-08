from dataclasses import dataclass
from itertools import product
from math import floor, prod
from pathlib import Path
from typing import Optional

from amulet_nbt import CompoundTag, IntTag, ListTag

from .blockstates import parse_state
from .limits import DEFAULT_MAX_BLOCKS, check_volume
from .nbt_io import load_root
from .structure import Structure
from .validation import vector
from .world_chunks import append_chunk
from .world_entities import EntityLocation, dimension_id, local_entities, player_entities
from .world_io import read_chunk as read_chunk


@dataclass
class WorldRegion:
    structure: Structure
    loaded: frozenset
    missing: frozenset
    notices: tuple
    dimension: str
    center: tuple
    radius: int
    vertical_radius: int
    sections: Optional[frozenset] = None
    entity_locations: tuple = ()

    def contains_column(self, x, z):
        return (x // 16, z // 16) in self.loaded


class JavaWorld:
    def __init__(self, path):
        self.path = Path(path).expanduser().resolve()
        self.data = load_root(self.path / "level.dat")["Data"]
        self.name = str(self.data.get("LevelName", self.path.name))
        self.data_version = int(self.data.get("DataVersion", 0))
        self.dimensions = {"minecraft:overworld": self.path}
        for name, folder in (("minecraft:the_nether", "DIM-1"), ("minecraft:the_end", "DIM1")):
            if (self.path / folder / "region").is_dir():
                self.dimensions[name] = self.path / folder
        custom = self.path / "dimensions"
        if custom.is_dir():
            for region in custom.rglob("region"):
                relative = region.parent.relative_to(custom)
                if region.is_dir() and len(relative.parts) >= 2:
                    self.dimensions[relative.parts[0] + ":" + "/".join(relative.parts[1:])] = region.parent
        player = self.data.get("Player", {})
        self.start_dimension = dimension_id(player.get("Dimension", "minecraft:overworld"))
        self.start_dimension = self.start_dimension if self.start_dimension in self.dimensions else "minecraft:overworld"
        position = player.get("Pos")
        self.start = tuple(float(v) for v in position) if position is not None else tuple(
            float(self.data.get("Spawn" + axis, 64 if axis == "Y" else 0)) for axis in "XYZ")

    def read_region(self, center=None, *, dimension="minecraft:overworld", radius=1, vertical_radius=48,
                    max_blocks=DEFAULT_MAX_BLOCKS, include_entities=True):
        center = vector(self.start if center is None else center, "Center", integer=False)
        if isinstance(radius, bool) or not isinstance(radius, int) or not 0 <= radius <= 8:
            raise ValueError("Radius must be between 0 and 8 chunks")
        if isinstance(vertical_radius, bool) or not isinstance(vertical_radius, int) or not 16 <= vertical_radius <= 192:
            raise ValueError("Vertical radius must be between 16 and 192 blocks")
        check_volume(0, max_blocks)
        if dimension not in self.dimensions:
            raise ValueError(f"Unknown dimension: {dimension}")
        cx, cz = floor(center[0] / 16), floor(center[2] / 16)
        origin = vector(((cx - radius) * 16, floor((center[1] - vertical_radius) / 16) * 16,
                         (cz - radius) * 16), "region origin")
        top = (floor((center[1] + vertical_radius) / 16) + 1) * 16
        size = ((2 * radius + 1) * 16, top - origin[1], (2 * radius + 1) * 16)
        if prod(size) > 8_000_000:
            raise ValueError("View volume exceeds 8 million cells; reduce the radius")
        try:
            from amulet.utils.world_utils import decode_long_array
        except ImportError as error:
            raise ImportError("Install structura-core[world] or structura-edit[gui,world] to read Java worlds") from error
        source = Structure.from_root(CompoundTag({
            "DataVersion": IntTag(self.data_version), "size": ListTag([IntTag(v) for v in size]),
            "palette": ListTag([parse_state("minecraft:air")]), "blocks": ListTag(), "entities": ListTag(),
        }))
        source.source_origin = origin
        palette = {"minecraft:air": 0}
        loaded, missing, entities, sections = set(), set(), [], set()
        directory = self.dimensions[dimension]
        for x, z in product(range(cx - radius, cx + radius + 1), range(cz - radius, cz + radius + 1)):
            root = read_chunk(directory / "region", x, z)
            if root is None:
                missing.add((x, z))
                continue
            body = append_chunk(source, root, x, z, palette, max_blocks, decode_long_array)
            sections.update((x, int(section["Y"]), z) for section in body.get("sections", ()) if "block_states" in section)
            if include_entities:
                location = EntityLocation(dimension, "region", (x, z))
                entities.extend((payload, location) for payload in body.get("Entities", ()))
                entity_chunk = read_chunk(directory / "entities", x, z)
                if entity_chunk is not None:
                    location = EntityLocation(dimension, "entities", (x, z))
                    entities.extend((payload, location) for payload in entity_chunk.get("Entities", ()))
            loaded.add((x, z))
        if include_entities:
            entities.extend(player_entities(self.path, self.data, located=True))
        source.entities, notices, locations = local_entities(entities, dimension, origin, size, located=True)
        source.validate()
        return WorldRegion(source, frozenset(loaded), frozenset(missing), notices,
                           dimension, center, radius, vertical_radius, frozenset(sections), locations)
