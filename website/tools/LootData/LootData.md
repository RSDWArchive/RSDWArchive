# LootData compile tool

## Purpose

Normalizes **enemy loot**, **loot drop tables**, **chest respawn profiles**, **chest prefabs**, and **item sets** from named DataTable exports into one JSON file. It **resolves** table references (enemy → drop table → resources) where possible and enriches item ids with **display names** from the item string table when available.

Typical consumers: **drop calculators**, **wiki loot pages**, and **cross-indexes** (which enemies or chest profiles reference an item).

**Wiki / website viewer:** open [`LootData.html`](../../LootData.html) for enemy/chest/item tabs, resolved drops, and JSON copy.

## Source inputs

| What | How it is found |
|------|-----------------|
| Root | Resolved to `{datasetVersion}/json` (or env override) with `RSDragonwilds` inside. |
| Loot tables | Fixed set of **filenames** (see below), located anywhere under the json tree via `rglob`, with **scoring** to prefer the intended path (e.g. base game vs `DowdunReach`). |
| Item display names | First `ST_ItemNames.json` found under the same tree. |

### Table filenames (hard-coded)

- `DT_CompositeEnemyLootDropTable`, `DT_EnemyLootDropTable`, `DT_LootDropTable`
- `DT_LootChest_RespawnProfiles`, `DT_LootChests_Prefabs`, `DT_LootChest_Sets`
- DowdunReach variants: `DT_*_DowdunReach` for composite, enemy, and general loot tables.

### Auto-discovery

Same semver `*/json` discovery as other compile scripts when env vars are not set.

### Environment variables

| Variable | Role |
|----------|------|
| `RSDW_JSON_ROOT` | Optional. Points at `{version}/json` or `{version}/json/RSDragonwilds`. |
| `RSDW_LOOT_SOURCE_DIR` | Optional; same semantics as json root for loot resolution. |

## Script and CLI

| Item | Value |
|------|--------|
| Script | [`CompileLootData.py`](CompileLootData.py) |
| Default output | `LootData.json` in this folder |
| CLI | `python CompileLootData.py [--output PATH]` |

## Orchestration

[`compiledata.py`](../compiledata.py) sets `RSDW_JSON_ROOT` and all per-category source env vars (including `RSDW_LOOT_SOURCE_DIR`), then runs the full pipeline (see [LocationData.md](../LocationData/LocationData.md) § Orchestration). `CompileLootData.py` runs after Item and Location, before NPC.

## Config file

See [`website/data.config.json`](../../data.config.json): `datasetVersion` and optional `datasetJsonRoot`.

## Output

**Default file:** `LootData.json`

**Top-level keys (summary):**

| Key | Meaning |
|-----|---------|
| `version` | Derived from parent folder of the resolved source root (e.g. `0.11.0.8`) or `unknown`. |
| `generatedAtUtc` | ISO timestamp when the compile ran. |
| `sourceRoot` | Absolute path to the directory used as the json/RSDragonwilds root. |
| `tables` | Metadata per loaded DataTable (file path, row count, type). |
| `enemies` | Per enemy row: resolved `drops`, `sources` (table chain), power tiers. |
| `chests` | Per respawn profile: prefab ref, guaranteed/additional sets, **resolvedItems**. |
| `itemSets` | Rows from `DT_LootChest_Sets` expanded with item ids and display names. |
| `indexes` | `itemToEnemies`, `itemToChestProfiles`. |
| `issues` | `missingFiles`, `parseErrors`, `missingReferences` (broken table/row links). |

## Related tools

- [`LocationData.md`](../LocationData/LocationData.md) — map `_Generated_` coordinates.
- [`NPCData.md`](../NPCData/NPCData.md) — NPC stats; loot cross-links can complement this data.
