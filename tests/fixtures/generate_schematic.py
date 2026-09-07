"""Regenerate independent block fixtures with optional Amulet Core 1.9.35."""

from pathlib import Path

import numpy as np
from amulet.api.block import Block
from amulet.api.selection import SelectionBox, SelectionGroup
from amulet.level.formats.sponge_schem.chunk import SpongeSchemChunk
from amulet.level.formats.sponge_schem.format_wrapper import SpongeSchemFormatWrapper
from amulet_nbt import CompoundTag, IntArrayTag, StringTag


def main():
    directory = Path(__file__).parent
    bounds = SelectionBox((-5, 6, 2), (0, 9, 15))
    palette = np.empty(130, dtype=object)
    palette[:] = [Block('fixture', 'block', {'index': StringTag(str(i))}) for i in range(130)]
    blocks = np.arange(195, dtype=np.uint32).reshape((5, 3, 13)) % 130
    nbt = CompoundTag({'Id': StringTag('fixture:container'), 'Pos': IntArrayTag([-4, 7, 4]),
                       'CustomName': StringTag('independent')})
    for version in (2, 3):
        output = directory / f'amulet-v{version}.schem'
        wrapper = SpongeSchemFormatWrapper(str(output))
        wrapper.create_and_open('java', (1, 20, 4), bounds=SelectionGroup(bounds), overwrite=True,
                                schematic_version=version)
        wrapper._put_raw_chunk_data(-1, 0, SpongeSchemChunk(bounds, blocks, palette, [nbt], []), wrapper.dimensions[0])
        with output.open('wb') as stream:
            wrapper.save_to(stream)
        wrapper.close()


if __name__ == '__main__':
    main()
