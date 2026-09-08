# Migration to core 0.6.1 and geo 0.1.0

Core 0.6.1 owns structure data, validation, file formats, world reading and
conversion. Geo 0.1.0 owns geometric analysis and preparation. Install the two
packages together when you use analysis:

```bash
python -m pip install --upgrade 'structura-core==0.6.1' 'structura-geo==0.1.0'
```

Geo is released separately; until its publication, use its local checkout or
built wheel. Geo requires `structura-core>=0.6.1,<0.7`, so an older core cannot
satisfy its dependency. Core never depends on geo or SciPy. Render 0.8.1 requires
the same core range and works without geo.

## Imports and commands that change

This release changes analysis import paths and legacy preparation defaults.
Existing consumers of those features must migrate explicitly even though the
Structure and format API remains in the 0.6 series.

| Before | After |
|---|---|
| `structura_core.analyze.StructureAnalyzer` | `structura_geo.analyze.StructureAnalyzer` |
| `structura_core.voxel`, `components`, `largest_component` | Corresponding `structura_geo` modules |
| `structura_core.aesthetics`, `materials` | Corresponding `structura_geo` modules |
| `structura_core.analysis_geometry`, `analysis_report`, `analysis_cli` | Corresponding `structura_geo` modules |
| `structura_core.check_doors`, `check_leaks`, `legacy_cleanup` | Corresponding `structura_geo` modules |
| `structura_core.convert_legacy.convert(..., prepare_for_placement=True)` | `structura_geo.convert_legacy.convert(...)` |
| Legacy conversion with implicit placement preparation | `structura-prepare-legacy input.schematic output.nbt` |

`structura-analyze`, `structura-check-doors` and `structura-check-leaks` retain
their command names and arguments. Geo now installs them. `python -m` calls use
the new module prefix.

`structura-convert-legacy` preserves selection bounds, authored air, materials
and connections. Its entity filter remains unchanged: `--all-entities` /
`preserve_all_entities=True` retains every source entity. `--preserve-layout`
remains accepted. Requesting placement preparation in core raises an actionable
error before opening the input or modifying the output. Geo's `legacy` extra
installs the translation engine needed by `structura-prepare-legacy`.

## APIs that remain compatible

`Structure`, `load_structure`, `convert_structure`, native document classes and
writers retain their existing import paths. Helpers from `structura_core.nbt`
continue to work. `save_structure` returns the number of written block records.
Core's data API remains compatible with the current render and edit consumers;
their `>=0.6,<0.7` dependency ranges accept this version.

The legacy converter preserves JSON sign components and their formatting.
Existing nonempty translated sign messages are retained, including components
represented as strings, lists, translated keys or nested text.

## Release order

Build and verify core 0.6.1 first. Publish that version before geo 0.1.0, whose
minimum core requirement is intentional. Geo verification checks its installed
wheel against that core release. No compatibility shim imports geo from core.
