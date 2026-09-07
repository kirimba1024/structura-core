# structura-core

**Read, convert and analyze Minecraft structures.**

Validated structure I/O, explicit conversion-loss reporting and NumPy/SciPy
voxel geometry primitives. Native formats need no Amulet Core translation engine.

## Quick start

```bash
pip install structura-core
structura-convert house.litematic house.nbt
structura-convert house.nbt house.schem
structura-convert house.nbt house.snbt --strict
structura-analyze house.nbt --json
```

## Formats

| Format | Read | Write | Installation |
|---|---|---|---|
| Java Structure `.nbt` | gzip/raw NBT; multiple palettes | gzip NBT | base |
| Java Structure `.snbt` | UTF-8 text | UTF-8 text, preserving NBT value types | base |
| Litematic `.litematic` | v5–v7; named regions | new v5/v7; native copies retain their version | base |
| Sponge `.schem` | v1–v3 | new v2; native copies retain their version | base |
| Bedrock `.mcstructure` | v1 native document | v1 native document / copy | base; `[bedrock]` for conversion to/from Java |
| Legacy `.schematic` | `structura-convert-legacy` | no legacy writer | `[legacy]` |

`structura-convert` converts among the first five formats. Java/Bedrock
translation needs `[bedrock]` and can be lossy. Sponge v1 without a DataVersion
requires `--source-data-version` when converting to another format; supply the
source game's version, not the desired target.

The base package uses `amulet-nbt` for NBT parsing. The separate `amulet-core`
translation dependency is installed only by `[legacy]` or `[bedrock]`.

## Python

```python
from structura_core import convert_structure, load_structure

structure = load_structure("house.litematic", region="Main")
print(structure.size, len(structure.present))
output = convert_structure(structure, "house.schem")
convert_structure("house.nbt", "house.snbt", strict=True)
```

`convert_structure` returns an absolute `Path`. Use `Litematic`, `Schematic` or
`Mcstructure` document objects when native regions, metadata and unknown fields
must survive a document copy.

## Conversion rules

- Native Java conversion retains `DataVersion`; it does not upgrade game data.
- Omitted data produces `ConversionWarning`. `--strict` / `strict=True` rejects reported loss before writing; failed writes preserve an existing destination.
- Same-format native document copies retain their fields. Cross-format conversion cannot preserve metadata that the destination cannot represent.
- Java/Bedrock translation supports known vanilla blocks and waterlogging, omits ordinary entities and warns about block-entity fidelity. Its default target is 1.21.0.

```bash
pip install 'structura-core[bedrock]'
structura-convert house.nbt house.mcstructure --target-version 1.21.0
```

For old `.schematic` files, install `[legacy]` and use
`structura-convert-legacy old.schematic house.nbt --preserve-layout --all-entities`.
The legacy converter defaults to Java 1.21.1; without these flags it prepares
structures for datapack placement.

## Documentation

- [Conversion guide](https://github.com/kirimba1024/structura-core/blob/main/docs/guide.md): preservation rules, Litematic regions, Sponge metadata, limits and existing helpers.
- [Format recipes](https://github.com/kirimba1024/structura-core/blob/main/docs/formats.md): SNBT round trips, Sponge v1 source versions and the full Bedrock translation contract.
- [structura-render](https://github.com/kirimba1024/structura-render): image, vector and 3D output from the same structures.

CLI commands support `--help`. Public entry points include type information
for IDE completion. Interactive editing belongs to the separate `structura-edit`.
