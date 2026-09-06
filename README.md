# structura-core

Reusable Minecraft Java 1.21.1 structure-processing core. It owns:

- validated Java Structure NBT I/O;
- legacy schematic conversion and numeric analysis;
- NumPy/SciPy voxel geometry primitives (connected components, closing).

Structure input accepts gzip-compressed and raw NBT, including files with
multiple palettes; output is gzip-compressed and reproducible byte for byte.

The library targets Minecraft Java 1.21.1 by default. Version constants live
in `structura_core.version`; callers can still pass an explicit Amulet
translation target to the legacy converter.

```bash
pip install -e '.[legacy]'
structura-analyze path/to/structure.nbt --json
```

The `legacy` extra is only needed for `.schematic` conversion and Sponge
`.schem` export. Normal Structure NBT processing stays independent of
`amulet-core`.

Legacy conversion keeps paintings and item frames by default, which is safe
for generated structures. Preview tools can call `convert(...,
preserve_all_entities=True)` to retain mobs, armor stands and loose items as
well, including their exact fractional positions and NBT payloads.

Generated additions may replace explicit air, but never overwrite source
solid blocks. Every saved position is bounds-checked.
