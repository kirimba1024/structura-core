from dataclasses import dataclass
from pathlib import Path
import re

import numpy as np

from .blockstates import AIR_NAMES, state_key
from .validation import int32
from .world_chunks import _section_states
from .world_io import read_chunk


@dataclass(frozen=True)
class TerrainSection:
    position: tuple
    palette: tuple
    blocks: np.ndarray
    block_entities: tuple = ()


def existing_chunks(directory):
    chunks = []
    for path in sorted(Path(directory).glob("r.*.*.mca")):
        match = re.fullmatch(r"r\.(-?\d+)\.(-?\d+)\.mca", path.name)
        if match is None:
            continue
        rx, rz = map(int, match.groups())
        with path.open("rb") as stream:
            header = stream.read(8192)
        if len(header) != 8192:
            raise ValueError(f"Truncated region header: {path.name}")
        for index, location in enumerate(np.frombuffer(header[:4096], dtype=">u4")):
            if location:
                if location >> 8 < 2 or not location & 255:
                    raise ValueError(f"Invalid chunk location in {path.name}")
                chunks.append((rx * 32 + index % 32, rz * 32 + index // 32))
    return tuple(sorted(chunks))


def terrain_sections(directory, cx, cz, data_version):
    from amulet.utils.world_utils import decode_long_array

    root = read_chunk(directory, cx, cz)
    if root is None:
        raise ValueError("World changed during reading; refresh the overview")
    version = int32(root.get("DataVersion", data_version), "chunk DataVersion")
    if version < 1451:
        raise ValueError("World viewing currently requires Java 1.13 or newer")
    body = root.get("Level", root)
    if (int32(body.get("xPos", cx), "chunk xPos"), int32(body.get("zPos", cz), "chunk zPos")) != (cx, cz):
        raise ValueError("Chunk coordinates do not match the region index")
    seen = set()
    entities = {}
    for payload in body.get("block_entities", body.get("TileEntities", ())):
        coordinates = tuple(int32(payload[axis], "block entity position") for axis in "xyz")
        if coordinates[0] // 16 != cx or coordinates[2] // 16 != cz:
            raise ValueError("Block entity is outside its chunk")
        entities.setdefault(coordinates[1] // 16, []).append(payload)
    for section in body.get("sections", body.get("Sections", ())):
        y = int32(section["Y"], "section Y")
        if y in seen:
            raise ValueError(f"Duplicate section Y in chunk {cx}, {cz}")
        seen.add(y)
        decoded = _section_states(section, version, decode_long_array)
        if decoded is None:
            continue
        entries, indices = decoded
        states = tuple(state_key(entry) for entry in entries)
        air = np.asarray([str(entry["Name"]) in AIR_NAMES for entry in entries])
        blocks = np.where(air[indices], -1, indices).astype(np.int32).reshape(16, 16, 16).transpose(2, 0, 1).copy()
        yield TerrainSection((cx, y, cz), states, blocks, tuple(entities.get(y, ())))


def terrain_stamp(directory):
    result = []
    for path in sorted(Path(directory).iterdir()):
        if path.suffix in (".mca", ".mcc") and path.is_file():
            stat = path.stat()
            result.append((path.name, stat.st_size, stat.st_mtime_ns))
    return tuple(result)
