# structura-core

Reusable Minecraft Java 1.21.1 structure-processing core. It owns:

- validated Java Structure NBT I/O;
- legacy schematic conversion and numeric analysis;
- NumPy/SciPy voxel geometry primitives (connected components, closing).

Structure input accepts gzip-compressed and raw NBT, including files with
multiple palettes. Saving preserves all palettes, root metadata, additional
block fields, block entities and entities. Repeated saves of the same data
produce reproducible gzip bytes; they need not match the original file bytes.

The library targets Minecraft Java 1.21.1 by default. Version constants live
in `structura_core.version`; callers can still pass an explicit Amulet
translation target to the legacy converter.

```bash
pip install structura-core
structura-analyze path/to/structure.nbt --json
```

The `legacy` extra is needed for legacy input conversion. Structure NBT
processing and Sponge v2 `.schem` export do not require `amulet-core`.

```bash
pip install 'structura-core[legacy]'
structura-convert-legacy old.schematic structure.nbt
structura-export-schematic structure.nbt structure.schem
```

For local development, use `pip install -e '.[legacy]'` from this package's
directory.

Legacy conversion keeps paintings and item frames by default, which is safe
for generated structures. Preview tools can call `convert(...,
preserve_all_entities=True)` to retain mobs, armor stands and loose items as
well, including their exact fractional positions and NBT payloads.

For conversion that retains selection bounds, authored air, bedrock and block
connections, pass `prepare_for_placement=False` as well, or use:

```bash
structura-convert-legacy old.schematic preserved.nbt --preserve-layout --all-entities
```

The converter's historical default still prepares a structure for datapack
placement: it trims bounds, replaces bedrock, repairs pane/bar connections and
selects interior/door-clearance air. Preview tools use the preserving mode.
Conversion retains custom entity namespaces and supplies translated block
entity IDs, allowing the result to be exported as Sponge without guessing IDs.

Generated `additions` fill missing cells and preserve authored cells, including
explicit air. Use `replacements` to intentionally replace a cell; replacement
also removes its old block entity NBT. Coordinates and palette indices must be
integers in the NBT range. Every saved block is bounds-checked, and a failed
write leaves an existing destination intact.

```python
from structura_core import Structure, save_structure
from structura_core.export_schematic import export_schematic

structure = Structure("house.nbt", palette_index=0)
save_structure(structure, "copy.nbt", structure.size)
export_schematic(structure, "house.schem")
```

Selecting `palette_index` chooses the active view without discarding the other
palettes on save. An integer addition selects the corresponding variant in
each palette; a string such as `"minecraft:stone"` adds that literal state to
every palette. Shifts update entity positions and known vanilla hanging-entity
coordinates, while retaining unrelated custom NBT.

Sponge v2 has a single palette and a dense block array: export uses the selected
palette and fills missing cells with air. Entities and block entity payloads
are included; an entity without an `id` raises an error. This export does not
translate Minecraft versions, and the output retains the source `DataVersion`.
