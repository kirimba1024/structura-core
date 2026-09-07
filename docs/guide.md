# Conversion guide

[Quick start and formats](https://github.com/kirimba1024/structura-core#readme)
· [SNBT, Sponge v1 and Bedrock recipes](formats.md)

## Native conversion

```python
from structura_core import Litematic, Structure, convert_structure, export_litematic, load_structure

document = Litematic("house.litematic")
print(document.region_names)
structure = load_structure("house.litematic", region="Main")
export_litematic(structure, "single-region.litematic")
convert_structure("house.schem", "native-copy.schem", strict=True)
structure = Structure.from_bytes(nbt_bytes)
structure = Structure.from_root(nbt_compound)
```

`from_root` copies caller-owned NBT; both in-memory constructors share file
validation. Structure inputs use the active palette. CLI notices go to stderr; stdout
is the output path.

| Operation | Contract |
|---|---|
| Structure NBT save | Retains palettes, root metadata, block-record fields, block entities and entities. Repeated saves produce reproducible gzip bytes, not necessarily original bytes. |
| Native Litematic/Sponge/Bedrock copy | Retains native layout, version and unknown fields without normalization. |
| Cross-format conversion | Reports observed omissions with `ConversionWarning`; strict mode rejects them before writing. Missing cells, offsets and metadata follow each destination's rules. |

Strict mode covers documented losses, not identical game-specific semantics
in another format. Failed serialization preserves an existing output.

## Litematic

New Litematic output is v5 for DataVersion ≤3700, otherwise v7. Litemapy is
only a fixture generator, not a dependency.

- `Litematic.save()` retains all regions, metadata, pending ticks and unknown fields.
- `to_structure()` combines disjoint regions in one bounding box, retaining block states, block entities and entity payloads/positions. Overlaps fail; select `region="Main"` explicitly.
- Negative region sizes do not mirror blocks. Local positions become nonnegative; `source_origin` maps them back to schematic coordinates.
- `export_litematic()` writes one region at `(0,0,0)` using the selected palette. Missing cells become `minecraft:structure_void`; authored air remains air. Entity IDs are required.

Normalization loses region names/layout, origin, previews, ticks and arbitrary
native metadata. Alternative Structure palettes and additional block-record
fields cannot be exported to Litematic. Keep the document when these matter.

## Sponge Schematic

```python
from structura_core import Schematic

document = Schematic("house.schem")
print(document.size, document.offset)
structure = document.to_structure()
document.save("copy.schem")
```

`from_root()` owns a copy. Native copies retain version layout, offset, biomes,
metadata and unknown NBT.
V1 without a DataVersion needs an explicit [source version](formats.md#sponge-v1-keep-the-source-version-explicit)
for normalization, but not copying.

`to_structure()` retains block properties, block-entity NBT, entity payloads and
fractional positions. Coordinates stay local; `source_origin` holds the paste
offset. Conversion to Structure/Litematic loses biomes, offset, document
metadata and unknown v3 entity-container fields.

Sparse palette indices and unsigned dimensions are supported. Malformed
VarInts, invalid indices, duplicate block entities and excessive volumes fail.
V3 without Blocks retains entities without inventing air cells. A local
palette is required when blocks exist; global numeric registries are unsupported.
Independent Amulet Core fixtures verify v2/v3 layouts, offsets and multibyte indices.

Sponge export uses the selected palette, fills missing cells with air, requires
entity IDs, and retains source DataVersion. It includes entities and block NBT.
The standalone command is `structura-export-schematic house.nbt house.schem`.

## Allocation guards

Native file readers and `Structure.from_bytes` limit input/decompressed NBT to
256 MiB each, before parsing; the input limit also covers UTF-8 SNBT and native
copies. Override `max_nbt_bytes` / `--max-nbt-bytes` for trusted larger inputs.
Litematic/Sponge/Bedrock default to 2,000,000 cells (`max_blocks` / `--max-blocks`)
before decoding or allocating arrays. These guards do not bound all parser
allocations or total process memory. Invalid/truncated data raises `ValueError`.

## Legacy conversion and existing helpers

```bash
pip install 'structura-core[legacy]'
structura-convert-legacy old.schematic preserved.nbt --preserve-layout --all-entities
```

Python equivalents are `prepare_for_placement=False` and
`preserve_all_entities=True` on `convert()`. They retain selection bounds,
authored air, bedrock, connections and entity NBT with fractional positions.
Historical defaults instead trim bounds, replace bedrock, repair panes/bars,
select interior/door-clearance air, and retain paintings/item frames only.
Custom entity namespaces and translated block-entity IDs are retained.

Legacy defaults come from `structura_core.version`: Java 1.21.1. Callers can
pass another Amulet target. The optional Bedrock adapter defaults to 1.21.0;
its [translation contract](formats.md#bedrock-native-documents-and-optional-block-translation)
is separate. Native I/O needs neither translation extra.

`Structure(path, palette_index=0)` selects a view without dropping palette
variants on save. `save_structure(structure, "copy.nbt", structure.size)` keeps
existing generation helpers available:

- `additions` fill missing cells, preserving authored air; `replacements` overwrite a cell and remove its old block NBT.
- Integer additions select corresponding variants in each palette; string block states apply to every palette.
- Shifts update entity positions and known hanging-entity coordinates, preserving unrelated NBT.
- Coordinates/palette indices must be integers in the NBT range; every saved block is bounds-checked.

## Module responsibilities

`nbt.py` owns Structure validation/serialization. `litematic.py`, `schematic.py`
and `bedrock.py` adapt native documents; `bedrock_translation.py` isolates the
optional translator; `formats.py` selects readers and `convert.py` supplies the
CLI. Native readers retain IDs/properties without a second Minecraft registry.
Interactive editing belongs to `structura-edit`; existing helpers stay compatible.
For development, install this package with `pip install -e '.[legacy,bedrock]'`.
