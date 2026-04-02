import json
import os
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDENT = 2
SOURCE_DIR_ENV_VAR = "RSDW_LOOT_SOURCE_DIR"
TARGET_VERSION_FOLDER = "0.11.0.3"

TABLE_FILENAMES = {
    "DT_CompositeEnemyLootDropTable": "DT_CompositeEnemyLootDropTable.json",
    "DT_EnemyLootDropTable": "DT_EnemyLootDropTable.json",
    "DT_LootDropTable": "DT_LootDropTable.json",
    "DT_LootChest_RespawnProfiles": "DT_LootChest_RespawnProfiles.json",
    "DT_LootChests_Prefabs": "DT_LootChests_Prefabs.json",
    "DT_LootChest_Sets": "DT_LootChest_Sets.json",
    "DT_CompositeEnemyLootDropTable_DowdunReach": "DT_CompositeEnemyLootDropTable_DowdunReach.json",
    "DT_EnemyLootDropTable_DowdunReach": "DT_EnemyLootDropTable_DowdunReach.json",
    "DT_LootDropTable_DowdunReach": "DT_LootDropTable_DowdunReach.json",
}

BASE_LOOT_RELATIVE_DIR = Path(
    TARGET_VERSION_FOLDER,
    "json",
    "RSDragonwilds",
    "Content",
    "Gameplay",
    "Items",
    "LootDropTables",
)

DOWNDUN_LOOT_RELATIVE_DIR = Path(
    TARGET_VERSION_FOLDER,
    "json",
    "RSDragonwilds",
    "Plugins",
    "GameFeatures",
    "DowdunReach",
    "Content",
    "Gameplay",
    "Items",
    "LootDropTables",
)

TABLE_SOURCE_GROUP = {
    "DT_CompositeEnemyLootDropTable": "base",
    "DT_EnemyLootDropTable": "base",
    "DT_LootDropTable": "base",
    "DT_LootChest_RespawnProfiles": "base",
    "DT_LootChests_Prefabs": "base",
    "DT_LootChest_Sets": "base",
    "DT_CompositeEnemyLootDropTable_DowdunReach": "dowdun",
    "DT_EnemyLootDropTable_DowdunReach": "dowdun",
    "DT_LootDropTable_DowdunReach": "dowdun",
}


def parse_table_name(object_name: str) -> str:
    if "'" in object_name:
        return object_name.split("'")[1]
    return object_name


def parse_item_id(object_name: str) -> str:
    if "'" in object_name:
        return object_name.split("'")[1]
    return object_name


