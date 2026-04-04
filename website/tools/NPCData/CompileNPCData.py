import argparse
import json
import os
import re
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


INDENT = 2
SOURCE_DIR_ENV_VAR = "RSDW_NPC_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_source_root(repo_root: Path) -> Path:
    source_override = os.getenv(SOURCE_DIR_ENV_VAR, "").strip()
    if source_override:
        candidate = Path(source_override)
        if (candidate / "RSDragonwilds").exists():
            return candidate
        if (candidate / "json" / "RSDragonwilds").exists():
            return candidate / "json"
        return candidate

    json_override = os.getenv(JSON_ROOT_ENV_VAR, "").strip()
    if json_override:
        candidate = Path(json_override)
        if (candidate / "RSDragonwilds").exists():
            return candidate
        if (candidate / "json" / "RSDragonwilds").exists():
            return candidate / "json"
        return candidate

    candidates: list[tuple[tuple[int, ...], Path]] = []
    for json_dir in repo_root.glob("*/json"):
        if not json_dir.is_dir():
            continue
        if not (json_dir / "RSDragonwilds").exists():
            continue
        version_name = json_dir.parent.name
        if re.fullmatch(r"\d+(?:\.\d+)+", version_name):
            parsed = tuple(int(part) for part in version_name.split("."))
            candidates.append((parsed, json_dir))
    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        return candidates[0][1]

    fallback = repo_root / DEFAULT_TARGET_VERSION_FOLDER / "json"
    if (fallback / "RSDragonwilds").exists():
        return fallback

    return repo_root


def derive_version_label(source_root: Path) -> str:
    name = source_root.parent.name
    if re.fullmatch(r"\d+(?:\.\d+)+", name):
        return name
    return "unknown"


def parse_object_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    object_name = value.get("ObjectName")
    if not isinstance(object_name, str):
        return None
    if "'" in object_name:
        parts = object_name.split("'")
        if len(parts) >= 2:
            return parts[1]
    return object_name


def normalize_npc_id(blueprint_name: str) -> str:
    npc_id = blueprint_name
    npc_id = npc_id.removeprefix("BP_AI_")
    npc_id = npc_id.removesuffix("_Data")
    npc_id = npc_id.removesuffix("_Character")
    return npc_id


def choose_default_export(
    exports: list[dict[str, Any]],
    expected_name: str,
) -> dict[str, Any] | None:
    for item in exports:
        if not isinstance(item, dict):
            continue
        if item.get("Name") == expected_name:
            return item
    return None


def get_path_leaf(path_string: str) -> str:
    raw = path_string.split("/")[-1]
    return raw.split(".")[0]


def normalize_blueprint_reference(value: Any) -> str | None:
    if isinstance(value, dict):
        for key in ("AssetPathName", "ObjectPath", "ObjectName"):
            nested = normalize_blueprint_reference(value.get(key))
            if nested:
                return nested
        return None

    if not isinstance(value, str):
        return None

    text = value.strip()
    if not text:
        return None
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 2:
            text = parts[1]
    text = text.split("/")[-1]
    text = text.split(".")[0]
    if text.endswith("_C"):
        text = text[:-2]
    return text or None


