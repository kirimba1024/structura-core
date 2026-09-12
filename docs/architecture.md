# Core architecture

Core owns structure data and format conversion. Numerical analysis belongs to
[structura-geo](https://github.com/kirimba1024/structura-geo). It has no
dependency on the renderer or editor. Optional translation engines are loaded
only by the corresponding conversion paths.

## Structure data and I/O

| Module | Responsibility |
|---|---|
| `nbt_io` | Bounded NBT/SNBT reading, compression, encoding and atomic file replacement. It has no knowledge of the Structure document schema. |
| `blockstates` | State syntax, canonical keys, palette validation and property-preserving material replacement. |
| `validation` | Checked 32-bit integers, finite coordinate vectors and NBT container types. No document or I/O dependency. |
| `structure` | `Structure`, palette variants, block records and document invariants. |
| `block_array` | MutableMapping-compatible int32 block storage with numerical validation, counts and region copies; -1 denotes an absent record. |
| `structure_writer` | Build an owned output document: reconcile palettes, apply additions/replacements, shift records and preserve metadata. |
| `entity_positions` | Copy and place block-entity coordinates; shift entity positions and hanging anchors without changing unrelated payload fields. |
| `nbt` | Re-export the established import paths for callers. |
| `schematic`, `litematic`, `bedrock` | Read and validate their own document formats and translate them to the shared structure representation. |
| `formats`, `convert` | Select the appropriate format operation and report conversion losses. |

`structure` depends on `nbt_io`; `structure_writer` depends on both. The
compatibility module imports these implementations. New internal code should
import the implementation that owns an operation, keeping this direction intact.

Format readers use `blockstates` and `validation` directly; they do not obtain
general validators through another document reader. Existing state helpers
remain importable from `structura_core`, `nbt` and `structure`.

The writer creates copies of palettes and records. It validates changes before
writing the destination, preserves authored air and unknown metadata, and keeps
integer palette references distinct from literal state strings. Entity placement
and the corresponding inner NBT coordinates move together. A shifted block
entity uses its block's output coordinates, including when the caller has already
rebased the payload. Entity hanging anchors retain their offset from `blockPos`.
Saving without a shift preserves existing payload coordinates. `save_structure`
remains available through both `structura_core` and `structura_core.nbt`.
It returns the number of written block records.

## Legacy conversion

`legacy_blocks` owns Amulet source lifetime, block translation and output records.
`legacy_entities` normalizes entity records and restores sign text.
`convert_legacy` coordinates reading, translation and writing.

Conversion preserves selection bounds, authored air, materials and connections.
`preserve_all_entities=True` retains every source entity; the existing default
retains paintings and item frames. `--preserve-layout` remains a compatible no-op.
Requesting `prepare_for_placement=True` points callers to
`structura_geo.convert_legacy.convert`; core performs no geometric cleanup.

## Java world reading

| Module | Responsibility |
|---|---|
| `world` | World metadata, dimensions, region selection and read orchestration. |
| `world_io` | Read Anvil chunk locations and internal/external chunk payloads. |
| `world_chunks` | Decode section states, merge palettes and localize block entities. No file I/O. |
| `world_terrain` | Inventory actual Anvil chunk locations and stream decoded sections for an immutable terrain snapshot. No render or GUI dependency. |
| `world_entities` | Player discovery, entity filtering/deduplication, local records and storage locations. |
| `world_entity_write` | Compare and stage entity/player changes, preserving unknown NBT and original storage. |
| `world_write`, `world_staging` | Explicit block/entity save orchestration, staged regions/files, conflict checks and backups. |

`world.read_chunk`, `JavaWorld` and `WorldRegion` retain their import paths.
`world_terrain.existing_chunks(regions=...)` limits inventory to requested region
coordinates, reading only their headers. Omit the filter to inventory a whole dimension.
`JavaWorld.read_region(vertical_radius=None)` reads the full height of actual saved
sections in the requested columns. Explicit finite radii remain supported; missing
sections are not generated. The editor defaults to this full-height mode.
Amulet remains optional and is loaded at the world-reading boundary. The decoder
is passed explicitly into section processing. Selection parameters are validated
before reading chunks. Duplicate sections and block entities are rejected rather
than silently overwriting previously read data. Entity `pos`, inner `Pos` and
hanging anchors are expressed in local coordinates; `source_origin` maps the
region back to the world. Reading does not write to the world directory.

## Checks

Format and preservation tests protect palettes, metadata, entity placement,
legacy layout and conversion failures. World tests cover modern/older section
layouts, negative coordinates, external chunks, entities and malformed input.
Public API type checks run against a built wheel in CI. Geometry tests and the
analysis benchmark live in structura-geo.

Verified backup restore works in the base install and declares its `portalocker`
dependency there. Manifest and player-storage paths use forward slashes on every
platform. Backup files are opened for writing before fsync, as required on Windows;
directory synchronization remains specific to POSIX.

## Преобразования и запись мира: 11 сентября

`grid_transform.py` представляет 48 подписанных перестановок осей: композиция, обратная матрица, координаты ячеек и непрерывные позиции. `block_transform.py` применяет их к свойствам с учётом допустимых значений; непредставимая ориентация отклоняется. `entity_grid_transform.py` сохраняет неизвестный NBT и преобразует позиции, движение, направление взгляда и hanging anchors. GUI-зависимостей нет. Точные циклы clipboard организует edit, сохраняя оригинал.

`StagedWorld` переиспользует AnvilRegionInterface в пределах одной записи. Чанки читаются свежими, патч сохраняет незатронутые данные; тест параллельного внешнего изменения проверяет это. NumPy-массивы координат при чтении преобразуются пакетно. Полная проверка инвариантов Structure сохраняется, обычные целочисленные tuple-позиции имеют быстрый путь.