def read_export_table(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, f"Failed to parse {path}: {exc}"

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        return None, f"Unexpected JSON shape in {path}"

    table = raw[0]
    if not isinstance(table.get("Rows"), dict):
        return None, f"Table missing Rows object in {path}"
    return table, None


def resolve_source_root(repo_root: Path) -> Path:
    source_override = os.getenv(SOURCE_DIR_ENV_VAR, "").strip()
    if source_override:
        return Path(source_override)
    return repo_root


def resolve_table_paths(source_root: Path) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    base_dir = source_root / BASE_LOOT_RELATIVE_DIR
    dowdun_dir = source_root / DOWNDUN_LOOT_RELATIVE_DIR
    for table_name, file_name in TABLE_FILENAMES.items():
        group = TABLE_SOURCE_GROUP[table_name]
        parent = base_dir if group == "base" else dowdun_dir
        paths[table_name] = parent / file_name
    return paths


def get_table_handle_name(handle: dict[str, Any]) -> str | None:
    dt = handle.get("DataTable")
    if not isinstance(dt, dict):
        return None
    object_name = dt.get("ObjectName")
    if not isinstance(object_name, str):
        return None
    return parse_table_name(object_name)


def get_set_entries(set_row: dict[str, Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for item in set_row.get("SpawnableItems", []):
        spawned = item.get("SpawnedItemData") or {}
        object_name = spawned.get("ObjectName", "")
        object_path = spawned.get("ObjectPath", "")
        out.append(
            {
                "itemId": parse_item_id(str(object_name)),
                "itemObjectName": object_name,
                "itemObjectPath": object_path,
                "minimumDropAmount": item.get("MinimumDropAmount"),
                "maximumDropAmount": item.get("MaximumDropAmount"),
                "dropChance": item.get("DropChance"),
                "flags": {
                    "oneInstancePerPlayerOnlyVisibleToThem": item.get("bOneInstancePerPlayerOnlyVisibleToThem"),
                    "autoAddToInventory": item.get("bAutoAddToInventory"),
                    "onlyForPlayersThatInflictedDamage": item.get("bOnlyForPlayersThatInflictedDamage"),
                },
            }
        )
    return out


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def main() -> None:
    print("[DEBUG] CompileLootData started", flush=True)
    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    table_paths = resolve_table_paths(source_root)
    out_path = here / "LootData.json"

    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    tables: dict[str, dict[str, Any]] = {}
    table_meta: dict[str, dict[str, Any]] = {}
    issues: dict[str, Any] = {
        "missingFiles": [],
        "parseErrors": [],
        "missingReferences": [],
    }

    for table_name, file_name in TABLE_FILENAMES.items():
        path = table_paths[table_name]
        if not path.exists():
            issues["missingFiles"].append({"table": table_name, "file": file_name})
            continue
        table, error = read_export_table(path)
        if error:
            issues["parseErrors"].append({"table": table_name, "file": str(path), "error": error})
            continue
        assert table is not None
        tables[table_name] = table
        table_meta[table_name] = {
            "file": str(path.relative_to(repo_root)).replace("\\", "/"),
            "rowCount": len(table["Rows"]),
            "type": table.get("Type"),
        }

    table_rows: dict[str, dict[str, Any]] = {
        name: tbl.get("Rows", {}) for name, tbl in tables.items()
    }

    enemies: dict[str, Any] = {}
    resolved_drop_handles_by_enemy: dict[str, set[tuple[str, str, Any]]] = defaultdict(set)
    enemy_sources = [
        "DT_EnemyLootDropTable",
        "DT_EnemyLootDropTable_DowdunReach",
        "DT_CompositeEnemyLootDropTable",
        "DT_CompositeEnemyLootDropTable_DowdunReach",
    ]

    for source_table in enemy_sources:
        rows = table_rows.get(source_table)
        if not rows:
            continue
        for enemy_name, enemy_row in rows.items():
            enemy_entry = enemies.setdefault(enemy_name, {"sources": [], "drops": []})
            handles_seen: set[tuple[str, str, Any]] = set()
            for tier in enemy_row.get("TablesByPowerLevel", []):
                min_level = tier.get("MinimumPowerLevel")
                for handle in tier.get("TableHandles", []):
                    target_table = get_table_handle_name(handle)
                    target_row = handle.get("RowName")
                    if not target_table or not target_row:
                        continue
                    key = (target_table, str(target_row), min_level)
                    if key in handles_seen:
                        continue
                    handles_seen.add(key)
                    enemy_entry["sources"].append(
                        {
                            "fromTable": source_table,
                            "minimumPowerLevel": min_level,
                            "targetTable": target_table,
                            "targetRow": target_row,
                        }
                    )

                    target_rows = table_rows.get(target_table)
                    if target_rows is None or target_row not in target_rows:
                        issues["missingReferences"].append(
                            {
                                "chain": "enemy->lootDrop",
                                "fromTable": source_table,
                                "fromRow": enemy_name,
                                "targetTable": target_table,
                                "targetRow": target_row,
                            }
                        )
                        continue

                    # Keep sourceRefs for traceability, but avoid duplicating resolved drops
                    # when base + composite tables point to the same target row.
                    resolved_key = (target_table, str(target_row), min_level)
                    if resolved_key in resolved_drop_handles_by_enemy[enemy_name]:
                        continue
                    resolved_drop_handles_by_enemy[enemy_name].add(resolved_key)

                    drop_row = target_rows[target_row]
                    for resource in drop_row.get("Resources", []):
                        spawned = resource.get("SpawnedItemData") or {}
                        object_name = spawned.get("ObjectName", "")
                        object_path = spawned.get("ObjectPath", "")
                        enemy_entry["drops"].append(
                            {
                                "sourceTable": target_table,
                                "sourceRow": target_row,
                                "itemId": parse_item_id(str(object_name)),
                                "itemObjectName": object_name,
                                "itemObjectPath": object_path,
                                "minimumDropAmount": resource.get("MinimumDropAmount"),
                                "maximumDropAmount": resource.get("MaximumDropAmount"),
                                "dropChance": resource.get("DropChance"),
                                "flags": {
                                    "oneInstancePerPlayerOnlyVisibleToThem": resource.get("bOneInstancePerPlayerOnlyVisibleToThem"),
                                    "autoAddToInventory": resource.get("bAutoAddToInventory"),
                                    "onlyForPlayersThatInflictedDamage": resource.get("bOnlyForPlayersThatInflictedDamage"),
                                },
                            }
                        )

    for enemy_entry in enemies.values():
        enemy_entry["sources"].sort(
            key=lambda x: (x["fromTable"], x["targetTable"], str(x["targetRow"]), x["minimumPowerLevel"] or 0)
        )
        enemy_entry["drops"].sort(key=lambda x: (x["itemId"], x["sourceTable"], str(x["sourceRow"])))

    chest_profiles = table_rows.get("DT_LootChest_RespawnProfiles", {})
    chest_prefabs = table_rows.get("DT_LootChests_Prefabs", {})
    chest_sets = table_rows.get("DT_LootChest_Sets", {})

    chests: dict[str, Any] = {}
    item_sets: dict[str, Any] = {set_name: get_set_entries(row) for set_name, row in chest_sets.items()}

    for profile_name, profile_row in chest_profiles.items():
        loot_roll_handle = profile_row.get("LootRollHandle") or {}
        prefab_table = get_table_handle_name(loot_roll_handle)
        prefab_row = loot_roll_handle.get("RowName")

        chest_entry = {
            "respawn": {
                "inGameRespawnTime": profile_row.get("InGameRespawnTime"),
                "respawnTrigger": profile_row.get("RespawnTrigger"),
            },
            "prefabRef": {
                "table": prefab_table,
                "row": prefab_row,
            },
            "guaranteedSetRows": [],
            "additionalSetRows": [],
            "resolvedItems": [],
        }

        if prefab_table != "DT_LootChests_Prefabs" or prefab_row not in chest_prefabs:
            issues["missingReferences"].append(
                {
                    "chain": "respawn->prefab",
                    "fromTable": "DT_LootChest_RespawnProfiles",
                    "fromRow": profile_name,
                    "targetTable": prefab_table,
                    "targetRow": prefab_row,
                }
            )
            chests[profile_name] = chest_entry
            continue

        prefab = chest_prefabs[prefab_row]
        for set_handle in prefab.get("GuaranteedItemSets", []):
            set_row = set_handle.get("RowName")
            chest_entry["guaranteedSetRows"].append(set_row)
            if set_row not in chest_sets:
                issues["missingReferences"].append(
                    {
                        "chain": "prefab->set(guaranteed)",
                        "fromTable": "DT_LootChests_Prefabs",
                        "fromRow": prefab_row,
                        "targetTable": "DT_LootChest_Sets",
                        "targetRow": set_row,
                    }
                )
                continue
            for item in item_sets[set_row]:
                chest_entry["resolvedItems"].append(
                    {
                        "source": "guaranteedSet",
                        "setRow": set_row,
                        "item": item,
                    }
                )

        for additional in prefab.get("AdditionalItemSets", []):
            handle = additional.get("LootItemSetHandle") or {}
            set_row = handle.get("RowName")
            set_chance = additional.get("DropChance")
            chest_entry["additionalSetRows"].append({"setRow": set_row, "setRollChance": set_chance})
            if set_row not in chest_sets:
                issues["missingReferences"].append(
                    {
                        "chain": "prefab->set(additional)",
                        "fromTable": "DT_LootChests_Prefabs",
                        "fromRow": prefab_row,
                        "targetTable": "DT_LootChest_Sets",
                        "targetRow": set_row,
                    }
                )
                continue
            for item in item_sets[set_row]:
                chest_entry["resolvedItems"].append(
                    {
                        "source": "additionalSet",
                        "setRow": set_row,
                        "setRollChance": set_chance,
                        "item": item,
                    }
                )

        chests[profile_name] = chest_entry

    item_to_enemies: dict[str, list[str]] = defaultdict(list)
    for enemy_name, enemy_entry in enemies.items():
        seen_for_enemy = set()
        for drop in enemy_entry["drops"]:
            item_id = drop["itemId"]
            if item_id in seen_for_enemy:
                continue
            seen_for_enemy.add(item_id)
            item_to_enemies[item_id].append(enemy_name)
    for item_id in item_to_enemies:
        item_to_enemies[item_id].sort()

    item_to_chest_profiles: dict[str, list[str]] = defaultdict(list)
    for profile_name, chest_entry in chests.items():
        seen_for_profile = set()
        for resolved in chest_entry["resolvedItems"]:
            item_id = resolved["item"]["itemId"]
            if item_id in seen_for_profile:
                continue
            seen_for_profile.add(item_id)
            item_to_chest_profiles[item_id].append(profile_name)
    for item_id in item_to_chest_profiles:
        item_to_chest_profiles[item_id].sort()

    compiled = {
        "version": TARGET_VERSION_FOLDER,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "tables": sorted_dict(table_meta),
        "enemies": sorted_dict(enemies),
        "chests": sorted_dict(chests),
        "itemSets": sorted_dict(item_sets),
        "indexes": {
            "itemToEnemies": sorted_dict(dict(item_to_enemies)),
            "itemToChestProfiles": sorted_dict(dict(item_to_chest_profiles)),
        },
        "issues": issues,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote compiled loot data to {out_path}", flush=True)
    print(f"[INFO] Enemy entries: {len(enemies)}", flush=True)
    print(f"[INFO] Chest profiles: {len(chests)}", flush=True)
    print(f"[INFO] Item sets: {len(item_sets)}", flush=True)
    print(
        "[INFO] Issues: "
        f"missingFiles={len(issues['missingFiles'])}, "
        f"parseErrors={len(issues['parseErrors'])}, "
        f"missingReferences={len(issues['missingReferences'])}",
        flush=True,
    )
    print("[DEBUG] CompileLootData finished", flush=True)


if __name__ == "__main__":
    main()
