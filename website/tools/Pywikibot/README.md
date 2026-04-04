# Pywikibot (Dev Wiki Automation)

This folder is the wiki automation workspace for Dragonwilds dev wiki publishing:
- https://en_rsdwwiki.dev.weirdgloop.org/

## Folder Layout

- Root:
  - `README.md`
  - `run_generation_pipeline.py` (master runner)
- `scripts/`:
  - `build_item_catalog.py`
  - `generate_item_pages.py`
  - `generate_armour_pages.py`
  - `generate_loot_enemy_pages.py`
  - `validate_pages.py`
  - `export_pages_text.py`
  - `publish_pages.py`
  - `requirements.txt`
  - `user-config.py.sample`
- `pages/`:
  - generated outputs (`catalog.items.json`, `pages.items.json`, quality report, text exports, etc.)
- `docs/`:
  - template and example documentation

## Setup

```powershell
cd E:\Github\RSDWArchive\website\tools\Pywikibot
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r .\scripts\requirements.txt
```

Copy `scripts/user-config.py.sample` to `user-config.py` and configure credentials/site.

## Master Pipeline (recommended)

```powershell
python .\run_generation_pipeline.py
```

By default this reads:

- `website/data.config.json`
  - `datasetVersion` (or optional `datasetJsonRoot`)

Optional override:

```powershell
python .\run_generation_pipeline.py --dataset-root E:\Github\RSDWArchive\0.11.0.3
```

Runs in order:
1. `website/tools/LootData/CompileLootData.py` -> `pages/LootData.generated.json`
2. `scripts/build_item_catalog.py` -> `pages/catalog.items.json`
3. `scripts/generate_item_pages.py` -> `pages/pages.items.json` + `pages/pages.items.quality.json`
4. `scripts/generate_loot_enemy_pages.py` -> `pages/pages.npcs.json`
5. `scripts/validate_pages.py`
6. `scripts/export_pages_text.py` for all generated page JSON files

Notes:
- Uses recursive discovery under configured `<dataset-root>\json`
- Does not overwrite `website/tools/LootData/LootData.json`
- Optional: `--skip-validate`
- Optional: `--skip-text-export`

## Script Commands (manual use)

Build catalog:
```powershell
python .\scripts\build_item_catalog.py
```

Generate all item pages:
```powershell
python .\scripts\generate_item_pages.py
```

Validate generated pages:
```powershell
python .\scripts\validate_pages.py --pages .\pages\pages.items.json
```

Export pages to text files:
```powershell
python .\scripts\export_pages_text.py --pages .\pages\pages.items.json --out-dir .\pages\pages.items.txt --combined
```

Generate enemy loot pages:
```powershell
python .\scripts\generate_loot_enemy_pages.py --loot-json .\pages\LootData.generated.json --npc-json .\pages\NPCData.generated.json --output .\pages\pages.npcs.json --limit 50
```

Dry-run publish:
```powershell
python .\scripts\publish_pages.py --pages .\pages\pages.items.json --dry-run --max-pages 20
```

Publish:
```powershell
python .\scripts\publish_pages.py --pages .\pages\pages.items.json --max-pages 50
```

Optional publish flag:
- `--skip-login` to skip explicit login call
