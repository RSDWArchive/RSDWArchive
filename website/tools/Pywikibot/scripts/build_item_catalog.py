import json
import os
import re
from collections import defaultdict
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


OUTPUT_PATH = Path(__file__).resolve().parent.parent / "pages" / "catalog.items.json"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"
EXCLUDED_FILE_NAME_TOKENS = ("_MeshData_",)


def parse_object_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if "'" in value:
        return value.split("'")[1]
    return value


def parse_asset_leaf(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    leaf = value.rsplit("/", 1)[-1]
    return leaf.split(".")[0] if "." in leaf else leaf


def read_export(path: Path, expected_name_prefix: str | None = None) -> dict[str, Any] | None:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, list) or not raw:
        return None
    candidates = [entry for entry in raw if isinstance(entry, dict)]
    if not candidates:
        return None
    if expected_name_prefix:
        for entry in candidates:
            name = entry.get("Name")
            if isinstance(name, str) and name.startswith(expected_name_prefix):
                return entry
    return candidates[0]


def rel_path(path: Path, repo_root: Path) -> str:
    return str(path.relative_to(repo_root)).replace("\\", "/")


def extract_text_field(field: Any) -> str | None:
    if isinstance(field, dict):
        return field.get("LocalizedString") or field.get("SourceString")
    return None


def extract_stat_subset(props: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "DamageMultiplier",
        "CriticalHitChanceIncrease",
        "Weight",
        "PowerLevel",
        "BaseDurability",
        "MaxStackSize",
        "BlockingDamageNegation",
        "BaseDamage",
        "AdditionalDamage",
        "DamageTypes",
        "ArmorWeight",
        "Slot",
    ]
    out = {}
    for key in keys:
        if key in props:
            out[key] = props[key]
    return out


def load_wearable_rows(source_root: Path) -> dict[str, dict[str, Any]]:
    table_path = (
        source_root
        / "RSDragonwilds"
        / "Content"
        / "Gameplay"
        / "Character"
        / "Player"
        / "Equipment"
        / "DT_WearableEquipment.json"
    )
    try:
        raw = json.loads(table_path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, list) or not raw:
        return {}
    table = raw[0]
    rows = table.get("Rows")
    if not isinstance(rows, dict):
        return {}
    out: dict[str, dict[str, Any]] = {}
    for row_name, row_data in rows.items():
        if isinstance(row_name, str) and isinstance(row_data, dict):
            out[row_name] = row_data
    return out


def read_item_wearable_row_name(repo_root: Path, source_file: str) -> str | None:
    path = repo_root / source_file
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    if not isinstance(raw, list):
        return None
    for export in raw:
        if not isinstance(export, dict):
            continue
        name = export.get("Name")
        if not isinstance(name, str) or not name.startswith("ITEM_"):
            continue
        props = export.get("Properties") or {}
        handle = props.get("WearableEquipmentDataTableRowHandle") or {}
        row_name = handle.get("RowName") if isinstance(handle, dict) else None
        if isinstance(row_name, str):
            return row_name
    return None


def to_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            return None
    return None