def read_localized_text(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    for key in ("LocalizedString", "SourceString", "Key"):
        candidate = value.get(key)
        if isinstance(candidate, str) and candidate.strip():
            return candidate.strip()
    return None


def read_journal_records(
    journal_paths: list[Path],
    repo_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_data_blueprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []

    for path in sorted(journal_paths):
        try:
            raw = load_json(path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)})
            continue
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue

        entry = raw[0]
        props = entry.get("Properties", {})
        if not isinstance(props, dict):
            continue

        unlock = props.get("UnlockCondition", {})
        if not isinstance(unlock, dict):
            unlock = {}
        ai_data = unlock.get("AIData", {})
        data_blueprint = normalize_blueprint_reference(ai_data)
        if not data_blueprint:
            continue

        page_descriptions = props.get("PageDescriptions", [])
        descriptions: list[str] = []
        if isinstance(page_descriptions, list):
            for desc_entry in page_descriptions:
                if not isinstance(desc_entry, dict):
                    continue
                text = read_localized_text(desc_entry.get("Description"))
                if text:
                    descriptions.append(text)

        locations: list[str] = []
        raw_locations = props.get("Locations", [])
        if isinstance(raw_locations, list):
            for location in raw_locations:
                if not isinstance(location, dict):
                    continue
                location_text = read_localized_text(location.get("LocationText"))
                if location_text:
                    locations.append(location_text)
                    continue
                location_id = location.get("LocationID")
                if isinstance(location_id, str) and location_id.strip():
                    locations.append(location_id.strip())

        by_data_blueprint[data_blueprint].append(
            {
                "internalName": props.get("InternalName"),
                "displayName": read_localized_text(props.get("DisplayName")),
                "unlockType": unlock.get("UnlockType"),
                "descriptions": descriptions,
                "locations": sorted(set(locations)),
                "sourcePath": str(path.relative_to(repo_root)).replace("\\", "/"),
            }
        )

    return dict(by_data_blueprint), errors


def format_respawn_duration(value: Any) -> str | None:
    if isinstance(value, dict):
        parts: list[str] = []
        days = value.get("Days")
        hours = value.get("Hours")
        minutes = value.get("Minutes")
        if isinstance(days, (int, float)) and int(days) > 0:
            day_value = int(days)
            parts.append(f"{day_value} day" if day_value == 1 else f"{day_value} days")
        if isinstance(hours, (int, float)) and int(hours) > 0:
            hour_value = int(hours)
            parts.append(f"{hour_value} hour" if hour_value == 1 else f"{hour_value} hours")
        if isinstance(minutes, (int, float)) and int(minutes) > 0:
            minute_value = int(minutes)
            parts.append(f"{minute_value} minute" if minute_value == 1 else f"{minute_value} minutes")
        if parts:
            return " ".join(parts)
        return None
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def read_spawn_records(
    spawn_paths: list[Path],
    repo_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_character_blueprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []

    for path in sorted(spawn_paths):
        try:
            raw = load_json(path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)})
            continue
        if not isinstance(raw, list):
            continue

        default_export = choose_default_export(raw, f"Default__{path.stem}_C")
        if not isinstance(default_export, dict):
            continue
        props = default_export.get("Properties", {})
        if not isinstance(props, dict):
            continue

        character_blueprint = normalize_blueprint_reference(props.get("AIClass"))
        if not character_blueprint:
            continue

        power_level = props.get("PowerLevel")
        respawn = format_respawn_duration(props.get("RespawnDuration"))
        should_respawn = props.get("bShouldRespawn")

        by_character_blueprint[character_blueprint].append(
            {
                "spawnPath": str(path.relative_to(repo_root)).replace("\\", "/"),
                "powerLevel": power_level if isinstance(power_level, (int, float)) else None,
                "respawnDuration": respawn,
                "shouldRespawn": should_respawn if isinstance(should_respawn, bool) else None,
            }
        )

    return dict(by_character_blueprint), errors


def read_ai_data_tables(
    table_paths: list[Path],
    repo_root: Path,
) -> tuple[dict[str, float], list[dict[str, Any]]]:
    max_health_by_row: dict[str, float] = {}
    errors: list[dict[str, Any]] = []

    for path in sorted(table_paths):
        try:
            raw = load_json(path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)})
            continue
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue
        rows = raw[0].get("Rows", {})
        if not isinstance(rows, dict):
            continue
        for row_name, row_data in rows.items():
            if not isinstance(row_name, str) or not isinstance(row_data, dict):
                continue
            value = row_data.get("MaxHealth")
            if not isinstance(value, (int, float)):
                continue
            max_health_by_row.setdefault(row_name, float(value))

    return max_health_by_row, errors


