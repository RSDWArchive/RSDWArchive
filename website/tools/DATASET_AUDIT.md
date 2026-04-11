# Dataset audit checklist

Repeatable summary checks for compiled `*Data.json` outputs. Wiki editors rely on these files for [RuneScape: Dragonwilds Wiki](https://dragonwilds.runescape.wiki/)-style fact-checking; running audits after changing compile scripts or game exports catches regressions early.

## Command

From the **repository root**:

```bash
python website/tools/audit_datasets.py
```

Optional:

```bash
python website/tools/audit_datasets.py --repo /path/to/RSDWArchive
```

## What the script reports

| Dataset | Highlights |
|---------|------------|
| **ItemData** | Entry count; % with `enrichment.displayName`, `flavourText`, `skillUsed`; random samples |
| **NameData** | String table file count; `counts.totalKeys`; parse errors; atypical exports |
| **RecipeData** | Entry count; `enrichmentMisses` length; `recipesByItemId` key count |
| **SpellData** | Entries with costs / gameplay effects; `UtilitySpellData` primary rows; enrichment misses |
| **PlanData** | Building summaries with stability profile; plan building issues |
| **ProgressionData** | Table count; enrichment misses (nested `resolvedDisplayName` scan is heuristic) |
| **VestigeData** | Unresolved `recipesToUnlock` slots |
| **LootData** | Enemy/chest counts; `missingReferences` |
| **NPCData** | NPC count; `missingLinks`; sample join check vs `LootData.enemies` keys |
| **LocationData** | Key count (very large); structure note |

## Manual spot-checks (not automated)

- **Residual issues:** If `LootData.issues.missingReferences` or `NPCData.issues.missingLinks` is non-empty, spot-check one entry: often a **missing set row** or **orphan character→data** link in the export, not a compiler bug. See [`DATA_ENRICHMENT.md`](DATA_ENRICHMENT.md) (“Known small residual issues”).
- **NPC ↔ Loot:** Pick 5 `enemyLootRowName` values from `NPCData.json` and confirm they exist under `LootData.json` → `enemies` (or document regional table differences).
- **Recipe reverse index:** Pick an item id from `RecipeData.json` → `indexes.recipesByItemId` and confirm listed paths appear under `entries`.
- **Progression:** Open one row with `UnlockQueryString` and confirm `resolvedDisplayName` matches expectations.

## When to run

- After bumping `datasetVersion` in [`website/data.config.json`](../data.config.json).
- After edits to [`compiledata.py`](compiledata.py) or any `Compile*Data.py`.
- Before publishing static site updates that depend on compiled JSON.

## Related docs

- [`DATA_ENRICHMENT.md`](DATA_ENRICHMENT.md) — join methodology and enrichment fields.
- Per-tool `*.md` under each `*Data/` folder — compile inputs and output shape.