def round_half_up(value: float) -> int:
    try:
        return int(Decimal(str(value)).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    except (InvalidOperation, ValueError):
        return int(round(value))


def compute_displayed_defence(defense: float, resistance: float | None) -> int:
    resistance_value = resistance or 0.0
    return round_half_up((defense + resistance_value) * 0.75)


def build_wearable_equipment_data(row_name: str, row: dict[str, Any]) -> dict[str, Any] | None:
    defense = to_float(row.get("Defense"))
    melee_res = to_float(row.get("MeleeResistance"))
    ranged_res = to_float(row.get("RangedResistance"))
    magic_res = to_float(row.get("MagicResistance"))
    if defense is None and melee_res is None and ranged_res is None and magic_res is None:
        return None

    raw = {
        "defense": defense,
        "meleeResistance": melee_res,
        "rangedResistance": ranged_res,
        "magicResistance": magic_res,
    }

    derived_display_defence = None
    if defense is not None:
        derived_display_defence = {
            "melee": compute_displayed_defence(defense, melee_res),
            "ranged": compute_displayed_defence(defense, ranged_res),
            "magic": compute_displayed_defence(defense, magic_res),
            "formula": "round((Defense + TypeResistance) * 0.75)",
        }

    return {
        "rowName": row_name,
        "raw": raw,
        "derivedDisplayDefence": derived_display_defence,
    }


def infer_item_category(item: dict[str, Any]) -> tuple[str, list[str]]:
    item_id = str(item.get("itemId", ""))
    class_name = str(item.get("className", ""))
    source_file = str(item.get("sourceFile", "")).lower()
    tags = [str(tag) for tag in (item.get("itemFilterTags") or [])]
    tags_joined = " ".join(tags)
    hints: list[str] = []

    if "ItemFilter.Type.Equipment.Armour" in tags_joined or "WearableEquipmentData" in class_name:
        hints.append("armour")
    if "ItemFilter.Type.Equipment.Weapon" in tags_joined or "HeldEquipmentData" in class_name:
        hints.append("weapon")
    if "ItemFilter.Type.Equipment.Tool" in tags_joined:
        hints.append("tool")
    if "ItemFilter.Type.Equipment.Trinket" in tags_joined:
        hints.append("trinket")
    if "ItemFilter.Type.Equipment" in tags_joined and "armour" not in hints and "weapon" not in hints:
        hints.append("equipment_other")
    if "ItemFilter.Type.Consumable.Plan" in tags_joined:
        hints.append("plan")
    if "ItemFilter.Type.Consumable.Vestige" in tags_joined:
        hints.append("vestige")
    if "ItemFilter.Type.Consumable" in tags_joined and "plan" not in hints and "vestige" not in hints:
        hints.append("consumable")
    if "ItemFilter.Type.QuestItem" in tags_joined:
        hints.append("quest_item")
    if "ITEM_Rune_" in item_id or item_id.endswith("Rune"):
        hints.append("rune")
    if "_Ammo_" in item_id or ".Ammo" in tags_joined:
        hints.append("ammo")

    if "/consumables/food/" in source_file:
        hints.append("food")
    if "/consumables/potions/" in source_file:
        hints.append("potion")
    if "/resources/" in source_file:
        hints.append("resource")
    if "/equipment/" in source_file and not any(x in hints for x in ("armour", "weapon", "tool", "trinket")):
        hints.append("equipment_other")

    # Keep deterministic order and pick first as primary category.
    deduped = []
    seen = set()
    for hint in hints:
        if hint in seen:
            continue
        seen.add(hint)
        deduped.append(hint)

    if deduped:
        return deduped[0], deduped
    return "other", ["other"]


def parse_version_tuple(value: str) -> tuple[int, ...]:
    if not re.fullmatch(r"\d+(?:\.\d+)+", value):
        return tuple()
    return tuple(int(part) for part in value.split("."))


def resolve_json_root(repo_root: Path) -> tuple[Path, str]:
    override = os.getenv(JSON_ROOT_ENV_VAR, "").strip()
    if override:
        root = Path(override)
        if (root / "RSDragonwilds").exists():
            version = root.parent.name
            return root, version
        if (root / "json" / "RSDragonwilds").exists():
            version = root.name
            return root / "json", version
        raise FileNotFoundError(
            f"{JSON_ROOT_ENV_VAR} points to unsupported path: {root}. "
            "Expected either <version>/json or direct json root containing RSDragonwilds."
        )

    candidates: list[tuple[tuple[int, ...], Path, str]] = []
    for json_dir in repo_root.glob("*/json"):
        if not json_dir.is_dir():
            continue
        if not (json_dir / "RSDragonwilds").exists():
            continue
        version_name = json_dir.parent.name
        parsed = parse_version_tuple(version_name)
        if parsed:
            candidates.append((parsed, json_dir, version_name))

    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        _, selected_root, selected_version = candidates[0]
        return selected_root, selected_version

    fallback = repo_root / DEFAULT_TARGET_VERSION_FOLDER / "json"
    if (fallback / "RSDragonwilds").exists():
        return fallback, DEFAULT_TARGET_VERSION_FOLDER

    raise FileNotFoundError(
        "Could not auto-detect a dataset root. "
        f"Set {JSON_ROOT_ENV_VAR} to <version>/json or json root containing RSDragonwilds."
    )


def main() -> None:
    repo_root = Path(__file__).resolve().parents[4]
    source_root, source_version = resolve_json_root(repo_root)
    if not source_root.exists():
        raise FileNotFoundError(f"JSON root not found: {source_root}")

    item_files = sorted(source_root.rglob("ITEM_*.json"))
    filtered_item_files = [
        path for path in item_files if not any(token in path.name for token in EXCLUDED_FILE_NAME_TOKENS)
    ]
    recipe_files = sorted(source_root.rglob("RECIPE_*.json"))
    plan_files = sorted(source_root.rglob("DA_Consumable_Plan_*.json"))
    unlocker_files = sorted(source_root.rglob("DA_Consumable_Vestige_*.json"))
    unlocker_files += sorted(source_root.rglob("DA_Consumable_Pattern_*.json"))
    progression_files = sorted(source_root.rglob("DT_Progression_*.json"))
    journal_recipe_files = sorted(source_root.rglob("JOURNAL_Recipes_*.json"))
    st_name_files = sorted(source_root.rglob("ST_ItemNames.json"))
    st_desc_files = sorted(source_root.rglob("ST_ItemDescriptions.json"))
    wearable_rows = load_wearable_rows(source_root)

    st_names: dict[str, str] = {}
    st_descriptions: dict[str, str] = {}
    for path in st_name_files:
        export = read_export(path)
        if not export:
            continue
        entries = (export.get("StringTable") or {}).get("KeysToEntries")
        if isinstance(entries, dict):
            st_names.update({str(k): str(v) for k, v in entries.items()})
    for path in st_desc_files:
        export = read_export(path)
        if not export:
            continue
        entries = (export.get("StringTable") or {}).get("KeysToEntries")
        if isinstance(entries, dict):
            st_descriptions.update({str(k): str(v) for k, v in entries.items()})

    items: dict[str, Any] = {}
    for path in filtered_item_files:
        export = read_export(path, expected_name_prefix="ITEM_")
        if not export:
            continue
        props = export.get("Properties") or {}
        item_id = export.get("Name")
        if not isinstance(item_id, str):
            continue

        name_obj = props.get("Name") or {}
        desc_obj = props.get("FlavourText") or {}
        name_key = name_obj.get("Key") if isinstance(name_obj, dict) else None
        desc_key = desc_obj.get("Key") if isinstance(desc_obj, dict) else None
        display_name = extract_text_field(name_obj) or (st_names.get(str(name_key)) if name_key else None)
        description = extract_text_field(desc_obj) or (st_descriptions.get(str(desc_key)) if desc_key else None)

        items[item_id] = {
            "itemId": item_id,
            "displayName": display_name,
            "description": description,
            "className": export.get("Class"),
            "typeName": export.get("Type"),
            "itemFilterTags": props.get("ItemFilterTags", []),
            "internalName": props.get("InternalName"),
            "sourceFile": rel_path(path, repo_root),
            "stats": extract_stat_subset(props),
            "links": {
                "createdByRecipes": [],
                "requiredInRecipes": [],
                "journalEntries": [],
                "unlockedByConsumables": [],
                "unlockedByProgressionBundles": [],
            },
        }

    recipes: dict[str, Any] = {}
    recipes_created_item_ids: dict[str, list[str]] = defaultdict(list)
    recipes_consumed_item_ids: dict[str, list[str]] = defaultdict(list)

    for path in recipe_files:
        export = read_export(path, expected_name_prefix="RECIPE_")
        if not export:
            continue
        props = export.get("Properties") or {}
        recipe_id = export.get("Name")
        if not isinstance(recipe_id, str):
            continue

        consumed = []
        for entry in props.get("ItemsConsumed", []):
            item_data = (entry or {}).get("ItemData") or {}
            item_id = parse_object_name(item_data.get("ObjectName"))
            consumed.append(
                {
                    "itemId": item_id,
                    "count": entry.get("Count"),
                    "objectPath": item_data.get("ObjectPath"),
                }
            )
            if item_id:
                recipes_consumed_item_ids[recipe_id].append(item_id)

        created = []
        for entry in props.get("ItemsCreated", []):
            item_data = (entry or {}).get("ItemData") or {}
            item_id = parse_object_name(item_data.get("ObjectName"))
            created.append(
                {
                    "itemId": item_id,
                    "count": entry.get("Count"),
                    "objectPath": item_data.get("ObjectPath"),
                }
            )
            if item_id:
                recipes_created_item_ids[recipe_id].append(item_id)

        station = None
        xp_event = props.get("OnCraftXpEvent") or {}
        if isinstance(xp_event, dict):
            station = xp_event.get("RowName")

        recipes[recipe_id] = {
            "recipeId": recipe_id,
            "sourceFile": rel_path(path, repo_root),
            "consumedItems": consumed,
            "createdItems": created,
            "skillXpAwarded": props.get("SkillXPAwardedOnCraft"),
            "skillUsedToCraft": parse_object_name(((props.get("SkillUsedToCraft") or {}).get("ObjectName"))),
            "craftXpEventRow": station,
            "internalName": props.get("InternalName"),
        }

    unlockers: dict[str, Any] = {}
    for path in plan_files + unlocker_files:
        export = read_export(path, expected_name_prefix="DA_")
        if not export:
            continue
        props = export.get("Properties") or {}
        unlock_id = export.get("Name")
        if not isinstance(unlock_id, str):
            continue

        unlock_type = "plan" if "BuildingPieceToUnlock" in props else "recipe_unlocker"
        recipes_to_unlock = []
        for entry in props.get("RecipesToUnlock", []):
            recipe_id = parse_object_name((entry or {}).get("ObjectName"))
            if recipe_id:
                recipes_to_unlock.append(recipe_id)

        building_to_unlock = None
        if isinstance(props.get("BuildingPieceToUnlock"), dict):
            building_to_unlock = parse_object_name((props.get("BuildingPieceToUnlock") or {}).get("ObjectName"))

        unlockers[unlock_id] = {
            "unlockerId": unlock_id,
            "unlockerType": unlock_type,
            "sourceFile": rel_path(path, repo_root),
            "displayName": extract_text_field(props.get("Name")),
            "description": extract_text_field(props.get("FlavourText")),
            "recipesToUnlock": recipes_to_unlock,
            "buildingPieceToUnlock": building_to_unlock,
            "maxStackSize": props.get("MaxStackSize"),
            "internalName": props.get("InternalName"),
        }

    progression: dict[str, Any] = {}
    recipe_to_progression_rows: dict[str, list[str]] = defaultdict(list)
    for path in progression_files:
        export = read_export(path, expected_name_prefix="DT_")
        if not export:
            continue
        rows = export.get("Rows")
        if not isinstance(rows, dict):
            continue

        table_name = str(export.get("Name"))
        for row_name, row in rows.items():
            if not isinstance(row, dict):
                continue
            unlocked_recipes = []
            for entry in row.get("UnlockedRecipes", []):
                recipe_id = parse_object_name((entry or {}).get("ObjectName"))
                if recipe_id:
                    unlocked_recipes.append(recipe_id)
                    recipe_to_progression_rows[recipe_id].append(f"{table_name}:{row_name}")

            unlock_query_items = []
            unlock_query = row.get("UnlockQuery") or {}
            if isinstance(unlock_query, dict):
                for operand_key in ("FirstOperand", "SecondOperand"):
                    operand = unlock_query.get(operand_key) or {}
                    if isinstance(operand, dict):
                        for item in operand.get("Items", []):
                            item_id = parse_object_name((item or {}).get("ObjectName"))
                            if item_id:
                                unlock_query_items.append(item_id)

            progression[f"{table_name}:{row_name}"] = {
                "tableName": table_name,
                "rowName": row_name,
                "unlockQueryString": row.get("UnlockQueryString"),
                "numberOfMatchesRequired": ((unlock_query.get("FirstOperand") or {}).get("NumberOfMatchesRequired") if isinstance(unlock_query, dict) else None),
                "unlockedRecipes": unlocked_recipes,
                "unlockedBuildings": [parse_object_name((entry or {}).get("ObjectName")) for entry in row.get("UnlockedBuildings", [])],
                "unlockQueryItems": unlock_query_items,
            }

    journals: dict[str, Any] = {}
    item_to_journals: dict[str, list[str]] = defaultdict(list)
    for path in journal_recipe_files:
        export = read_export(path, expected_name_prefix="JOURNAL_")
        if not export:
            continue
        props = export.get("Properties") or {}
        journal_id = export.get("Name")
        if not isinstance(journal_id, str):
            continue

        item_data = props.get("ItemData") or {}
        asset = item_data.get("AssetPathName") if isinstance(item_data, dict) else None
        linked_item_id = parse_asset_leaf(asset)
        recipe_data = props.get("RecipeData") or {}
        recipe_asset = recipe_data.get("AssetPathName") if isinstance(recipe_data, dict) else None
        linked_recipe_id = parse_asset_leaf(recipe_asset)
        station_handle = props.get("StationTableRowHandle") or {}
        station_row = station_handle.get("RowName") if isinstance(station_handle, dict) else None
        page_descriptions = []
        for entry in props.get("PageDescriptions", []):
            description = extract_text_field((entry or {}).get("Description"))
            if description:
                page_descriptions.append(description)

        journals[journal_id] = {
            "journalId": journal_id,
            "sourceFile": rel_path(path, repo_root),
            "displayName": extract_text_field(props.get("DisplayName")),
            "linkedItemId": linked_item_id,
            "linkedRecipeId": linked_recipe_id,
            "stationRow": station_row,
            "descriptionPages": page_descriptions,
        }
        if linked_item_id:
            item_to_journals[linked_item_id].append(journal_id)

    unlocker_to_created_items: dict[str, list[str]] = defaultdict(list)
    for unlocker_id, unlocker in unlockers.items():
        for recipe_id in unlocker.get("recipesToUnlock", []):
            for item_id in recipes_created_item_ids.get(recipe_id, []):
                unlocker_to_created_items[unlocker_id].append(item_id)

    # Link all relationships back to per-item record
    for recipe_id, item_ids in recipes_created_item_ids.items():
        for item_id in item_ids:
            if item_id in items:
                items[item_id]["links"]["createdByRecipes"].append(recipe_id)

    for recipe_id, item_ids in recipes_consumed_item_ids.items():
        for item_id in item_ids:
            if item_id in items:
                items[item_id]["links"]["requiredInRecipes"].append(recipe_id)

    for item_id, journal_ids in item_to_journals.items():
        if item_id in items:
            items[item_id]["links"]["journalEntries"].extend(journal_ids)

    for unlocker_id, item_ids in unlocker_to_created_items.items():
        for item_id in item_ids:
            if item_id in items:
                items[item_id]["links"]["unlockedByConsumables"].append(unlocker_id)

    for recipe_id, progression_rows in recipe_to_progression_rows.items():
        for item_id in recipes_created_item_ids.get(recipe_id, []):
            if item_id in items:
                items[item_id]["links"]["unlockedByProgressionBundles"].extend(progression_rows)

    for item in items.values():
        source_file = item.get("sourceFile")
        if isinstance(source_file, str) and source_file:
            row_name = read_item_wearable_row_name(repo_root, source_file)
            if row_name:
                wearable_row = wearable_rows.get(row_name)
                if isinstance(wearable_row, dict):
                    wearable_data = build_wearable_equipment_data(row_name, wearable_row)
                    if wearable_data:
                        item["wearableEquipment"] = wearable_data

        category, category_hints = infer_item_category(item)
        item["category"] = category
        item["categoryHints"] = category_hints
        for link_key in item["links"]:
            item["links"][link_key] = sorted(set(item["links"][link_key]))

    items_by_category: dict[str, list[str]] = defaultdict(list)
    for item_id, item in items.items():
        items_by_category[str(item.get("category", "other"))].append(item_id)
    for category_name in list(items_by_category.keys()):
        items_by_category[category_name].sort()

    recipes_by_created_item_category: dict[str, list[str]] = defaultdict(list)
    for recipe_id, recipe in recipes.items():
        created_items = recipe.get("createdItems", [])
        categories = set()
        for created in created_items:
            created_item_id = created.get("itemId")
            created_item = items.get(created_item_id)
            if created_item:
                categories.add(str(created_item.get("category", "other")))
        if not categories:
            categories.add("other")
        for category_name in sorted(categories):
            recipes_by_created_item_category[category_name].append(recipe_id)
    for category_name in list(recipes_by_created_item_category.keys()):
        recipes_by_created_item_category[category_name] = sorted(set(recipes_by_created_item_category[category_name]))

    output = {
        "version": source_version,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "counts": {
            "itemFiles": len(item_files),
            "itemFilesAfterFilters": len(filtered_item_files),
            "recipeFiles": len(recipe_files),
            "planFiles": len(plan_files),
            "unlockerFiles": len(unlocker_files),
            "progressionFiles": len(progression_files),
            "journalRecipeFiles": len(journal_recipe_files),
            "items": len(items),
            "recipes": len(recipes),
            "unlockers": len(unlockers),
            "progressionRows": len(progression),
            "journals": len(journals),
        },
        "sources": {
            "stItemNamesFiles": [rel_path(path, repo_root) for path in st_name_files],
            "stItemDescriptionFiles": [rel_path(path, repo_root) for path in st_desc_files],
        },
        "indexes": {
            "itemsByCategory": {k: items_by_category[k] for k in sorted(items_by_category.keys())},
            "recipesByCreatedItemCategory": {
                k: recipes_by_created_item_category[k] for k in sorted(recipes_by_created_item_category.keys())
            },
        },
        "items": {key: items[key] for key in sorted(items.keys())},
        "recipes": {key: recipes[key] for key in sorted(recipes.keys())},
        "unlockers": {key: unlockers[key] for key in sorted(unlockers.keys())},
        "progression": {key: progression[key] for key in sorted(progression.keys())},
        "journals": {key: journals[key] for key in sorted(journals.keys())},
    }

    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote item catalog: {OUTPUT_PATH}")
    print(f"[INFO] Items: {len(items)} | Recipes: {len(recipes)} | Unlockers: {len(unlockers)}")


if __name__ == "__main__":
    main()
