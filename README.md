# RSDWArchive

A repository to archive json/texture files of different RSDW versions.

All of these game files are the property of Jagex.

## RSDWArchive.com
https://rsdwarchive.com

RSDWArchive.com reads the data from this repo. It allows you to quickly navigate files.

## Archived Versions
Can be found at:

https://github.com/RSDWArchive?tab=repositories

## Updating Archive Data
New archive folders are generated locally with:

```powershell
python .\tools\UpdateArchiveData.py
```

The pipeline detects the installed game root, reads the full UE4SS `ProjectVersion`,
uses the shared `E:\Github\Retoc\RSDragonwilds\<version>` cache, runs the
RSDWArchive CUE4Parse extractor against `E:\Github\CUE4Parse`, writes
`<version>\json`, `<version>\textures`, and `<version>\usmap`, updates
`website\data.config.json`, runs the website compile/index stage, generates
reports comparing the previous dataset to the new full version, moves the
previous dataset folder to `E:\Github`, writes a local Git commit batch plan,
and writes `<version>\PipelineRun.json`.

Useful checks before a full run:

```powershell
python .\tools\UpdateArchiveData.py --dry-run
python .\tools\UpdateArchiveData.py --skip-retoc --extract-limit 50 --skip-website --skip-config-update
```

Useful report/archive controls:

```powershell
python .\tools\UpdateArchiveData.py --run-reports --skip-retoc --skip-extract --skip-config-update --skip-website --previous-version 0.11.2 --version 0.11.2.2 --skip-archive-previous
python .\tools\UpdateArchiveData.py --skip-archive-previous
```

Useful Git commit planning commands:

```powershell
python .\tools\PlanGitCommits.py
python .\tools\PlanGitCommits.py commit-batches
```

The second command is a dry run unless `--execute` is added. The pipeline also
writes `<version>\GitCommitPlan.json` at the end of full runs.

To let the pipeline create or push batches at the end, use explicit opt-in flags:

```powershell
python .\tools\UpdateArchiveData.py --git-commit-batches
python .\tools\UpdateArchiveData.py --git-commit-batches --git-push-each
```

Use the full detected game version as the dataset folder, for example `0.11.2.2`.

## Tips for Searching:
Commonly used keywords to help you find what you're looking for. Search for:

### **Tag Style Searching**
You can type: **black png crossbow** and it will find files like **T_Icon_Black_Sniper_Crossbow.png**

### **ST_**
Display Names, Descriptions, Journal Text, etc. (This is most displayed text in game)

### **ITEM_**
DamageMultiplier, CriticalHitChanceIncrease, Weight, PowerLevel, BaseDurability, etc (This is item data)

### **USD_**
UtilitySpellData, ItemsCostInfo, etc (This is Spell data)

### **RECIPE_**
ItemsConsumed, ItemsCreated, OnCraftXpEvent, etc (Players ability to make things and item requirements)

### **DA_Consumable_Plan_**
BuildingPieceToUnlock, MaxStackSize, PersistenceID, etc (Consumable item for building menu)

### **DA_Consumable_Vestige_**
RecipesToUnlock, MaxStackSize, PersistenceID, etc (Consumable item that unlocks Recipes)

### **DT_Progression_**
NumberOfMatchesRequired, UnlockedBuildings, UnlockedRecipes, etc (This is what items are required for the player to unlock a recipe)
