# MapData compile tool

## Purpose

Produces the **WorldPartition chunk-boundary GeoJSON overlays** displayed on [`website/Map.html`](../../Map.html). This tool is only concerned with the chunk grid — per-actor coordinates live in [`LocationData`](../LocationData/LocationData.md).

[`website/map.js`](../../map.js) fetches the GeoJSON files directly from this folder as Leaflet layers; there is no intermediate JSON sidecar.

## Source input

| What | Path (relative to the versioned dump) |
|------|----------------------------------------|
| Main package | `RSDragonwilds/Content/Maps/World/L_World.json` |

Only `L_World.json` is needed — specifically the `WorldPartitionRuntimeCellDataSpatialHash` records, which hold per-chunk `ContentBounds`, `position`, `Extent`, and `GridName`.

### Auto-discovery

Same rules as `LocationData`:

| Variable | Role |
|----------|------|
| `RSDW_JSON_ROOT` | Optional. Points at `{version}/json` or `{version}/json/RSDragonwilds`. |
| `RSDW_LOCATION_SOURCE_DIR` | Optional override; resolved the same way and then walked down to `…/L_World/_Generated_`, whose parent is used to locate `L_World.json`. |

If neither is set, the highest semver folder matching `*/json` under the repo is used.

## Script and CLI

| Item | Value |
|------|--------|
| Script | [`CompileMapData.py`](CompileMapData.py) |
| Default outputs | `ChunkWorldMapBounds_ContentBounds.geojson`, `ChunkWorldMapBounds_GridCell.geojson` in this folder |
| CLI | `python CompileMapData.py [--l-world PATH] [--out-dir DIR]` |

## Outputs

Both files are standard GeoJSON `FeatureCollection`s; each feature is a polygon in XY game-space with `properties.id` (chunk stem) and `properties.gridName`.

- **`ChunkWorldMapBounds_ContentBounds.geojson`** — per-chunk actor AABB, built from `ContentBounds.Min` / `ContentBounds.Max`. Reflects where actors actually live in each cell.
- **`ChunkWorldMapBounds_GridCell.geojson`** — per-chunk nominal tile (`position ± Extent`). Reflects the nominal WorldPartition grid.

`Map.html` lets the user toggle between the two layers; the default is **Grid cells**.

## Orchestration

This runs as a standard step in [`website/tools/compiledata.py`](../compiledata.py), right after `LocationData`:

1. Reads [`website/data.config.json`](../../data.config.json) (`datasetVersion`, optional `datasetJsonRoot`).
2. Sets `RSDW_JSON_ROOT` / `RSDW_*_SOURCE_DIR` to the resolved json root.
3. Invokes `CompileMapData.py`, which auto-discovers `L_World.json` from those env vars.

Run standalone whenever the WorldPartition layout changes (new dataset version, chunk grid edits, etc.):

```
python website/tools/MapData/CompileMapData.py
```

## Related tools

- [`LocationData.md`](../LocationData/LocationData.md) — the master `LocationData.json` consumed by `LocationData.html` and the map marker layer.
