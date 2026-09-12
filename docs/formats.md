# Format recipes

[Format table](https://github.com/kirimba1024/structura-core#formats)
· [Conversion guide](guide.md)

## Conversion matrix and round-trip coverage

Rows are inputs; columns are outputs. `J` preserves the shared Java structure
data, `B` uses the limited Java/Bedrock translation contract below, `L` first
normalizes legacy data, and `C` copies a native document. `—` is unsupported.

| Input → output | `.nbt` | `.snbt` | `.litematic` | `.schem` | `.mcstructure` | `.schematic` |
|---|---|---|---|---|---|---|
| `.nbt` | J | J | J | J | B | — |
| `.snbt` | J | J | J | J | B | — |
| `.litematic` | J | J | C | J | B | — |
| `.schem` | J | J | J | C | B | — |
| `.mcstructure` | B | B | B | B | C | — |
| `.schematic` | L | L | L | L | L+B | — |

There is no legacy writer or return cycle to legacy.

`tests/test_conversion_invariants.py` checks all 16 Java pairs over three return
cycles. Its snapshot compares dimensions, DataVersion, origin, occupied cells,
state properties, block NBT including exact tag/array types, and entities including
duplicates. Palette indices and record order may change without changing that data.
The fixture includes explicit air, structure void, waterlogged stairs, a chest
inventory, Unicode text and fractional entity positions. Sparse-cell normalization
is checked separately because Litematic fills holes with structure void and Sponge
fills them with air; Sponge loss is rejected by strict mode.

`tests/test_format_matrix.py` adds the nine pairs involving Bedrock, also over three
return cycles, and all five legacy import destinations. These cases use a deliberately
representable set of blocks and a fixed Java 1.21.0 schema for Bedrock; they do not
assert that arbitrary NBT, entities or every Minecraft block translates losslessly.
All six attempts to write legacy format are tested for explicit failure without
overwriting an existing file. Together the tests cover all 30 supported routes.

Native-copy tests compare typed document trees, including unknown fields, in
`test_conversion_api.py` and `test_additional_formats.py`. The latter also checks
NBT ↔ SNBT with alternative palettes and metadata, Bedrock layers and an independent
Amulet reader. Other tests cover signed Litematic regions and Sponge v1–v3 fixtures.

Cross-format cycles compare only mutually representable structure data. They do
not preserve document-specific metadata, region layout, scheduled ticks, biomes,
alternative palettes or offsets where the destination cannot carry them. Conversion
warnings expose documented losses; strict mode rejects them before replacing output.
This is regression coverage of the format contract, not proof for every possible
file, game version, modded block or in-game interpretation.

## SNBT: readable structure data

```bash
structura-convert house.nbt house.snbt --strict
structura-convert house.snbt restored.nbt --strict
```

SNBT is UTF-8 Java Structure NBT text. Round trips retain tag types, palettes,
entities and unknown fields; record/palette order is not canonicalized.
`load_structure("house.snbt", max_nbt_bytes=8_000_000)` bounds text before
parsing. Binary NBT is more compact for distribution.

## Sponge v1: keep the source version explicit

```bash
structura-convert old.schem native-copy.schem --strict
structura-convert old.schem normalized.nbt --source-data-version 1343 --strict
```

1343 means the source is Java 1.12.2; declaring it does not translate states.
It cannot contradict a DataVersion already present. Native copies need no
version declaration. The reader supports local palettes, VarInts and
TileEntities; global numeric registries are unsupported.

## Bedrock: native documents and optional block translation

```python
from structura_core import Mcstructure

document = Mcstructure("bedrock.mcstructure")
print(document.size, document.origin)
document.save("native-copy.mcstructure")
```

Base-package copies retain both block layers, entities, block-position data,
origin, unknown fields and UTF-8 strings. Input must be format v1 with the
default palette and two correctly sized index arrays. Native copies do not
upgrade versions; the [standard input guards](guide.md#allocation-guards) apply.

```bash
pip install 'structura-core[bedrock]'
structura-convert house.nbt house.mcstructure --target-version 1.21.0
structura-convert house.mcstructure house.nbt --target-version 1.21.0
```

Python: `load_structure(path, target_version=(1, 21, 0), strict=True)` or
`convert_structure(source, output, target_version=(1, 21, 0), strict=True)`.

| Translation rule | Contract |
|---|---|
| Target | Defaults to 1.21.0; must exactly match a destination schema in installed PyMCTranslate. Java output receives its DataVersion. |
| Source | Java uses the latest known schema no newer than its DataVersion; future versions are rejected. Bedrock uses each palette entry's version. Pre-1.13 numeric blocks are unsupported. |
| Blocks | Known vanilla states and waterlogging; missing cells remain absent, authored air remains air. Normalized coordinates are local; `source_origin` retains origin. |
| Reported losses | Ordinary entities are omitted. Block NBT has a fidelity warning. Changed round-trip states, dropped secondary layers and missing neighbour context are reported. |
| Rejected cases | Unknown blocks/properties, unsupported block-to-entity conversion and neighbour-dependent operations across mixed Bedrock schemas. |

`ConversionWarning` reports approximations; strict mode rejects them before
publishing output. Arbitrary Java/Bedrock conversion is not lossless. Fixtures
are independently generated by Amulet Core, but have not been checked in-game.
The adapter reuses Amulet/PyMCTranslate; no game resources or translation tables
are bundled.
