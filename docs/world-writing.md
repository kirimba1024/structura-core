# Editing saved Java worlds

Install `structura-core[world]`. `JavaWorld.read_region` remains read-only and
bounded. `world_write.save_world_patch(path, patch)` is the explicit write API
for existing Java 1.18+ chunks and sections. It does not generate terrain.

```python
from structura_core.world_write import save_world_patch

backup = save_world_patch("/path/to/world", {
    ("minecraft:overworld", 12, 64, -3): (
        ("minecraft:stone", None),
        ("minecraft:gold_block", None),
    ),
})
```

Keys are dimension IDs and absolute integer XYZ coordinates. Values are pairs
of `(blockstate, block_entity_snbt_or_none)`, before and after. NBT coordinates
are ignored for comparison and replaced with the destination coordinates when
writing. Ordinary entities, biomes and unrelated chunk NBT are retained.

The optional `entities=` argument accepts `world_entity_write.EntityPatch` records.
Each contains a before/after SNBT payload and `world_entities.EntityLocation`
(dimension, storage, chunk or player file). Payload positions use world coordinates.
`WorldRegion.entity_locations` corresponds to the loaded structure's entity list.
Changing a payload updates the existing entity; changing the destination chunk moves
it. A missing before payload creates an entity, and a missing after payload deletes it.
Destinations must contain terrain chunks. UUIDs and original payloads are checked
against fresh disk data; already-applied changes are accepted, conflicts abort Save.
Entities without UUIDs are matched by their full original payload.

Player records retain their original `level.dat` or `playerdata` storage. They can be
edited, including inventories, but cannot be created or deleted through this API.
Editing the local player also updates a matching playerdata profile when its baseline
agrees. Unknown mod fields remain intact. Player files and entity regions use the same
staging, read-back validation, hash checks and backups as block changes.

`world_patch` groups changes by section, decodes each palette once and updates
only requested cells. `world_staging` uses Amulet's AnvilRegionInterface to
write copied region files and reads staged chunks back for verification.
The original values must match disk, or disk must already contain the requested
result. A conflict aborts preparation before any original region is replaced.
Invalid height/light caches and affected POI sections are marked for rebuilding
by Minecraft; pending ticks at replaced positions are removed.

Before installation, original files and `manifest.json` are stored under
`.structura/backups/<save-id>`. The manifest lists prior hashes and installed
paths. External `.mcc` files are included. File hashes are rechecked before
replacement; an I/O error reports the backup path. Backups have no automatic
retention policy. The return value is the backup directory, or `None` when the
requested state is already on disk.
In the manifest, a null original hash marks a file that did not exist before
the save; restoring that entry means removing the newly created file.

The `.structura/write.lock` serializes Structura saves. It does not lock the
game's `session.lock`. Hash checks detect changes observed during preparation,
but do not eliminate the final race with Minecraft or another writer. Replacement
is atomic per file, not across a world. Recovery remains manual after a partial
installation; keep the pending patch until the entire call succeeds.

A local macOS microbenchmark of 32,768 replacements (stone to an oak-stair state,
eight 16³ sections) took 0.53 s before caching repeated state parsing and 0.14 s
afterwards. This measures chunk preparation only, excluding region copies and
disk installation; it is not a world-save throughput claim.
