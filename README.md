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
See [Updating.md](Updating.md) for the local archive update pipeline, report
generation, old-dataset archival, and Git batch-push flow.

For larger multi-project orchestration, see
[PIPELINE_HANDOFF.md](PIPELINE_HANDOFF.md) for this repo's pipeline contract,
inputs, outputs, success markers, and failure modes.

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
