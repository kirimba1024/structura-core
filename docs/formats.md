# Additional structure formats

All examples use the same validated documents and atomic file writes as the
existing converter. Native I/O does not require Amulet Core.

## SNBT: readable structure data

```bash
structura-convert house.nbt house.snbt --strict
structura-convert house.snbt restored.nbt --strict
```

```python
from structura_core import convert_structure, load_structure

structure = load_structure("house.snbt", max_nbt_bytes=8_000_000)
convert_structure(structure, "restored.nbt", strict=True)
```

SNBT is UTF-8 text containing a Java Structure compound. NBT tag types,
palette variants, entities and unknown fields survive NBT/SNBT round trips.
The same byte limit applies before parsing text. Large structures produce
large text files; use binary NBT for distribution. This is not canonical
semantic diffing: palette order and block-record order are retained.

## Sponge v1: keep the source version explicit

```bash
structura-convert old.schem native-copy.schem --strict
structura-convert old.schem normalized.nbt --source-data-version 1343 --strict
```

The second example assumes the source really is Java 1.12.2 (DataVersion 1343).
Choose the version of the source, not the version you want to run. Assigning
a DataVersion does not translate old block states. Native copies preserve the
document without needing this information. The v1 reader handles local
palettes, VarInt arrays and TileEntities; global numeric registries are
unsupported. An explicit DataVersion cannot contradict one already present.

## Bedrock: native documents and optional block translation

```python
from structura_core import Mcstructure

document = Mcstructure("bedrock.mcstructure")
print(document.size, document.origin)
document.save("native-copy.mcstructure")
```

Native copies retain both block layers, entities, block-position data, origin,
unknown fields and UTF-8 strings. The format must be version 1, use the default
palette, and contain two correctly sized index arrays. The default limit is
2,000,000 cells and 256 MiB of input/decompressed NBT.

Install translation only when needed:

```bash
pip install 'structura-core[bedrock]'
structura-convert house.nbt house.mcstructure --target-version 1.21.0
structura-convert house.mcstructure house.nbt --target-version 1.21.0
```

`--target-version` selects a schema for the destination edition, and must be
an exact schema available in the installed PyMCTranslate database. The default
is 1.21.0. Java output receives the selected schema's DataVersion. Input Java
DataVersions select the latest known schema not newer than the source;
versions beyond the database's coverage are rejected. Bedrock input uses the
version recorded in each block-palette entry. Pre-1.13 numeric Bedrock blocks
are outside the translation contract.

```python
from structura_core import convert_structure, load_structure

structure = load_structure("house.mcstructure", target_version=(1, 21, 0), strict=True)
convert_structure(structure, "house.mcstructure", target_version=(1, 21, 0), strict=True)
```

Translation currently targets known vanilla blocks, including waterlogging.
Missing cells remain absent and explicit air remains air. Coordinates in the
normalized Java structure are local; `source_origin` retains the Bedrock origin.
Native Bedrock copies do not upgrade game versions.

`ConversionWarning` reports approximations; `strict=True` rejects them before
publishing output. Ordinary entities are omitted because the translation
dependency has no entity database. Block-entity payloads are translated with
an explicit fidelity warning, including custom data that might not survive.
Block states changed by a translation round trip, dropped secondary layers
and missing neighbour context are also reported. Unknown blocks/properties,
unsupported block-to-entity conversions and neighbour-dependent operations
across mixed Bedrock schemas fail explicitly. Arbitrary Java/Bedrock conversion
is not lossless, and these files have not been validated by launching Bedrock.

The adapter uses the existing Amulet/PyMCTranslate data; no translation tables
or game resources are bundled. The small interoperability fixture is generated
independently by `tests/fixtures/generate_bedrock.py` using Amulet Core.
