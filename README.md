# structura-core

Reusable Minecraft Java 1.21.1 structure-processing core. It owns:

- validated Java Structure NBT I/O;
- legacy schematic conversion and numeric analysis;
- NumPy/SciPy envelope, terrain-pod and foundation geometry;
- loot, connector, template-pool and worldgen JSON generators.

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

Generated additions may replace explicit air, but never overwrite source
solid blocks. Every saved position is bounds-checked.
