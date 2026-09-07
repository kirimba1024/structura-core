# structura-core

Reusable Minecraft Java 1.21.1 structure-processing core. It owns:

- validated Java Structure NBT I/O;
- native Litematic v5, v6 and v7 reading and writing;
- native Sponge Schematic v2/v3 reading and lossless document copies;
- legacy schematic conversion and numeric analysis;
- NumPy/SciPy voxel geometry primitives (connected components, closing).

Structure input accepts gzip-compressed and raw NBT, including files with
multiple palettes. Saving preserves all palettes, root metadata, additional
block fields, block entities and entities. Repeated saves of the same data
produce reproducible gzip bytes; they need not match the original file bytes.

The library targets Minecraft Java 1.21.1 by default. Version constants live
in `structura_core.version`; callers can still pass an explicit Amulet
translation target to the legacy converter.
Native I/O retains the source Minecraft `DataVersion` and does not upgrade
block states or entity payloads between game versions.

```bash
pip install structura-core
structura-analyze path/to/structure.nbt --json
```

## Native conversion

Use the same conversion from Python or the command line:

```python
from structura_core import convert_structure

output = convert_structure("house.nbt", "house.litematic")
```

The result is an absolute `Path`. A `Structure` object is also accepted and
uses its active palette. Existing low-level functions remain available.
Public entry points include type annotations and IDE completion information.

```bash
structura-convert house.litematic house.nbt
structura-convert house.nbt house.litematic
structura-convert worldedit.schem house.litematic
structura-convert house.litematic house.schem --region Main
```

Conversions emit one `ConversionWarning` describing source data they omit,
such as region names, nonzero offsets, biomes, alternative palettes or custom
metadata. Only losses found in this input are reported. Use `strict=True` in
Python or `--strict` in the CLI to reject reported loss before writing.
An existing output survives strict rejection and serialization failure.
CLI notices go to stderr; stdout remains the output path.

```python
convert_structure("house.schem", "native-copy.schem", strict=True)
```

Same-format Litematic/Sponge copies retain the entire native document and
remain quiet, including unknown fields. Cross-format conversion cannot carry
all native metadata. Strict mode checks the documented loss categories; it
does not translate Minecraft versions or establish that every game-specific
NBT payload has identical meaning in a different format.

These commands need only the base package. Litematic is parsed directly with
the existing NBT dependency. Litemapy is used to produce an interoperability
test fixture, and is not an installation dependency.

```python
from structura_core import Litematic, Structure, export_litematic, load_structure

document = Litematic("house.litematic")
print(document.region_names)
structure = load_structure("house.litematic", region="Main")
export_litematic(structure, "house-copy.litematic")

structure = Structure.from_bytes(nbt_bytes)
structure = Structure.from_root(nbt_compound)
```

`from_root` owns a copy; caller-owned NBT is not modified. Both in-memory
constructors use the same validation as `Structure(path)`.

| Operation | Preserved / conversion rules |
|---|---|
| `Litematic(path).save(output)` | All native regions, metadata, pending ticks and unknown NBT fields; gzip bytes are reproducible. |
| `Litematic.to_structure()` | Block states, block entities, entity payloads and positions; all disjoint regions share one bounding box. |
| `load_structure(path, region="Main")` | One named Litematic region; blocks are normalized to nonnegative local coordinates. `source_origin` maps them back to schematic coordinates. |
| `export_litematic(structure, output)` | One region at `(0,0,0)`, using the selected palette. Missing cells become `minecraft:structure_void`, the no-placement marker; explicit air remains air. |

Negative region sizes do not mirror the blocks. Entity positions and block
positions use different Litematic coordinate conventions, both handled by the
reader. Overlapping regions are rejected instead of depending on file order;
choose a region explicitly. Unsupported versions and malformed arrays fail
with a `ValueError`.

Cross-format conversion does not preserve Litematic region names/layout,
placement origin, preview, scheduling ticks or arbitrary document metadata in
Structure NBT. Keep the native `Litematic` document when these matter.
Litematic export uses the active Structure palette; other palette variants and
additional Structure block-record fields are not representable there.
Minecraft entity `id` values are required for export. No IDs are guessed.

Native Litematic decoding and encoding default to at most 2,000,000 cells,
checked before unpacking or allocating block arrays. Raise `max_blocks` in
Python or `--max-blocks` in the converter for trusted larger files. This is an
allocation guard, not a sandbox for arbitrary untrusted compressed files.

All native file readers and `Structure.from_bytes` also limit input and
decompressed NBT to 256 MiB each, before passing it to the NBT parser. Set
`max_nbt_bytes` explicitly for trusted larger inputs; `structura-convert`
exposes `--max-nbt-bytes`. The bound applies to raw and gzip NBT, including
same-format document copies. Invalid/truncated NBT raises `ValueError`.
This byte limit does not bound all parser allocations or total process memory.

## Sponge Schematic v2 and v3

Modern WorldEdit `.schem` files need no Amulet Core or version translation:

```python
from structura_core import Schematic, load_structure

document = Schematic("house.schem")
print(document.size, document.offset)
structure = document.to_structure()
document.save("copy.schem")
structure = load_structure("house.schem", max_blocks=2_000_000)
```

`Schematic.from_root(compound)` owns a copy of the input. Native `save()` and
`.schem` → `.schem` conversion preserve the original v2/v3 layout, offset,
biomes, metadata and unknown NBT fields. Blocks, properties, block entities,
entity NBT and fractional positions are available through `to_structure()`.
Sparse palette indices and unsigned dimensions are supported. Invalid indices,
truncated/overflowing VarInts, duplicate block entities and excessive volumes
fail explicitly; the default cell limit is 2,000,000.

Block and entity positions stay local to the selection; `source_origin` holds
its paste offset. Structure NBT and Litematic conversion do not carry Sponge
biomes, paste offset, document metadata or unknown v3 entity-container fields.
Keep the `Schematic` document when these matter. V3 documents without a Blocks
container retain their entities without inventing air cells. A block palette
is required when blocks are present; global numeric registries are unsupported.
Sponge v1 is outside the native reader's contract.

Fixtures generated by Amulet Core 1.9.35 independently verify both layouts,
nonzero offsets and multibyte block indices. Format details follow the
[Sponge v2](https://github.com/SpongePowered/Schematic-Specification/blob/master/versions/schematic-2.md)
and [v3 specifications](https://github.com/SpongePowered/Schematic-Specification/blob/master/versions/schematic-3.md).

## Stable responsibilities

`nbt.py` owns Structure validation and serialization; `litematic.py` and
`schematic.py` adapt their native formats; `formats.py` selects the reader; `convert.py` supplies the CLI.
Readers retain block state IDs and properties rather than maintaining another
Minecraft registry. A game upgrade does not silently rewrite source data.

New editing tools and interactive navigation belong to a separate future
`structura-edit` package. Existing generation helpers remain available for
compatibility.

## Legacy input and existing helpers

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
