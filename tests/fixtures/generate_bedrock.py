"""Generate the small independent Bedrock fixture using Amulet Core 1.9.35."""

from pathlib import Path
import numpy as np
from amulet.api.selection import SelectionBox, SelectionGroup
from amulet.level.formats.mcstructure.chunk import MCStructureChunk
from amulet.level.formats.mcstructure.format_wrapper import MCStructureFormatWrapper
from amulet_nbt import CompoundTag, IntTag, StringTag

path = Path(__file__).with_name("amulet-bedrock.mcstructure")
box = SelectionBox((-3, 6, 2), (0, 8, 6))
stone = CompoundTag(
    {
        "name": StringTag("minecraft:stone"),
        "states": CompoundTag(),
        "version": IntTag(18153475),
    }
)
dirt = CompoundTag(
    {
        "name": StringTag("minecraft:dirt"),
        "states": CompoundTag({"dirt_type": StringTag("normal")}),
        "version": IntTag(18153475),
    }
)
palette = np.empty(2, dtype=object)
palette[0] = (stone,)
palette[1] = (dirt,)
blocks = np.arange(24, dtype=np.uint32).reshape(box.shape) % 2
wrapper = MCStructureFormatWrapper(str(path))
wrapper.create_and_open(
    "bedrock", (1, 21, 0), bounds=SelectionGroup(box), overwrite=True
)
wrapper._put_raw_chunk_data(
    -1, 0, MCStructureChunk(box, blocks, palette, [], []), wrapper.dimensions[0]
)
with path.open("wb") as stream:
    wrapper.save_to(stream)
wrapper.close()
