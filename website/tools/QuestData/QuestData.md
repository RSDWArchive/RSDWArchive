# QuestData compile tool

## Purpose

Compiles quest definitions, quest flow graphs, item references, and progression hooks into one normalized `QuestData.json` payload. The output is intended to answer practical player questions: quest names/descriptions, objective text and order, required or checked items, reward inventory-space checks, rewarded items, consumed items, recipe unlocks, quest locations, entry tags, and external progression triggers.

## Source inputs

| What | How it is found |
|------|-----------------|
| Root | Resolved to `{datasetVersion}/json` or `RSDW_JSON_ROOT`, with `RSDragonwilds` inside. |
| Quest catalog | All `Quest_*.json` exports with `Type == "QuestData"`. |
| Quest flows | All `QF_*.json` conversation database exports, excluding shared `QuestFlow/` templates. |
| Text | Inline `LocalizedString` / `SourceString`, `ST_*.json`, and embedded `StringTable` exports in `QF_*.json` when referenced by `TableId`. |
| Item names | `ST_ItemNames.json` plus item export fallback logic from `compiledata.py`. |
| Progression hooks | `DT_Progression_Quests.json`. |

## Script and CLI

| Item | Value |
|------|-------|
| Script | [`CompileQuestData.py`](CompileQuestData.py) |
| Default output | `QuestData.json` in this folder |
| CLI | `python CompileQuestData.py [--output PATH]` |

## Output

**Default file:** `QuestData.json`

Top-level keys:

| Key | Meaning |
|-----|---------|
| `version` | Dataset version derived from the selected json root. |
| `generatedAtUtc` | Compile timestamp. |
| `sourceRoot` | Absolute source json directory. |
| `globs` | Quest, flow, and progression source patterns. |
| `counts` | Quest, flow, progression, and unresolved text counts. |
| `quests` | Normalized quest records keyed by quest asset id. |
| `indexes` | Reverse indexes for item requirements, checks, reward inventory-space checks, rewards, consumes, recipes, flow files, progression rows, and entry tags. |
| `issues` | Parse errors, missing files, and unresolved text references. |

Save-file lookup indexes:

| Index | Meaning |
|-------|---------|
| `persistenceIdToQuest` | Maps save `QuestProgress.Quests[].QuestId` values to compiled quest ids. |
| `objectiveIdToQuestObjectives` | Maps saved `QuestObjective` ids to matching quest objective records. |
| `questVariableToQuests` | Maps saved `QuestBools[].QuestVariableName` / `QuestInts[].QuestVariableName` values to quests that reference the variable in flow data. |

## Per-quest sections

Each quest record includes:

- `displayName`, `description`, `questRegion`, `isMainQuest`, `internalName`, and `persistenceId`.
- `objectives` in the order stored by the `QuestData` asset.
- `flowFiles` for primary flow graphs, plus `crossQuestRefs` when a flow references another quest.
- `orderedSteps` from graph traversal order where available.
- `itemRequirements`, `itemChecks`, `inventorySpaceChecks`, `itemRewards`, `itemConsumes`, `recipeRewards`, and `recipeChecks`.
- `questLocations`, `entryPoints`, `stateChanges`, `questPrerequisites`, `questVariables`, `dialogueRefs`, and `progressionTriggers`.

## Notes

`QF_*.json` graphs are branching conversation databases, so `orderedSteps` is best-effort graph order rather than a guaranteed single linear walkthrough. Every extracted row keeps its `flowFile`, `nodeName`, `nodeType`, `nodeGuid`, and `graphOrder` so ambiguous data can be audited against the source export.
