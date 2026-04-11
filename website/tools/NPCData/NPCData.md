# NPCData compile tool

## Purpose

Builds a **single normalized catalog of NPCs** by joining:

- AI **Data** blueprints (`BP_AI_*_Data`)
- AI **Character** blueprints (`BP_AI_*_Character`)
- **String tables** for display names (`ST_AI_Names*`)
- **Journal** entries that unlock fauna (`JOURNAL_World_Fauna*`)
- **Spawn points** (`BP_SpawnPoint_*`)
- **AI data** and **spawn** DataTables (`DT_AIData*`, `DT_AISpawnData*`)

Output is suitable for **bestiaries**, **stat tools**, and **spawn/location** views.

**Wiki / website viewer:** open [`NPCData.html`](../../NPCData.html) for NPC stats, loot row names (join to LootData), and difficulty tabs.

## Source inputs

All paths are resolved under the same json root as other compilers (`RSDragonwilds`).

| Glob / pattern | Role |
|----------------|------|
| `BP_AI_*_Data.json` | Per-NPC data asset (health metadata, loot row names, etc.). |
| `BP_AI_*_Character.json` | Character blueprint; links to data asset. |
| `ST_AI_Names*.json` | Localized AI names. |
| `JOURNAL_World_Fauna*.json` | Descriptions and unlock wiring to AI data blueprints (fauna / bestiary scope; not all `JOURNAL_*` assets). |
| `BP_SpawnPoint_*.json` | World spawn annotations. |
| `DT_AIData*.json` | Table rows (e.g. health) keyed by row name. |
| `DT_AISpawnData*.json` | Spawn table rows referencing character blueprints. |

### Auto-discovery

Highest semver `*/json` under the repo containing `RSDragonwilds`, unless overridden.

### Environment variables

| Variable | Role |
|----------|------|
| `RSDW_JSON_ROOT` | Optional json root. |
| `RSDW_NPC_SOURCE_DIR` | Optional; same resolution as json root. |

## Script and CLI

| Item | Value |
|------|--------|
| Script | [`CompileNPCData.py`](CompileNPCData.py) |
| Default output | `NPCData.json` in this folder |
| CLI | `python CompileNPCData.py [--output PATH]` |

## Orchestration

[`compiledata.py`](../compiledata.py) sets `RSDW_JSON_ROOT` and all per-category source env vars (including `RSDW_NPC_SOURCE_DIR`), then runs the full pipeline (see [LocationData.md](../LocationData/LocationData.md) § Orchestration). `CompileNPCData.py` runs after Item, Location, and Loot.

## Config file

[`website/data.config.json`](../../data.config.json): `datasetVersion`, optional `datasetJsonRoot`.

## Output

**Default file:** `NPCData.json`

**Top-level keys (summary):**

| Key | Meaning |
|-----|---------|
| `version` | Dataset version label when inferable. |
| `generatedAtUtc` | Compile time (UTC ISO). |
| `sourceRoot` | Resolved json/RSDragonwilds root. |
| `counts` | File counts per source type and final NPC count. |
| `npcs` | Map of **npc id** → compact record (classification, combat, loot, journal, spawning, …). |
| `indexes` | e.g. `byDifficultyTag`, `byEnemyLootRowName`. |
| `issues` | `parseErrors`, `stringTableCollisions`, `missingLinks` (e.g. character→data). |

Duplicate logical ids may be expanded with suffixes (`baseId`, variant slug); see script logs.

## Joining NPCData to LootData

NPC entries carry **loot references**; **`LootData.json`** carries **resolved drops** (items, chances, table chains). Join in the website or tooling layer:

| NPCData field | Use |
|---------------|-----|
| `enemyLootRowName` | Lookup key for `LootData.enemies` (same row name when that enemy appears in the loot compile). |
| `enemyLootTable` | Hints which composite / enemy table the game used (useful when the same row name exists in multiple pipelines). |

Full drop lists are intentionally **not** inlined into `NPCData.json`; see [`LootData.md`](../LootData/LootData.md) and [`DATA_ENRICHMENT.md`](../DATA_ENRICHMENT.md) § NPCData checklist.

## Related tools

- [`LootData.md`](../LootData/LootData.md) — detailed drop resolution from loot tables.
- [`LocationData.md`](../LocationData/LocationData.md) — world coordinates from map exports.
- [`DATA_ENRICHMENT.md`](../DATA_ENRICHMENT.md) — enrichment methodology and journal scope notes.
