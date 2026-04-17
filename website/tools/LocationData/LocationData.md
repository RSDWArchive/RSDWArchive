# LocationData compile tool

## Purpose

Builds a **flat lookup map** from Unreal **Outer** identifiers to **world-space coordinates** (`X Y Z` as a single string) by scanning the exported map chunk JSON under `L_World/_Generated_` and the main `L_World.json` package. Output is the single file consumed by the wiki viewer — no intermediate artifacts, no secondary scripts.

Typical consumers: **static site generators**, **location calculators**, or any tool that needs a quick **name → coordinates** index from a dataset dump.

**Wiki / website viewer:** open [`LocationData.html`](../../LocationData.html) to search compiled coordinates and copy values for articles. [`website/locationdata.js`](../../locationdata.js) fetches `LocationData.json` as the single source of truth.

## Source inputs

| What | Path (relative to the versioned dump) |
|------|----------------------------------------|
| Root | `{datasetVersion}/json/` — must contain `RSDragonwilds/` |
| Scanned tree | `RSDragonwilds/Content/Maps/World/L_World/_Generated_/**/*.json` (WorldPartition cell shards) |
| Main package | `RSDragonwilds/Content/Maps/World/L_World.json` (always-loaded actors + spatial hash) |

The script scans **both** WorldPartition sources. The `_Generated_` shards hold streamed cell actors; the sibling `L_World.json` holds "always loaded" actors (`WP_IsAlwaysLoaded`, root PCG spawners, etc.) plus the `WorldPartitionRuntimeCellDataSpatialHash` index used by the PCG phase. Missing the main package previously caused spawners living outside runtime cells — notably some `BP_Spawner_Pumpkin_*_C` instances placed via `BP_PCG_TileSpawner_C` — to drop out of the index.

### Auto-discovery

If environment overrides are unset, the script picks the **highest semver** folder matching `*/json` under the repo (e.g. `0.11.0.8/json`) that contains `RSDragonwilds`.

### Environment variables

| Variable | Role |
|----------|------|
| `RSDW_JSON_ROOT` | Optional. Points at `{version}/json` or at `{version}/json/RSDragonwilds` (both layouts are accepted). |
| `RSDW_LOCATION_SOURCE_DIR` | Optional override; same resolution rules as `RSDW_JSON_ROOT`, then the script appends `.../Maps/World/L_World/_Generated_`. |

## Script and CLI

| Item | Value |
|------|--------|
| Script | [`CompileLocationData.py`](CompileLocationData.py) |
| Default output | `LocationData.json` in this folder |
| CLI | `python CompileLocationData.py [--output PATH] [--l-world PATH] [--no-l-world] [--debug]` |

A normal run produces exactly one file: `LocationData.json`. Pass `--debug` if you want the PCG debug sidecars described below.

## Orchestration

[`compiledata.py`](../compiledata.py) (repo `website/tools/compiledata.py`):

1. Reads [`website/data.config.json`](../../data.config.json) (`datasetVersion`, optional `datasetJsonRoot`).
2. Sets `RSDW_JSON_ROOT` and every `RSDW_*_SOURCE_DIR` (including `RSDW_LOCATION_SOURCE_DIR`) to the resolved json root.
3. Runs compile scripts in order: Item → **Location** → **MapData** → Loot → Name → NPC → Plan → Progression → Recipe → Spell → Vestige → Icon.

You can also run `CompileLocationData.py` alone; it only needs `RSDW_JSON_ROOT` / `RSDW_LOCATION_SOURCE_DIR` when overriding paths.

The chunk-overlay GeoJSON files used by [`website/Map.html`](../../Map.html) are **not** produced here — see [`website/tools/MapData/MapData.md`](../MapData/MapData.md).

## Config file

[`website/data.config.json`](../../data.config.json):

- **`datasetVersion`** (required unless `datasetJsonRoot` is set): folder name such as `0.11.0.8`; combined with `{repo}/{datasetVersion}/json`.
- **`datasetJsonRoot`** (optional): explicit path to the `json` directory (or parent containing `RSDragonwilds`).

## Output

**Primary file:** `LocationData.json`.

**Shape:** a single JSON object whose keys are location identifiers and values are **three numbers as one string** (`"X Y Z"`), sorted by key.

The pipeline runs three internal phases inside a single script:

1. **Chunk phase.** Walks each `_Generated_` JSON **and** the main `L_World.json` recursively, finding dict nodes with `Outer` and `Properties.RelativeLocation` (`X`, `Y`, `Z`). Keys are normalized Outer strings (Anima vents get an element suffix so paired actors don't collide). If the same key appears in multiple files, **last write wins**; duplicates are only noted in the console log.
2. **PCG foliage phase.** Rescans the same files for `BP_InteractableFoliageISMC_*` components and resolves world space per instance. Keys look like `BP_Spawner_…_C::BP_PCG_TileSpawner_…/SM_Branches_02_4` so they do not collide with Outer keys. On collision with the chunk phase the chunk value wins. Per-instance rows (`…#inst0`, …) are emitted from `PerInstanceSMData` when available; root is `RootComponent0` for `InstancedFoliageActor_*` and the `Box` component for `BP_PCG_TileSpawner_C`.
3. **Wiki-bounds filter.** Drops out-of-bounds coordinates (X `0..302400`, Y `-100800..201600`, Z sanity band), bad XYZ strings, PCG aggregate rows shadowed by per-instance siblings, and any `BP_InteractableFoliageISMC_*` aggregate row that also has `#instN` siblings. The filtered result is the only thing written to `LocationData.json`.

The wiki X/Y bounds must stay in sync with [`website/map.js`](../../map.js) and [`website/locationdata.js`](../../locationdata.js) (Leaflet `maxBounds`).

**Debug sidecars (opt-in, `--debug`):**

- `PCGLocationData.json` — PCG-only flat map in the same shape as `LocationData.json`.
- `PCGLocationDataReport.json` — per-entry metadata (candidates, source chunk, position method) plus merge/filter stats.

Neither sidecar is checked in and neither is consumed by the website; they exist purely for diffing future dataset exports.

## Related tools

- [`MapData.md`](../MapData/MapData.md) — WorldPartition chunk-boundary overlays for `Map.html`.
- [`LootData.md`](../LootData/LootData.md) — loot tables and resolved drops.
- [`NPCData.md`](../NPCData/NPCData.md) — NPC bundles and indexes.
