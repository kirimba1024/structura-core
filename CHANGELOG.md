# Changelog

## 0.6.0

- Add bounded SNBT I/O through the existing conversion API.
- Read and copy Sponge v1 natively; normalization requires an explicit source DataVersion.
- Preserve native Bedrock mcstructure documents and add optional, diagnosed Java/Bedrock block translation.

## 0.5.0

- Add typed `convert_structure(source, output, ...)`, used by the native CLI.
  Keep native document copies lossless and retain existing conversion functions.
- Report source-specific conversion losses with `ConversionWarning`; optional
  `strict=True` / `--strict` rejects them before writing.
- Bound input and decompressed NBT to 256 MiB by default, with an explicit
  `max_nbt_bytes` override. Normalize malformed/truncated reads to `ValueError`.
- Ship public type information and check a consumer against the installed wheel.
  Add package documentation, issue and changelog links.

## 0.4.0

- Read Sponge Schematic v2/v3 directly without Amulet Core. Preserve native
  document fields on save; normalize local blocks/entities with explicit
  limits for cross-format conversion, offsets and biomes.
- Add `Schematic` and `.schem` input to `load_structure` / `structura-convert`.
  Validate VarInts, unsigned dimensions, sparse palette indices and entities.
- Share cell limits across native formats and include independent Amulet
  block fixtures for both Sponge versions in the source distribution.

## 0.3.0

- Read Litematic v5–v7 natively, including signed region sizes, palettes crossing
  packed-word boundaries, tile entities and fractional entity positions.
- Add `Litematic`, `load_structure`, `export_litematic` and `structura-convert`.
  Native Litematic copies retain metadata/ticks; cross-format conversion has
  explicit documented limits. Overlaps require a named region choice.
- Add `Structure.from_root` and `Structure.from_bytes` using existing validation.
  Caller-owned compounds are copied. Existing Structure APIs remain available.
- Keep the Minecraft data version unchanged; validate sizes, palette indices,
  entity IDs and configurable allocation limits before export.
- Use reproducible, atomic Litematic writes and include an independently
  generated Litemapy interoperability fixture in the source distribution.

## 0.2.3

- Preserve alternative palettes, unknown root/block fields and entity payloads
  when saving Structure NBT. Additions retain authored air; replacements remain
  the explicit way to overwrite a cell and its block NBT.
- Reject fractional coordinates, malformed records and signed-integer overflow;
  keep existing output files intact when validation or publication fails.
- Export Sponge v2 with a named `Schematic` root, standard block entity fields,
  entities, correct VarInt ordering and unsigned-short dimensions. Export no
  longer requires the `legacy` extra. Omitted cells become air, and the selected
  Structure palette is used.
- Add `prepare_for_placement=False` / `--preserve-layout` and `--all-entities`
  for conversion that retains bounds, air, authored materials and connections.
  The historical placement cleanup remains the converter's default.
- Preserve custom entity namespaces, restore Amulet logging after conversion,
  and include translated block entity IDs so converted files can be exported.
- Test installed wheels before publishing and check the release tag/version.

Sponge export does not translate entity/block versions. Its payloads retain the
source `DataVersion`. Missing entity IDs fail explicitly; files produced by an
older converter without block entity IDs can be regenerated with this version.
