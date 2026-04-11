# LocationData compile tool

## Purpose

Builds a **flat lookup map** from Unreal **Outer** identifiers to **world-space coordinates** (`X Y Z` as a single string) by scanning the exported map chunk JSON under `L_World/_Generated_`. This supports placing markers or linking wiki data to approximate in-world positions without loading the game.

Typical consumers: **static site generators**, **location calculators**, or any tool that needs a quick **name → coordinates** index from a dataset dump.

**Wiki / website viewer:** open [`LocationData.html`](../../LocationData.html) to search compiled coordinates and copy values for articles.

## Source inputs

| What | Path (relative to the versioned dump) |
|------|----------------------------------------|
| Root | `{datasetVersion}/json/` — must contain `RSDragonwilds/` |
| Scanned tree | `RSDragonwilds/Content/Maps/World/L_World/_Generated_/**/*.json` |

The script does **not** scan the entire `RSDragonwilds` tree—only the `_Generated_` map export folder.

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
| CLI | `python CompileLocationData.py [--output PATH]` |

## Orchestration

[`compiledata.py`](../compiledata.py) (repo `website/tools/compiledata.py`):

1. Reads [`website/data.config.json`](../../data.config.json) (`datasetVersion`, optional `datasetJsonRoot`).
2. Sets `RSDW_JSON_ROOT` and every `RSDW_*_SOURCE_DIR` (including `RSDW_LOCATION_SOURCE_DIR`) to the resolved json root.
3. Runs all compile scripts in **alphabetical order** by script name: Item → Location → Loot → NPC → Plan → Progression → Recipe → Spell → Vestige.

You can still run `CompileLocationData.py` alone; it only needs `RSDW_JSON_ROOT` / `RSDW_LOCATION_SOURCE_DIR` when overriding paths.

## Config file

[`website/data.config.json`](../../data.config.json):

- **`datasetVersion`** (required unless `datasetJsonRoot` is set): folder name such as `0.11.0.8`; combined with `{repo}/{datasetVersion}/json`.
- **`datasetJsonRoot`** (optional): explicit path to the `json` directory (or parent containing `RSDragonwilds`).

## Output

**Default file:** `LocationData.json`

**Shape:** a single JSON object whose keys are **Outer** strings and values are **three numbers as one string** (`"X Y Z"`), sorted by key.

- Built by walking each JSON file recursively, finding dict nodes that have both `Outer` and `Properties.RelativeLocation` with `X`, `Y`, `Z`.
- If the same `Outer` appears in multiple files, **last write wins**; duplicate conflicts are only noted in the console log.

There is **no** `version` / `generatedAtUtc` wrapper—unlike Loot/NPC—this output is intentionally minimal.

## Related tools

- [`LootData.md`](../LootData/LootData.md) — loot tables and resolved drops.
- [`NPCData.md`](../NPCData/NPCData.md) — NPC bundles and indexes.
