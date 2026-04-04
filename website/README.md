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

1. runs `website/tools/compiledata.py`
2. compiles:
   - `website/tools/LocationData/LocationData.json`
   - `website/tools/LootData/LootData.json`
   - `website/tools/NPCData/NPCData.json`
3. rebuilds `website/file-index.json` from the configured dataset root

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

## What Is Dynamic Now

- `website/app.js` reads `data.config.json` for:
  - `datasetVersion`
  - `repoBranch`
- `website/locationdata.js` reads `data.config.json` for:
  - `datasetVersion`

`website/lootdata.js` currently reads `LootData.json` directly and does not show version label text from config yet.

## Scope Note

`website/updatewebsite.py` is the website data pipeline.  
Pywikibot wiki generation is a separate pipeline in:

- `website/tools/Pywikibot/run_generation_pipeline.py`

