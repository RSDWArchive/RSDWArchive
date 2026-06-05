# Website Update Pipeline

This folder uses a single config pointer so the website knows which archive dataset
is current.

## Single Source Of Truth

`website/data.config.json` controls what dataset the website and compilers use.

Current keys:

- `datasetVersion`: dataset folder under repo root (example: `0.11.0.3`)
- `repoBranch`: branch used by `website/app.js` for GitHub/raw links
- Optional `datasetJsonRoot`: explicit override path to `<dataset>/json`

If `datasetJsonRoot` is set, it is used directly.
If not, `datasetVersion` is used to resolve `<repo>/<datasetVersion>/json`.

## Regular Update Flow

When a new game version arrives, run the archive-owned update command from the
repo root:

```powershell
python .\tools\UpdateArchiveData.py
```

This command:

1. Detects the installed game root, full `ProjectVersion`, and matching `.usmap`.
2. Prepares or reuses the shared Retoc cache at `E:\Github\Retoc\RSDragonwilds\<version>`.
3. Runs the RSDWArchive CUE4Parse extractor to produce `<version>/json`, `<version>/textures`, and `<version>/usmap`.
4. Writes large-file `.gitignore` entries for files over 100 MB.
5. Updates `website/data.config.json`.
6. Runs `website/updatewebsite.py` to compile website datasets and rebuild `website/file-index.json`.
7. Generates old-vs-new reports under `reports/reports/<old>_to_<version>`.
8. Moves the previous dataset folder out of the repo to `E:\Github`.
9. Writes `<version>/GitCommitPlan.json` for safe commit/push batching.
10. Writes `<version>/PipelineRun.json`.

Use the full detected game version as the dataset folder, for example `0.11.2.2`,
not a shortened `0.11.2`.

If you want to keep the previous dataset in the repo after generating reports,
pass:

```powershell
python .\tools\UpdateArchiveData.py --skip-archive-previous
```

## Website-Only Stage

`website/updatewebsite.py` is still useful when the archive files already exist and
only the compiled website data or file index needs refreshing:

```powershell
python .\website\updatewebsite.py
```

This command runs `website/tools/compiledata.py` (see that file for the
authoritative step list). It currently compiles, in order:

- `ItemData/ItemData.json`
- `LocationData/LocationData.json`
- `MapData`
- `BPData`
- `GEData`
- `LootData/LootData.json`
- `NameData/NameData.json`
- `NPCData/NPCData.json`
- `PlanData/PlanData.json`
- `ProgressionData/ProgressionData.json`
- `QuestData/QuestData.json`
- `RecipeData/RecipeData.json`
- `SpellData/SpellData.json`
- `VestigeData/VestigeData.json`
- `IconData`
- `LocationMap`

It then rebuilds `website/file-index.json` from the configured dataset root.

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

Dataset HTML pages load compiled JSON under `website/tools/...` (each file embeds
its own `version` from the compiler). They do not need a separate
`updatewebsite.py` change when compiler logic changes; only when you add a new
compile step to `compiledata.py` should you document it here and in
`compiledata.py`'s `main()` list.

## Scope Note

`website/updatewebsite.py` is the website data compile/index stage.
Pywikibot wiki generation is a separate pipeline in:

- `website/tools/Pywikibot/run_generation_pipeline.py`