def read_spawn_data_tables(
    table_paths: list[Path],
    repo_root: Path,
) -> tuple[dict[str, list[dict[str, Any]]], list[dict[str, Any]]]:
    by_character_blueprint: dict[str, list[dict[str, Any]]] = defaultdict(list)
    errors: list[dict[str, Any]] = []

    for path in sorted(table_paths):
        try:
            raw = load_json(path)
        except Exception as exc:  # noqa: BLE001
            errors.append({"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)})
            continue
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue
        rows = raw[0].get("Rows", {})
        if not isinstance(rows, dict):
            continue

        for row_data in rows.values():
            if not isinstance(row_data, dict):
                continue
            group = row_data.get("Group", [])
            if not isinstance(group, list):
                continue
            for group_item in group:
                if not isinstance(group_item, dict):
                    continue
                character_blueprint = normalize_blueprint_reference(group_item.get("AIClass"))
                if not character_blueprint:
                    continue
                power_level = group_item.get("PowerLevel")
                by_character_blueprint[character_blueprint].append(
                    {
                        "spawnPath": str(path.relative_to(repo_root)).replace("\\", "/"),
                        "powerLevel": power_level if isinstance(power_level, (int, float)) else None,
                        "respawnDuration": None,
                        "shouldRespawn": None,
                    }
                )

    return dict(by_character_blueprint), errors


def summarize_journal_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    display_name = None
    descriptions: list[str] = []
    locations: list[str] = []
    source_paths: list[str] = []

    for record in records:
        if not isinstance(record, dict):
            continue
        if not display_name:
            candidate = record.get("displayName")
            if isinstance(candidate, str) and candidate.strip():
                display_name = candidate.strip()
        rec_descriptions = record.get("descriptions", [])
        if isinstance(rec_descriptions, list):
            descriptions.extend([text for text in rec_descriptions if isinstance(text, str) and text.strip()])
        rec_locations = record.get("locations", [])
        if isinstance(rec_locations, list):
            locations.extend([text for text in rec_locations if isinstance(text, str) and text.strip()])
        source_path = record.get("sourcePath")
        if isinstance(source_path, str) and source_path:
            source_paths.append(source_path)

    out: dict[str, Any] = {
        "displayName": display_name,
        "description": "\n\n".join(dict.fromkeys(descriptions)) if descriptions else None,
        "locations": sorted(set(locations)),
        "sourcePaths": sorted(set(source_paths)),
    }
    return compact(out)


def summarize_spawn_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    power_values: list[float] = []
    respawn_values: list[str] = []
    source_paths: list[str] = []
    should_respawn_any = False
    should_respawn_all_false = True
    has_should_respawn_value = False

    for record in records:
        if not isinstance(record, dict):
            continue
        power = record.get("powerLevel")
        if isinstance(power, (int, float)):
            power_values.append(float(power))
        respawn = record.get("respawnDuration")
        if isinstance(respawn, str) and respawn.strip():
            respawn_values.append(respawn.strip())
        source_path = record.get("spawnPath")
        if isinstance(source_path, str) and source_path:
            source_paths.append(source_path)
        should_respawn = record.get("shouldRespawn")
        if isinstance(should_respawn, bool):
            has_should_respawn_value = True
            if should_respawn:
                should_respawn_any = True
            else:
                should_respawn_all_false = should_respawn_all_false and True
        else:
            should_respawn_all_false = False

    if power_values:
        low = min(power_values)
        high = max(power_values)
        if low == high:
            power_level = str(int(low)) if low.is_integer() else str(low)
        else:
            low_text = str(int(low)) if low.is_integer() else str(low)
            high_text = str(int(high)) if high.is_integer() else str(high)
            power_level = f"{low_text}-{high_text}"
    else:
        power_level = None

    out = {
        "powerLevel": power_level,
        "respawn": ", ".join(sorted(set(respawn_values))) if respawn_values else None,
        "shouldRespawn": (
            True
            if should_respawn_any
            else False
            if has_should_respawn_value and should_respawn_all_false
            else None
        ),
        "sourcePaths": sorted(set(source_paths)),
    }
    return compact(out)


def read_string_tables(
    string_table_paths: list[Path],
    repo_root: Path,
) -> tuple[dict[str, str], dict[str, list[str]], list[dict[str, Any]]]:
    merged: dict[str, str] = {}
    sources_by_key: dict[str, list[str]] = defaultdict(list)
    collisions: list[dict[str, Any]] = []

    for path in sorted(string_table_paths):
        try:
            raw = load_json(path)
        except Exception as exc:  # noqa: BLE001
            collisions.append(
                {
                    "tablePath": str(path.relative_to(repo_root)).replace("\\", "/"),
                    "error": f"Failed to parse string table: {exc}",
                }
            )
            continue

        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue
        entries = (
            raw[0]
            .get("StringTable", {})
            .get("KeysToEntries", {})
        )
        if not isinstance(entries, dict):
            continue

        rel_path = str(path.relative_to(repo_root)).replace("\\", "/")
        for key, value in entries.items():
            if not isinstance(key, str) or not isinstance(value, str):
                continue
            sources_by_key[key].append(rel_path)
            if key not in merged:
                merged[key] = value
                continue
            if merged[key] != value:
                collisions.append(
                    {
                        "key": key,
                        "existingValue": merged[key],
                        "newValue": value,
                        "fromTable": rel_path,
                    }
                )
    return merged, dict(sources_by_key), collisions


def extract_data_record(path: Path, repo_root: Path) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        raw = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return None, None, {"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)}

    if not isinstance(raw, list):
        return None, None, {"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": "Expected top-level list"}

    blueprint_name = path.stem
    default_export = choose_default_export(raw, f"Default__{blueprint_name}_C")
    if default_export is None:
        return None, None, {
            "path": str(path.relative_to(repo_root)).replace("\\", "/"),
            "error": "Missing default export object",
        }

    props = default_export.get("Properties", {})
    if not isinstance(props, dict):
        props = {}

    ai_name = props.get("AIName", {})
    if not isinstance(ai_name, dict):
        ai_name = {}

    mover = props.get("MoverConfig", {})
    if not isinstance(mover, dict):
        mover = {}

    threat = props.get("ThreatSystemConfig", {})
    if not isinstance(threat, dict):
        threat = {}

    gameplay_tags = props.get("GameplayTags", [])
    if not isinstance(gameplay_tags, list):
        gameplay_tags = []
    gameplay_tags = [tag for tag in gameplay_tags if isinstance(tag, str)]

    difficulty = props.get("AIDifficultyScalingCategoryTag", {})
    if not isinstance(difficulty, dict):
        difficulty = {}

    data_record = {
        "dataBlueprint": blueprint_name,
        "dataPath": str(path.relative_to(repo_root)).replace("\\", "/"),
        "aiName": {
            "tableId": ai_name.get("TableId"),
            "key": ai_name.get("Key"),
            "sourceString": ai_name.get("SourceString"),
            "localizedString": ai_name.get("LocalizedString"),
        },
        "classification": {
            "archetype": props.get("Archetype"),
            "difficultyTag": difficulty.get("TagName"),
            "gameplayTags": gameplay_tags,
            "isQuadruped": props.get("bIsQuadruped"),
            "isColossal": props.get("bIsColossal"),
        },
        "movement": {
            "walkSpeed": mover.get("WalkSpeed"),
            "runSpeed": mover.get("RunSpeed"),
            "preferredDistanceFromTarget": props.get("PreferredDistanceFromTarget"),
        },
        "combat": {
            "combatAttacksTable": parse_object_name(props.get("CombatAttacksTable")),
            "combatActionsTable": parse_object_name(props.get("CombatActionsTable")),
            "threat": {
                "playerThreatPriorityRadius": threat.get("PlayerThreatPriorityRadius"),
                "memoryDuration": threat.get("MemoryDuration"),
                "memoryDurationOutOfCombat": threat.get("MemoryDurationOutOfCombat"),
                "suspiciousToCombatRequiredCertainty": threat.get("SuspiciousToCombatRequiredCertainty"),
            },
        },
        "meta": {
            "aiDataRowName": (props.get("AIDataTableRowHandle") or {}).get("RowName")
            if isinstance(props.get("AIDataTableRowHandle"), dict)
            else None,
            "persistenceId": props.get("PersistenceID"),
        },
    }
    return blueprint_name, data_record, None


def extract_character_record(path: Path, repo_root: Path) -> tuple[str | None, dict[str, Any] | None, dict[str, Any] | None]:
    try:
        raw = load_json(path)
    except Exception as exc:  # noqa: BLE001
        return None, None, {"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": str(exc)}

    if not isinstance(raw, list):
        return None, None, {"path": str(path.relative_to(repo_root)).replace("\\", "/"), "error": "Expected top-level list"}

    blueprint_name = path.stem
    default_export = choose_default_export(raw, f"Default__{blueprint_name}_C")
    if default_export is None:
        return None, None, {
            "path": str(path.relative_to(repo_root)).replace("\\", "/"),
            "error": "Missing default export object",
        }

    props = default_export.get("Properties", {})
    if not isinstance(props, dict):
        props = {}

    ai_data_class = props.get("AIDataClass", {})
    ai_data_asset = ai_data_class.get("AssetPathName") if isinstance(ai_data_class, dict) else None
    linked_data_blueprint = None
    if isinstance(ai_data_asset, str) and ai_data_asset:
        linked_data_blueprint = get_path_leaf(ai_data_asset)

    max_health = None
    damage_affinities: list[dict[str, Any]] = []
    loot_row_name = None
    loot_table_name = None

    for item in raw:
        if not isinstance(item, dict):
            continue

        item_type = item.get("Type")
        item_props = item.get("Properties", {})
        if not isinstance(item_props, dict):
            item_props = {}

        if item_type == "AiHealthComponent" and max_health is None:
            value = item_props.get("MaxHealth")
            if isinstance(value, (int, float)):
                max_health = value

        if item_type == "AIAttributesComponent" and not damage_affinities:
            entries = item_props.get("DamageTypeAffinities", [])
            if isinstance(entries, list):
                for entry in entries:
                    if not isinstance(entry, dict):
                        continue
                    key = entry.get("Key", {})
                    if not isinstance(key, dict):
                        key = {}
                    damage_affinities.append(
                        {
                            "damageTypeTag": key.get("TagName"),
                            "affinity": entry.get("Value"),
                        }
                    )

        if item_type == "LootDropComponent" and loot_row_name is None:
            handle = item_props.get("EnemyTableRowHandle", {})
            if isinstance(handle, dict):
                loot_row_name = handle.get("RowName")
                dt = handle.get("DataTable", {})
                if isinstance(dt, dict):
                    loot_table_name = parse_object_name(dt)

    character_record = {
        "characterBlueprint": blueprint_name,
        "characterPath": str(path.relative_to(repo_root)).replace("\\", "/"),
        "linkedDataBlueprint": linked_data_blueprint,
        "combat": {
            "maxHealth": max_health,
            "damageTypeAffinities": damage_affinities,
        },
        "loot": {
            "enemyLootRowName": loot_row_name,
            "enemyLootTable": loot_table_name,
        },
    }
    return blueprint_name, character_record, None


def choose_display_name(
    npc_id: str,
    ai_name: dict[str, Any],
    string_values: dict[str, str],
) -> str:
    localized = ai_name.get("localizedString")
    if isinstance(localized, str) and localized.strip():
        return localized.strip()

    source = ai_name.get("sourceString")
    if isinstance(source, str) and source.strip():
        return source.strip()

    key = ai_name.get("key")
    if isinstance(key, str) and key in string_values:
        return string_values[key]

    return npc_id


def compact(value: Any) -> Any:
    if isinstance(value, dict):
        out = {}
        for key, child in value.items():
            normalized = compact(child)
            if normalized is None:
                continue
            if normalized == {}:
                continue
            if normalized == []:
                continue
            out[key] = normalized
        return out
    if isinstance(value, list):
        out_list = []
        for child in value:
            normalized = compact(child)
            if normalized is None:
                continue
            if normalized == {} or normalized == []:
                continue
            out_list.append(normalized)
        return out_list
    return value


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile NPC data into a normalized JSON payload.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "NPCData.json"),
        help="Output path for compiled NPC data JSON",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    out_path = Path(args.output)

    print("[DEBUG] CompileNPCData started", flush=True)
    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    data_paths = sorted(source_root.rglob("BP_AI_*_Data.json"))
    character_paths = sorted(source_root.rglob("BP_AI_*_Character.json"))
    string_table_paths = sorted(source_root.rglob("ST_AI_Names*.json"))
    journal_paths = sorted(source_root.rglob("JOURNAL_World_Fauna*.json"))
    spawn_paths = sorted(source_root.rglob("BP_SpawnPoint_*.json"))
    ai_data_table_paths = sorted(source_root.rglob("DT_AIData*.json"))
    ai_spawn_table_paths = sorted(source_root.rglob("DT_AISpawnData*.json"))

    print(f"[DEBUG] Data files: {len(data_paths)}", flush=True)
    print(f"[DEBUG] Character files: {len(character_paths)}", flush=True)
    print(f"[DEBUG] String tables: {len(string_table_paths)}", flush=True)
    print(f"[DEBUG] Fauna journals: {len(journal_paths)}", flush=True)
    print(f"[DEBUG] Spawn points: {len(spawn_paths)}", flush=True)
    print(f"[DEBUG] AI data tables: {len(ai_data_table_paths)}", flush=True)
    print(f"[DEBUG] AI spawn tables: {len(ai_spawn_table_paths)}", flush=True)

    string_values, string_sources, table_issues = read_string_tables(string_table_paths, repo_root)
    journals_by_data_blueprint, journal_parse_errors = read_journal_records(journal_paths, repo_root)
    spawns_by_character_blueprint, spawn_parse_errors = read_spawn_records(spawn_paths, repo_root)
    ai_data_health_by_row, ai_data_table_errors = read_ai_data_tables(ai_data_table_paths, repo_root)
    ai_spawn_by_character_blueprint, ai_spawn_table_errors = read_spawn_data_tables(ai_spawn_table_paths, repo_root)

    data_by_blueprint: dict[str, dict[str, Any]] = {}
    character_by_blueprint: dict[str, dict[str, Any]] = {}

    issues: dict[str, Any] = {
        "parseErrors": journal_parse_errors + spawn_parse_errors + ai_data_table_errors + ai_spawn_table_errors,
        "stringTableCollisions": table_issues,
        "missingLinks": [],
    }

    for path in data_paths:
        blueprint_name, record, parse_error = extract_data_record(path, repo_root)
        if parse_error:
            issues["parseErrors"].append(parse_error)
            continue
        assert blueprint_name is not None and record is not None
        data_by_blueprint[blueprint_name] = record

    for path in character_paths:
        blueprint_name, record, parse_error = extract_character_record(path, repo_root)
        if parse_error:
            issues["parseErrors"].append(parse_error)
            continue
        assert blueprint_name is not None and record is not None
        character_by_blueprint[blueprint_name] = record

    npc_records: list[dict[str, Any]] = []
    data_blueprints_referenced: set[str] = set()

    for character_blueprint, character in character_by_blueprint.items():
        linked_data_blueprint = character.get("linkedDataBlueprint")
        data = data_by_blueprint.get(linked_data_blueprint) if isinstance(linked_data_blueprint, str) else None

        if isinstance(linked_data_blueprint, str):
            data_blueprints_referenced.add(linked_data_blueprint)
            if data is None:
                issues["missingLinks"].append(
                    {
                        "type": "character->data",
                        "characterBlueprint": character_blueprint,
                        "linkedDataBlueprint": linked_data_blueprint,
                    }
                )

        npc_id = normalize_npc_id(character_blueprint)
        ai_name = data.get("aiName", {}) if isinstance(data, dict) else {}
        if not isinstance(ai_name, dict):
            ai_name = {}

        key = ai_name.get("key")
        string_table_sources = string_sources.get(key, []) if isinstance(key, str) else []

        ai_data_row_name = (
            data.get("meta", {}).get("aiDataRowName")
            if isinstance(data, dict) and isinstance(data.get("meta"), dict)
            else None
        )
        base_max_health = (
            (character.get("combat") or {}).get("maxHealth")
            if isinstance(character.get("combat"), dict)
            else None
        )
        if not isinstance(base_max_health, (int, float)) and isinstance(ai_data_row_name, str):
            fallback_health = ai_data_health_by_row.get(ai_data_row_name)
            if isinstance(fallback_health, (int, float)):
                base_max_health = fallback_health

        spawn_records = list(spawns_by_character_blueprint.get(character_blueprint, []))
        spawn_records.extend(ai_spawn_by_character_blueprint.get(character_blueprint, []))

        npc_records.append(
            {
                "id": npc_id,
                "displayName": choose_display_name(npc_id, ai_name, string_values),
                "names": {
                    "key": ai_name.get("key"),
                    "tableId": ai_name.get("tableId"),
                    "sourceString": ai_name.get("sourceString"),
                    "localizedString": ai_name.get("localizedString"),
                    "stringTableSources": string_table_sources,
                },
                "source": {
                    "dataPath": data.get("dataPath") if isinstance(data, dict) else None,
                    "characterPath": character.get("characterPath"),
                    "dataBlueprint": linked_data_blueprint,
                    "characterBlueprint": character_blueprint,
                },
                "classification": data.get("classification") if isinstance(data, dict) else {},
                "movement": data.get("movement") if isinstance(data, dict) else {},
                "combat": {
                    "maxHealth": base_max_health,
                    "damageTypeAffinities": (character.get("combat") or {}).get("damageTypeAffinities")
                    if isinstance(character.get("combat"), dict)
                    else [],
                    "combatAttacksTable": (data.get("combat") or {}).get("combatAttacksTable")
                    if isinstance(data, dict) and isinstance(data.get("combat"), dict)
                    else None,
                    "combatActionsTable": (data.get("combat") or {}).get("combatActionsTable")
                    if isinstance(data, dict) and isinstance(data.get("combat"), dict)
                    else None,
                },
                "journal": summarize_journal_records(
                    journals_by_data_blueprint.get(str(linked_data_blueprint), [])
                )
                if isinstance(linked_data_blueprint, str)
                else {},
                "spawning": summarize_spawn_records(
                    spawn_records
                ),
                "loot": character.get("loot"),
                "meta": data.get("meta") if isinstance(data, dict) else {},
            }
        )

    # Preserve data-only entries as well.
    for data_blueprint, data in data_by_blueprint.items():
        if data_blueprint in data_blueprints_referenced:
            continue
        npc_id = normalize_npc_id(data_blueprint)
        ai_name = data.get("aiName", {})
        if not isinstance(ai_name, dict):
            ai_name = {}
        key = ai_name.get("key")
        string_table_sources = string_sources.get(key, []) if isinstance(key, str) else []

        npc_records.append(
            {
                "id": npc_id,
                "displayName": choose_display_name(npc_id, ai_name, string_values),
                "names": {
                    "key": ai_name.get("key"),
                    "tableId": ai_name.get("tableId"),
                    "sourceString": ai_name.get("sourceString"),
                    "localizedString": ai_name.get("localizedString"),
                    "stringTableSources": string_table_sources,
                },
                "source": {
                    "dataPath": data.get("dataPath"),
                    "characterPath": None,
                    "dataBlueprint": data_blueprint,
                    "characterBlueprint": None,
                },
                "classification": data.get("classification"),
                "movement": data.get("movement"),
                "combat": {
                    "maxHealth": ai_data_health_by_row.get(
                        (data.get("meta") or {}).get("aiDataRowName")
                    )
                    if isinstance(data.get("meta"), dict)
                    else None,
                    "damageTypeAffinities": [],
                    "combatAttacksTable": (data.get("combat") or {}).get("combatAttacksTable")
                    if isinstance(data.get("combat"), dict)
                    else None,
                    "combatActionsTable": (data.get("combat") or {}).get("combatActionsTable")
                    if isinstance(data.get("combat"), dict)
                    else None,
                },
                "journal": summarize_journal_records(
                    journals_by_data_blueprint.get(data_blueprint, [])
                ),
                "spawning": summarize_spawn_records(
                    ai_spawn_by_character_blueprint.get(
                        normalize_blueprint_reference(data_blueprint.replace("_Data", "_Character")) or "",
                        [],
                    )
                ),
                "loot": {},
                "meta": data.get("meta"),
            }
        )

    npc_map: dict[str, dict[str, Any]] = {}
    duplicate_ids: list[str] = []
    for record in sorted(npc_records, key=lambda item: str(item.get("id"))):
        base_id = str(record.get("id"))
        npc_id = base_id
        if npc_id in npc_map:
            duplicate_ids.append(base_id)
            source = record.get("source", {})
            source_blueprint = None
            if isinstance(source, dict):
                source_blueprint = source.get("characterBlueprint") or source.get("dataBlueprint")
            source_blueprint_text = str(source_blueprint or "Variant")
            source_slug = re.sub(r"[^A-Za-z0-9_]+", "_", source_blueprint_text).strip("_")
            if not source_slug:
                source_slug = "Variant"
            npc_id = f"{base_id}__{source_slug}"
            suffix = 2
            while npc_id in npc_map:
                npc_id = f"{base_id}__{source_slug}_{suffix}"
                suffix += 1
            record["baseId"] = base_id
            record["id"] = npc_id
        npc_map[npc_id] = compact(record)

    if duplicate_ids:
        issues["missingLinks"].append(
            {
                "type": "duplicateNpcIdExpanded",
                "ids": sorted(set(duplicate_ids)),
            }
        )

    by_difficulty: dict[str, list[str]] = defaultdict(list)
    by_loot_row: dict[str, list[str]] = defaultdict(list)
    for npc_id, npc in npc_map.items():
        difficulty = (
            ((npc.get("classification") or {}).get("difficultyTag"))
            if isinstance(npc.get("classification"), dict)
            else None
        )
        if isinstance(difficulty, str) and difficulty:
            by_difficulty[difficulty].append(npc_id)

        loot = npc.get("loot")
        loot_row = None
        if isinstance(loot, dict):
            loot_row = loot.get("enemyLootRowName")
        if isinstance(loot_row, str) and loot_row:
            by_loot_row[loot_row].append(npc_id)

    for values in by_difficulty.values():
        values.sort()
    for values in by_loot_row.values():
        values.sort()

    compiled = {
        "version": derive_version_label(source_root),
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "counts": {
            "dataFilesFound": len(data_paths),
            "characterFilesFound": len(character_paths),
            "stringTablesFound": len(string_table_paths),
            "journalFilesFound": len(journal_paths),
            "spawnFilesFound": len(spawn_paths),
            "aiDataTablesFound": len(ai_data_table_paths),
            "aiSpawnTablesFound": len(ai_spawn_table_paths),
            "npcs": len(npc_map),
        },
        "npcs": sorted_dict(npc_map),
        "indexes": {
            "byDifficultyTag": sorted_dict(dict(by_difficulty)),
            "byEnemyLootRowName": sorted_dict(dict(by_loot_row)),
        },
        "issues": issues,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote compiled NPC data to {out_path}", flush=True)
    print(f"[INFO] NPC entries: {len(npc_map)}", flush=True)
    print(
        "[INFO] Issues: "
        f"parseErrors={len(issues['parseErrors'])}, "
        f"stringTableCollisions={len(issues['stringTableCollisions'])}, "
        f"missingLinks={len(issues['missingLinks'])}",
        flush=True,
    )
    print("[DEBUG] CompileNPCData finished", flush=True)


if __name__ == "__main__":
    main()
