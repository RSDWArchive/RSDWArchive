# Website Update Pipeline

This folder uses a single config pointer so version updates are simple.

## Single Source Of Truth

`website/data.config.json` controls what dataset the website and compilers use.

Current keys:

- `datasetVersion`: dataset folder under repo root (example: `0.11.0.3`)
- `repoBranch`: branch used by `website/app.js` for GitHub/raw links
- Optional `datasetJsonRoot`: explicit override path to `<dataset>/json`

If `datasetJsonRoot` is set, it is used directly.  
If not, `datasetVersion` is used to resolve `<repo>/<datasetVersion>/json`.

## Regular Update Flow

When a new game version arrives:

1. Add the new dataset folder at repo root (example: `0.12.0.0`).
2. Update `website/data.config.json`:
   - set `datasetVersion` to the new folder.
3. Run:

```powershell
python .\website\updatewebsite.py
```

This command:

1. Runs `website/tools/compiledata.py` (see that file for the authoritative step list). It compiles, in order:
   - `ItemData/ItemData.json`
   - `LocationData/LocationData.json`
   - `LootData/LootData.json`
   - `NameData/NameData.json`
   - `NPCData/NPCData.json`
   - `PlanData/PlanData.json`
   - `ProgressionData/ProgressionData.json`
   - `RecipeData/RecipeData.json`
   - `SpellData/SpellData.json`
   - `VestigeData/VestigeData.json`
2. Rebuilds `website/file-index.json` from the configured dataset root (all files under that version folder).

## Quick Commands

Compile only data files:

```powershell
python .\website\tools\compiledata.py
```

Skip compile and only rebuild file index:

```powershell
python .\website\updatewebsite.py --skip-compile-data
```

Skip file-index and only compile data:

```powershell
python .\website\updatewebsite.py --skip-file-index
```

## What Reads `data.config.json`

- **`website/app.js`** (main file index): `datasetVersion`, `repoBranch`
- **`website/locationdata.js`**: `datasetVersion` (map tiles / folder label)

Dataset HTML pages load compiled JSON under `website/tools/…` (each file embeds its own `version` from the compiler). They do not need a separate `updatewebsite.py` change when compiler logic changes—only when you add a new compile step to `compiledata.py` (then document it here and in `compiledata.py`’s `main()` list).

## Scope Note

`website/updatewebsite.py` is the website data pipeline.  
Pywikibot wiki generation is a separate pipeline in:

- `website/tools/Pywikibot/run_generation_pipeline.py`

