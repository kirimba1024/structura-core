# Changelog

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
