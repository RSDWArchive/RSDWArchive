# RSDWArchive

A repository to archive json/texture files of different RSDW versions to give easy access to modders. 

All of these game files are the property of Jagex.

## RSDWArchive.com
https://rsdwarchive.com

RSDWArchive.com reads the data from this repo. It allows you to quickly navigate files.

### **Tag Style Searching**
You can type: **black png crossbow** and it will find files like **T_Icon_Black_Sniper_Crossbow.png**

## Tips for Searching:
Commonly used keywords to help you find what you're looking for. Search for:

### **ST_**
Display Names, Descriptions, Journal Text, etc. (This is most displayed text in game)

### **ITEM_**
DamageMultiplier, CriticalHitChanceIncrease, Weight, PowerLevel, BaseDurability, etc (This is item data)

### **RECIPE_**
ItemsConsumed, ItemsCreated, OnCraftXpEvent, etc (Players ability to make things and item requirements)

### **DA_Consumable_Plan_**
BuildingPieceToUnlock, MaxStackSize, PersistenceID, etc (Consumable item for building menu)

### **DA_Consumable_Vestige_**
RecipesToUnlock, MaxStackSize, PersistenceID, etc (Consumable item that unlocks Recipes)

### **DT_Progression_**
NumberOfMatchesRequired, UnlockedBuildings, UnlockedRecipes, etc (This is what items are required for the player to unlock a recipe)

## Location Data
Location Data for actors is in chunks. I've compiled them here:

### Location Data Tool:
https://rsdwarchive.com/LocationData.html

### ADVANCED: Location Data Path
https://github.com/RSDWArchive/RSDWArchive/tree/main/0.11.0.3/json/RSDragonwilds/Content/Maps/World/L_World/_Generated_

Script for compiling Location Data to LocationData.json
https://github.com/RSDWArchive/RSDWArchive/tree/main/website/tools/LocationData

## Loot Data
Loot Data is in multiple files. I've compiled them here:

### Loot Data Tool:
https://rsdwarchive.com/LootData.html

### ADVANCED: Loot Data Paths
https://github.com/RSDWArchive/RSDWArchive/tree/main/0.11.0.3/json/RSDragonwilds/Content/Gameplay/Items/LootDropTables
https://github.com/RSDWArchive/RSDWArchive/tree/main/0.11.0.3/json/RSDragonwilds/Plugins/GameFeatures/DowdunReach/Content/Gameplay/Items/LootDropTables

Script for compiling Loot Data to LootData.json
https://github.com/RSDWArchive/RSDWArchive/tree/main/website/tools/LootData
