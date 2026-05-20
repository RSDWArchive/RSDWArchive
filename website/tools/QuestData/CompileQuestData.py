"""Compile quest definitions and quest flow exports into QuestData.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import defaultdict, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from compiledata import (  # noqa: E402
    ItemDisplayCache,
    load_item_name_table,
    parse_object_name_inner,
    resolve_item_display_from_object_path,
    resolve_localized_plain,
)

INDENT = 2
SOURCE_DIR_ENV_VAR = "RSDW_QUEST_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"

QUEST_GLOB = "Quest_*.json"
FLOW_GLOB = "QF_*.json"
PROGRESSION_QUESTS_FILE = "DT_Progression_Quests.json"

ITEM_REQUIREMENT_TYPES = {
    "QFR_PlayerHasItem_C",
    "QFR_PlayerHasItemAmount_C",
}
ITEM_CHECK_TYPES = {
    "QFR_PlayerHasItem_C",
    "QFR_PlayerHasItemAmount_C",
    "QFR_PlayerHasLessThanItemAmount_C",
    "QFR_PlayerDoesntHaveItem_C",
}
INVENTORY_SPACE_CHECK_TYPES = {
    "QFR_PlayerDoesntHaveSpaceForItem_C",
    "QFR_PlayerHasSpaceForItem_C",
}
ITEM_REWARD_TYPES = {
    "QFT_GiveItemToPlayer_C",
    "QFT_GiveItemsToPlayer_C",
}
ITEM_CONSUME_TYPES = {
    "QFT_TakeItemFromPlayer_C",
    "QFT_TakeItemAmountFromPlayer_C",
}
RECIPE_CHECK_TYPES = {
    "QFR_PlayerHasRecipeUnlocked_C",
    "QFR_PlayerDoesntHaveRecipeUnlocked_C",
}
LOCAL_FLOW_FALLBACK_TYPES = (
    ITEM_CHECK_TYPES
    | INVENTORY_SPACE_CHECK_TYPES
    | ITEM_REWARD_TYPES
    | ITEM_CONSUME_TYPES
    | RECIPE_CHECK_TYPES
    | {
        "QFT_GiveCraftingRecipe_C",
    }
)
PRIMARY_QUEST_NODE_TYPES = {
    "QFT_GiveQuest_C",
    "QFT_CompleteQuest_C",
    "QFT_CompleteQuests_C",
    "QFT_CompleteQuest_RestlessGhost_C",
    "QFT_SetQuestObjective_C",
    "QFT_SetQuestBool_C",
    "QFT_ModifyQuestInt_C",
    "QFT_UpdateQuestLocation_C",
}
OWNER_QUEST_NODE_TYPES = {
    "QFT_GiveQuest_C",
    "QFT_CompleteQuest_C",
    "QFT_CompleteQuests_C",
    "QFT_CompleteQuest_RestlessGhost_C",
}
QUEST_PREREQUISITE_TYPES = {
    "QFR_HasQuestState_C",
    "QFR_DoesNotHaveQuestState_C",
}


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


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def clean_enum(value: Any) -> Any:
    if isinstance(value, str) and "::" in value:
        return value.rsplit("::", 1)[1]
    return value


def read_export_list(path: Path) -> tuple[list[dict[str, Any]] | None, str | None]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if not isinstance(raw, list):
        return None, "expected top-level list"
    out = [entry for entry in raw if isinstance(entry, dict)]
    if len(out) != len(raw):
        return None, "expected every top-level export to be an object"
    return out, None


def rel_path(path: Path, root: Path) -> str:
    return str(path.relative_to(root)).replace("\\", "/")


def normalize_package_path(object_path: Any) -> str:
    value = str(object_path or "").strip()
    if not value:
        return ""

    if re.search(r"\.\d+$", value):
        value = value.rsplit(".", 1)[0]

    if value.startswith("RSDragonwilds/"):
        return value
    if value.startswith("/Game/"):
        return f"RSDragonwilds/Content/{value[len('/Game/'):]}"

    plugin_match = re.match(r"^/([^/]+)/(.+)$", value)
    if plugin_match:
        plugin_name, rest = plugin_match.groups()
        return f"RSDragonwilds/Plugins/GameFeatures/{plugin_name}/Content/{rest}"

    return value.lstrip("/")


def table_id_to_json_path(source_root: Path, table_id: Any) -> Path | None:
    if not isinstance(table_id, str) or not table_id.strip():
        return None
    package = table_id.split(".", 1)[0]
    package_path = normalize_package_path(package)
    if not package_path:
        return None
    return source_root / f"{package_path}.json"


def get_tag_name(value: Any) -> str | None:
    if isinstance(value, dict):
        tag = value.get("TagName")
        if isinstance(tag, str) and tag != "None":
            return tag
    return None


def object_ref_payload(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    object_name = value.get("ObjectName")
    object_path = value.get("ObjectPath")
    if not isinstance(object_name, str) or "'" not in object_name:
        return None
    return {
        "objectName": object_name,
        "objectPath": object_path,
        "id": parse_object_name_inner(object_name),
        "normalizedObjectPath": normalize_package_path(object_path),
    }


def walk_object_refs(value: Any) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    if isinstance(value, dict):
        ref = object_ref_payload(value)
        if ref:
            out.append(ref)
        for child in value.values():
            out.extend(walk_object_refs(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(walk_object_refs(child))
    return out


def load_string_table(
    path: Path,
    cache: dict[str, dict[str, str] | None],
) -> dict[str, str] | None:
    key = str(path)
    if key in cache:
        return cache[key]
    if not path.exists():
        cache[key] = None
        return None
    raw, err = read_export_list(path)
    if err or raw is None:
        cache[key] = None
        return None
    merged: dict[str, str] = {}
    for export in raw:
        st = export.get("StringTable")
        if not isinstance(st, dict):
            continue
        entries = st.get("KeysToEntries")
        if isinstance(entries, dict):
            merged.update({str(k): str(v) for k, v in entries.items()})
    cache[key] = merged if merged else None
    return cache[key]


def resolve_text(
    text_obj: Any,
    source_root: Path,
    repo_root: Path,
    string_cache: dict[str, dict[str, str] | None],
    issues: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any]:
    table_id = text_obj.get("TableId") if isinstance(text_obj, dict) else None
    key = text_obj.get("Key") if isinstance(text_obj, dict) else None
    resolved = resolve_localized_plain(text_obj)
    if not resolved and isinstance(text_obj, dict):
        culture_invariant = text_obj.get("CultureInvariantString")
        if isinstance(culture_invariant, str) and culture_invariant.strip():
            resolved = culture_invariant.strip()
    if resolved:
        return {
            "text": resolved,
            "source": "inline",
            "tableId": table_id,
            "key": key,
        }

    if not isinstance(table_id, str) or not isinstance(key, str):
        issues.append({**context, "reason": "missing text, table id, or key"})
        return {
            "text": None,
            "source": None,
            "tableId": table_id,
            "key": key,
        }

    table_path = table_id_to_json_path(source_root, table_id)
    if table_path is None:
        issues.append({**context, "tableId": table_id, "key": key, "reason": "unmapped table id"})
        return {
            "text": None,
            "source": None,
            "tableId": table_id,
            "key": key,
        }

    entries = load_string_table(table_path, string_cache)
    if entries and key in entries:
        return {
            "text": entries[key],
            "source": "stringTable",
            "tableId": table_id,
            "key": key,
            "sourceFile": rel_path(table_path, repo_root) if table_path.is_relative_to(repo_root) else str(table_path),
        }

    issues.append(
        {
            **context,
            "tableId": table_id,
            "key": key,
            "sourceFile": rel_path(table_path, repo_root) if table_path.is_relative_to(repo_root) else str(table_path),
            "reason": "string table key not found",
        }
    )
    return {
        "text": None,
        "source": None,
        "tableId": table_id,
        "key": key,
    }


def resolve_optional_text(
    text_obj: Any,
    source_root: Path,
    repo_root: Path,
    string_cache: dict[str, dict[str, str] | None],
    issues: list[dict[str, Any]],
    context: dict[str, Any],
) -> dict[str, Any] | None:
    if not isinstance(text_obj, dict):
        return None
    return resolve_text(text_obj, source_root, repo_root, string_cache, issues, context)


def quest_ref_keys_for_path(path: Path, source_root: Path) -> list[str]:
    package_path = rel_path(path.with_suffix(""), source_root)
    keys = [package_path, f"{package_path}.0"]
    parts = package_path.split("/")
    if len(parts) >= 5 and parts[:3] == ["RSDragonwilds", "Plugins", "GameFeatures"] and parts[4] == "Content":
        plugin = parts[3]
        plugin_rel = "/".join(parts[5:])
        keys.extend([f"/{plugin}/{plugin_rel}", f"/{plugin}/{plugin_rel}.0"])
    if len(parts) >= 3 and parts[:2] == ["RSDragonwilds", "Content"]:
        game_rel = "/".join(parts[2:])
        keys.extend([f"/Game/{game_rel}", f"/Game/{game_rel}.0"])
    return keys


def resolve_quest_id_from_ref(
    value: Any,
    quest_id_by_ref: dict[str, str],
) -> str | None:
    ref = object_ref_payload(value)
    if not ref:
        return None
    object_name = str(ref["objectName"])
    if "QuestData'" not in object_name:
        return None
    inner = ref["id"]
    if inner in quest_id_by_ref:
        return quest_id_by_ref[inner]
    object_path = str(value.get("ObjectPath") or "")
    for key in (object_path, normalize_package_path(object_path), f"{normalize_package_path(object_path)}.0"):
        if key in quest_id_by_ref:
            return quest_id_by_ref[key]
    return inner if isinstance(inner, str) and inner.startswith("Quest_") else None


def collect_quest_ids(value: Any, quest_id_by_ref: dict[str, str]) -> set[str]:
    out: set[str] = set()
    if isinstance(value, dict):
        qid = resolve_quest_id_from_ref(value, quest_id_by_ref)
        if qid:
            out.add(qid)
        for child in value.values():
            out.update(collect_quest_ids(child, quest_id_by_ref))
    elif isinstance(value, list):
        for child in value:
            out.update(collect_quest_ids(child, quest_id_by_ref))
    return out


def build_item_payload(
    ref: Any,
    amount: Any,
    source_root: Path,
    st_item_names: dict[str, str],
    item_display_name_cache: ItemDisplayCache,
) -> dict[str, Any] | None:
    payload = object_ref_payload(ref)
    if not payload:
        return None

    object_name = str(payload["objectName"])
    object_path = str(payload.get("objectPath") or "")
    normalized_object_path = str(payload.get("normalizedObjectPath") or "")
    item_id = str(payload["id"])
    display_name, display_source = resolve_item_display_from_object_path(
        source_root,
        normalized_object_path,
        item_id,
        st_item_names,
        item_display_name_cache,
    )
    out = {
        "itemId": item_id,
        "itemDisplayName": display_name,
        "itemDisplayNameSource": display_source,
        "itemObjectName": object_name,
        "itemObjectPath": object_path,
        "normalizedObjectPath": normalized_object_path,
    }
    if amount is not None:
        out["amount"] = amount
    return out


def build_recipe_payload(ref: Any) -> dict[str, Any] | None:
    payload = object_ref_payload(ref)
    if not payload:
        return None
    return {
        "recipeId": payload["id"],
        "recipeObjectName": payload["objectName"],
        "recipeObjectPath": payload.get("objectPath"),
        "normalizedObjectPath": payload.get("normalizedObjectPath"),
    }


def node_ref(flow_rel: str, export: dict[str, Any], graph_order: int | None) -> dict[str, Any]:
    props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
    return {
        "flowFile": flow_rel,
        "nodeName": export.get("Name"),
        "nodeType": export.get("Type"),
        "nodeGuid": props.get("Compiled_NodeGUID"),
        "graphOrder": graph_order,
    }


def build_graph_order(exports: list[dict[str, Any]]) -> dict[str, int]:
    guid_to_export: dict[str, dict[str, Any]] = {}
    starts: list[str] = []
    for export in exports:
        props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
        guid = props.get("Compiled_NodeGUID")
        if isinstance(guid, str):
            guid_to_export[guid] = export
        if export.get("Type") == "ConversationDatabase":
            for entry in props.get("EntryTags", []) if isinstance(props.get("EntryTags"), list) else []:
                if isinstance(entry, dict):
                    starts.extend([str(x) for x in entry.get("DestinationList", []) if isinstance(x, str)])

    order: dict[str, int] = {}
    queue: deque[str] = deque(starts)
    while queue:
        guid = queue.popleft()
        if guid in order:
            continue
        export = guid_to_export.get(guid)
        if export is None:
            continue
        order[guid] = len(order)
        props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
        for nxt in props.get("OutputConnections", []) if isinstance(props.get("OutputConnections"), list) else []:
            if isinstance(nxt, str) and nxt not in order:
                queue.append(nxt)

    for export in exports:
        props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
        guid = props.get("Compiled_NodeGUID")
        if isinstance(guid, str) and guid not in order:
            order[guid] = len(order)
    return order


def add_unique_list_entry(items: list[dict[str, Any]], entry: dict[str, Any]) -> None:
    if entry not in items:
        items.append(entry)


def add_step(quest: dict[str, Any], kind: str, source: dict[str, Any], details: dict[str, Any]) -> None:
    quest["orderedSteps"].append(
        {
            "kind": kind,
            **source,
            "details": details,
        }
    )


def index_add(index: dict[str, set[str]], key: Any, quest_id: str) -> None:
    if isinstance(key, str) and key:
        index[key].add(quest_id)


def compile_catalog(
    source_root: Path,
    repo_root: Path,
    issues: dict[str, list[dict[str, Any]]],
) -> tuple[dict[str, Any], dict[str, str]]:
    quests: dict[str, Any] = {}
    quest_id_by_ref: dict[str, str] = {}
    string_cache: dict[str, dict[str, str] | None] = {}

    for path in sorted(source_root.rglob(QUEST_GLOB)):
        raw, err = read_export_list(path)
        source_file = rel_path(path, repo_root) if path.is_relative_to(repo_root) else str(path)
        if err or raw is None:
            issues["parseErrors"].append({"path": source_file, "error": err})
            continue
        export = next((entry for entry in raw if entry.get("Type") == "QuestData"), None)
        if not export:
            continue
        quest_id = str(export.get("Name") or path.stem)
        props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}

        name_text = resolve_text(
            props.get("QuestName"),
            source_root,
            repo_root,
            string_cache,
            issues["unresolvedText"],
            {"questId": quest_id, "field": "QuestName", "path": source_file},
        )
        description_text = resolve_text(
            props.get("QuestDescription"),
            source_root,
            repo_root,
            string_cache,
            issues["unresolvedText"],
            {"questId": quest_id, "field": "QuestDescription", "path": source_file},
        )

        objectives: list[dict[str, Any]] = []
        for idx, obj in enumerate(props.get("ObjectiveTexts", []) if isinstance(props.get("ObjectiveTexts"), list) else []):
            if not isinstance(obj, dict):
                continue
            objective_id = obj.get("Key")
            resolved = resolve_text(
                obj.get("Value"),
                source_root,
                repo_root,
                string_cache,
                issues["unresolvedText"],
                {"questId": quest_id, "field": f"ObjectiveTexts[{idx}]", "path": source_file},
            )
            objectives.append(
                {
                    "order": idx,
                    "id": objective_id,
                    "text": resolved["text"],
                    "textRef": {
                        "tableId": resolved.get("tableId"),
                        "key": resolved.get("key"),
                        "source": resolved.get("source"),
                        "sourceFile": resolved.get("sourceFile"),
                    },
                }
            )

        quest = {
            "id": quest_id,
            "internalName": props.get("InternalName"),
            "persistenceId": props.get("PersistenceID"),
            "displayName": name_text["text"],
            "description": description_text["text"],
            "questRegion": clean_enum(props.get("QuestRegion")),
            "isMainQuest": bool(props.get("bIsMainQuest", False)),
            "objectives": objectives,
            "flowFiles": [],
            "entryPoints": [],
            "orderedSteps": [],
            "itemRequirements": [],
            "itemChecks": [],
            "inventorySpaceChecks": [],
            "itemRewards": [],
            "itemConsumes": [],
            "recipeRewards": [],
            "recipeChecks": [],
            "questLocations": [],
            "questPrerequisites": [],
            "crossQuestRefs": [],
            "stateChanges": [],
            "questVariables": [],
            "dialogueRefs": [],
            "progressionTriggers": [],
            "source": {
                "file": source_file,
                "exportName": export.get("Name"),
                "exportType": export.get("Type"),
            },
        }
        quests[quest_id] = quest
        quest_id_by_ref[quest_id] = quest_id
        for key in quest_ref_keys_for_path(path, source_root):
            quest_id_by_ref[key] = quest_id

    return quests, quest_id_by_ref


def target_quests_for_node(
    props: dict[str, Any],
    flow_quest_ids: set[str],
    quest_id_by_ref: dict[str, str],
) -> set[str]:
    explicit = collect_quest_ids(props, quest_id_by_ref)
    if explicit:
        return explicit
    return set(flow_quest_ids)


def source_dir_parts(rel: str) -> tuple[str, ...]:
    parts = tuple(part for part in rel.replace("\\", "/").split("/") if part)
    if len(parts) >= 3 and parts[1] == "json":
        return parts[2:-1]
    return parts[:-1]


def parts_are_related(left: tuple[str, ...], right: tuple[str, ...]) -> bool:
    if not left or not right:
        return False
    shorter, longer = (left, right) if len(left) <= len(right) else (right, left)
    return longer[: len(shorter)] == shorter


def local_flow_quest_ids(
    flow_rel: str,
    flow_quest_ids: set[str],
    quests: dict[str, Any],
) -> set[str]:
    flow_dir = source_dir_parts(flow_rel)
    out: set[str] = set()
    for quest_id in flow_quest_ids:
        quest_source = quests.get(quest_id, {}).get("source") or {}
        quest_file = quest_source.get("file")
        if not isinstance(quest_file, str):
            continue
        if parts_are_related(flow_dir, source_dir_parts(quest_file)):
            out.add(quest_id)
    return out


def primary_quest_ids_for_flow(
    exports: list[dict[str, Any]],
    quest_id_by_ref: dict[str, str],
) -> set[str]:
    owners: set[str] = set()
    primary: set[str] = set()
    for export in exports:
        props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
        if export.get("Type") in OWNER_QUEST_NODE_TYPES:
            owners.update(collect_quest_ids(props, quest_id_by_ref))
        if export.get("Type") not in PRIMARY_QUEST_NODE_TYPES:
            continue
        primary.update(collect_quest_ids(props, quest_id_by_ref))
    return owners or primary


def compile_flow_files(
    source_root: Path,
    repo_root: Path,
    quests: dict[str, Any],
    quest_id_by_ref: dict[str, str],
    st_item_names: dict[str, str],
    item_display_name_cache: ItemDisplayCache,
    indexes: dict[str, dict[str, set[str]]],
    issues: dict[str, list[dict[str, Any]]],
) -> int:
    string_cache: dict[str, dict[str, str] | None] = {}
    flow_count = 0

    for path in sorted(source_root.rglob(FLOW_GLOB)):
        if "\\QuestFlow\\" in str(path) or "/QuestFlow/" in path.as_posix():
            continue
        raw, err = read_export_list(path)
        flow_rel = rel_path(path, repo_root) if path.is_relative_to(repo_root) else str(path)
        if err or raw is None:
            issues["parseErrors"].append({"path": flow_rel, "error": err})
            continue
        database = next((entry for entry in raw if entry.get("Type") == "ConversationDatabase"), None)
        if not database:
            continue
        flow_count += 1

        flow_name = str(database.get("Name") or path.stem)
        all_flow_quest_ids = {qid for qid in collect_quest_ids(raw, quest_id_by_ref) if qid in quests}
        primary_flow_quest_ids = {qid for qid in primary_quest_ids_for_flow(raw, quest_id_by_ref) if qid in quests}
        flow_quest_ids = primary_flow_quest_ids or all_flow_quest_ids
        cross_quest_ids = all_flow_quest_ids - flow_quest_ids
        local_quest_ids = local_flow_quest_ids(flow_rel, flow_quest_ids, quests)
        graph_order = build_graph_order(raw)
        db_props = database.get("Properties") if isinstance(database.get("Properties"), dict) else {}
        db_entry_tags: list[str] = []
        for entry in db_props.get("EntryTags", []) if isinstance(db_props.get("EntryTags"), list) else []:
            if isinstance(entry, dict):
                tag = get_tag_name(entry.get("EntryTag"))
                if tag:
                    db_entry_tags.append(tag)

        for quest_id in flow_quest_ids:
            flow_meta = {
                "file": flow_rel,
                "name": flow_name,
                "questRefs": sorted(flow_quest_ids),
                "crossQuestRefs": sorted(cross_quest_ids),
                "entryTags": sorted(set(db_entry_tags)),
                "nodeCount": len(raw),
            }
            add_unique_list_entry(quests[quest_id]["flowFiles"], flow_meta)
            indexes["questToFlowFiles"][quest_id].add(flow_rel)
            for cross_quest_id in sorted(cross_quest_ids):
                add_unique_list_entry(
                    quests[quest_id]["crossQuestRefs"],
                    {
                        "questId": cross_quest_id,
                        "flowFile": flow_rel,
                        "relationship": "referencedByFlow",
                    },
                )

        for export in raw:
            typ = export.get("Type")
            if not isinstance(typ, str):
                continue
            props = export.get("Properties") if isinstance(export.get("Properties"), dict) else {}
            guid = props.get("Compiled_NodeGUID")
            source = node_ref(flow_rel, export, graph_order.get(guid) if isinstance(guid, str) else None)
            explicit_node_quest_ids = {qid for qid in collect_quest_ids(props, quest_id_by_ref) if qid in quests}
            if typ.startswith("QFR_"):
                node_quest_ids = set(flow_quest_ids)
            else:
                node_quest_ids = explicit_node_quest_ids or set(flow_quest_ids)
            if typ in LOCAL_FLOW_FALLBACK_TYPES and not explicit_node_quest_ids:
                node_quest_ids = set(local_quest_ids)
            if not node_quest_ids:
                continue

            if typ == "ConversationEntryPointNode":
                tag = get_tag_name(props.get("EntryTag"))
                if tag:
                    for quest_id in node_quest_ids:
                        entry = {**source, "entryTag": tag}
                        add_unique_list_entry(quests[quest_id]["entryPoints"], entry)
                        indexes["entryTagToQuests"][tag].add(quest_id)
                continue

            if typ == "ConversationChoiceNode":
                resolved = resolve_optional_text(
                    props.get("DefaultChoiceDisplayText"),
                    source_root,
                    repo_root,
                    string_cache,
                    issues["unresolvedText"],
                    {"flowFile": flow_rel, "node": export.get("Name"), "field": "DefaultChoiceDisplayText"},
                )
                if resolved is None:
                    continue
                for quest_id in node_quest_ids:
                    quests[quest_id]["dialogueRefs"].append(
                        {
                            **source,
                            "kind": "choice",
                            "text": resolved.get("text"),
                            "textRef": {
                                "tableId": resolved.get("tableId"),
                                "key": resolved.get("key"),
                                "source": resolved.get("source"),
                                "sourceFile": resolved.get("sourceFile"),
                            },
                        }
                    )
                continue

            if typ == "QFT_PromptMessage_C":
                resolved = resolve_optional_text(
                    props.get("Message"),
                    source_root,
                    repo_root,
                    string_cache,
                    issues["unresolvedText"],
                    {"flowFile": flow_rel, "node": export.get("Name"), "field": "Message"},
                )
                if resolved is None:
                    continue
                for quest_id in node_quest_ids:
                    quests[quest_id]["dialogueRefs"].append(
                        {
                            **source,
                            "kind": "prompt",
                            "text": resolved.get("text"),
                            "textRef": {
                                "tableId": resolved.get("tableId"),
                                "key": resolved.get("key"),
                                "source": resolved.get("source"),
                                "sourceFile": resolved.get("sourceFile"),
                            },
                        }
                    )
                continue

            if typ in QUEST_PREREQUISITE_TYPES:
                referenced_quests = sorted(collect_quest_ids(props, quest_id_by_ref))
                details = {
                    "condition": typ.removesuffix("_C"),
                    "referencedQuests": referenced_quests,
                    "questState": clean_enum(props.get("QuestState")),
                }
                for quest_id in node_quest_ids:
                    quests[quest_id]["questPrerequisites"].append({**source, **details})
                    for referenced_quest in referenced_quests:
                        if referenced_quest != quest_id:
                            add_unique_list_entry(
                                quests[quest_id]["crossQuestRefs"],
                                {
                                    "questId": referenced_quest,
                                    "flowFile": flow_rel,
                                    "nodeName": export.get("Name"),
                                    "nodeType": typ,
                                    "relationship": "prerequisite",
                                },
                            )
                continue

            if typ == "QFT_SetQuestObjective_C":
                details = {
                    "textName": props.get("TextName"),
                    "questRefs": sorted(collect_quest_ids(props, quest_id_by_ref)),
                }
                for quest_id in node_quest_ids:
                    quests[quest_id]["stateChanges"].append({**source, "kind": "setObjective", **details})
                    add_step(quests[quest_id], "setObjective", source, details)
                continue

            if typ in {"QFT_GiveQuest_C", "QFT_CompleteQuest_C", "QFT_CompleteQuests_C", "QFT_CompleteQuest_RestlessGhost_C"}:
                details = {
                    "questRefs": sorted(collect_quest_ids(props, quest_id_by_ref)),
                    "silent": props.get("Silent"),
                }
                for quest_id in node_quest_ids:
                    quests[quest_id]["stateChanges"].append({**source, "kind": typ.removesuffix("_C"), **details})
                    add_step(quests[quest_id], typ.removesuffix("_C"), source, details)
                continue

            if typ in {"QFT_SetQuestBool_C", "QFT_ModifyQuestInt_C", "QFR_TestQuestBool_C", "QFR_TestQuestInt_C"}:
                details = {
                    "questRefs": sorted(collect_quest_ids(props, quest_id_by_ref)),
                    "boolName": props.get("BoolName") or props.get("Quest Bool Name"),
                    "intName": props.get("Name") or props.get("Quest Int Name"),
                    "newValue": props.get("NewValue"),
                    "testValue": props.get("TestValue"),
                    "modifierValue": props.get("ModifierValue"),
                }
                for quest_id in node_quest_ids:
                    quests[quest_id]["questVariables"].append({**source, **details})
                continue

            if typ in ITEM_REWARD_TYPES:
                entries: list[tuple[Any, Any]] = []
                if typ == "QFT_GiveItemsToPlayer_C":
                    for item_entry in props.get("ItemData", []) if isinstance(props.get("ItemData"), list) else []:
                        if isinstance(item_entry, dict):
                            entries.append((item_entry.get("ItemData"), item_entry.get("Count")))
                else:
                    entries.append((props.get("ItemData"), props.get("Amount", 1)))
                for item_ref, amount in entries:
                    item = build_item_payload(item_ref, amount, source_root, st_item_names, item_display_name_cache)
                    if not item:
                        continue
                    entry = {**source, "item": item}
                    for quest_id in node_quest_ids:
                        quests[quest_id]["itemRewards"].append(entry)
                        index_add(indexes["itemToRewardedByQuests"], item["itemId"], quest_id)
                        add_step(quests[quest_id], "itemReward", source, {"item": item})
                continue

            if typ in ITEM_CONSUME_TYPES:
                item = build_item_payload(
                    props.get("ItemData"),
                    props.get("Amount", 1),
                    source_root,
                    st_item_names,
                    item_display_name_cache,
                )
                if item:
                    entry = {**source, "item": item}
                    for quest_id in node_quest_ids:
                        quests[quest_id]["itemConsumes"].append(entry)
                        index_add(indexes["itemToConsumedByQuests"], item["itemId"], quest_id)
                        add_step(quests[quest_id], "itemConsume", source, {"item": item})
                continue

            if typ in ITEM_CHECK_TYPES or typ in INVENTORY_SPACE_CHECK_TYPES:
                item = build_item_payload(
                    props.get("ItemData"),
                    props.get("Amount"),
                    source_root,
                    st_item_names,
                    item_display_name_cache,
                )
                if item:
                    condition = typ.removesuffix("_C")
                    entry = {**source, "condition": condition, "item": item}
                    for quest_id in node_quest_ids:
                        if typ in INVENTORY_SPACE_CHECK_TYPES:
                            quests[quest_id]["inventorySpaceChecks"].append(entry)
                            index_add(indexes["itemToInventorySpaceCheckedByQuests"], item["itemId"], quest_id)
                            continue
                        quests[quest_id]["itemChecks"].append(entry)
                        index_add(indexes["itemToCheckedByQuests"], item["itemId"], quest_id)
                        if typ in ITEM_REQUIREMENT_TYPES:
                            quests[quest_id]["itemRequirements"].append(entry)
                            index_add(indexes["itemToRequiredByQuests"], item["itemId"], quest_id)
                continue

            if typ == "QFT_GiveCraftingRecipe_C":
                recipes: list[dict[str, Any]] = []
                for ref in walk_object_refs(props):
                    if "RecipeData'" not in str(ref.get("objectName")):
                        continue
                    recipe = build_recipe_payload(
                        {
                            "ObjectName": ref.get("objectName"),
                            "ObjectPath": ref.get("objectPath"),
                        }
                    )
                    if recipe and recipe not in recipes:
                        recipes.append(recipe)
                for recipe in recipes:
                    entry = {**source, "recipe": recipe}
                    for quest_id in node_quest_ids:
                        quests[quest_id]["recipeRewards"].append(entry)
                        index_add(indexes["recipeToRewardedByQuests"], recipe["recipeId"], quest_id)
                        add_step(quests[quest_id], "recipeReward", source, {"recipe": recipe})
                continue

            if typ in RECIPE_CHECK_TYPES:
                recipe = build_recipe_payload(props.get("RecipeData"))
                if recipe:
                    entry = {**source, "condition": typ.removesuffix("_C"), "recipe": recipe}
                    for quest_id in node_quest_ids:
                        quests[quest_id]["recipeChecks"].append(entry)
                continue

            if typ == "QFT_UpdateQuestLocation_C":
                details = {
                    "locationName": props.get("Quest Location Name"),
                    "revealed": props.get("Revealed"),
                }
                for quest_id in node_quest_ids:
                    quests[quest_id]["questLocations"].append({**source, **details})
                    add_step(quests[quest_id], "questLocation", source, details)
                continue

    return flow_count


def compile_progression_triggers(
    source_root: Path,
    repo_root: Path,
    quests: dict[str, Any],
    quest_id_by_ref: dict[str, str],
    st_item_names: dict[str, str],
    item_display_name_cache: ItemDisplayCache,
    indexes: dict[str, dict[str, set[str]]],
    issues: dict[str, list[dict[str, Any]]],
) -> int:
    matches = sorted(source_root.rglob(PROGRESSION_QUESTS_FILE))
    if not matches:
        issues["missingFiles"].append({"file": PROGRESSION_QUESTS_FILE})
        return 0
    path = matches[0]
    raw, err = read_export_list(path)
    source_file = rel_path(path, repo_root) if path.is_relative_to(repo_root) else str(path)
    if err or raw is None:
        issues["parseErrors"].append({"path": source_file, "error": err})
        return 0
    table = raw[0] if raw else {}
    rows = table.get("Rows") if isinstance(table.get("Rows"), dict) else {}
    for row_name, row in rows.items():
        if not isinstance(row, dict):
            continue
        trigger_items: list[dict[str, Any]] = []
        for ref in walk_object_refs(row.get("UnlockQuery")):
            if "ItemData'" not in str(ref.get("objectName")):
                continue
            item = build_item_payload(
                {
                    "ObjectName": ref.get("objectName"),
                    "ObjectPath": ref.get("objectPath"),
                },
                None,
                source_root,
                st_item_names,
                item_display_name_cache,
            )
            if item and item not in trigger_items:
                trigger_items.append(item)
        for change in row.get("ChangedQuests", []) if isinstance(row.get("ChangedQuests"), list) else []:
            if not isinstance(change, dict):
                continue
            quest_id = resolve_quest_id_from_ref(change.get("QuestData"), quest_id_by_ref)
            if not quest_id or quest_id not in quests:
                continue
            trigger = {
                "rowName": row_name,
                "unlockQueryString": row.get("UnlockQueryString"),
                "triggerItems": trigger_items,
                "shouldAdvanceQuest": change.get("bShouldAdvanceQuest"),
                "questState": clean_enum(change.get("QuestState")),
                "questBoolValues": change.get("QuestBoolValues", []),
                "questIntValues": change.get("QuestIntValues", []),
                "questObjectives": change.get("QuestObjectives", []),
                "questLocations": change.get("QuestLocations", []),
                "conversationEntryPointTag": get_tag_name(change.get("ConversationEntryPointTag")),
                "conversationParticipantTag": get_tag_name(change.get("ConversationParticipantTag")),
                "source": {
                    "table": "DT_Progression_Quests",
                    "file": source_file,
                },
            }
            quests[quest_id]["progressionTriggers"].append(trigger)
            indexes["progressionRowToQuests"][str(row_name)].add(quest_id)
    return len(rows)


def finalize_quests(quests: dict[str, Any]) -> None:
    for quest in quests.values():
        for key in (
            "flowFiles",
            "entryPoints",
            "orderedSteps",
            "itemRequirements",
            "itemChecks",
            "inventorySpaceChecks",
            "itemRewards",
            "itemConsumes",
            "recipeRewards",
            "recipeChecks",
            "questLocations",
            "questPrerequisites",
            "crossQuestRefs",
            "stateChanges",
            "questVariables",
            "dialogueRefs",
            "progressionTriggers",
        ):
            values = quest.get(key)
            if isinstance(values, list):
                values.sort(
                    key=lambda entry: (
                        str(entry.get("flowFile") or ""),
                        entry.get("graphOrder") if entry.get("graphOrder") is not None else 999999,
                        str(entry.get("nodeName") or ""),
                        str(entry.get("rowName") or ""),
                    )
                )


def materialize_indexes(indexes: dict[str, dict[str, set[str]]]) -> dict[str, dict[str, list[str]]]:
    return {
        index_name: {key: sorted(values) for key, values in sorted(index.items())}
        for index_name, index in sorted(indexes.items())
    }


def build_save_lookup_indexes(quests: dict[str, Any]) -> dict[str, Any]:
    persistence_id_to_quest: dict[str, str] = {}
    objective_id_to_quest_objectives: dict[str, list[dict[str, Any]]] = defaultdict(list)
    quest_variable_to_quests: dict[str, set[str]] = defaultdict(set)

    for quest_id, quest in quests.items():
        persistence_id = quest.get("persistenceId")
        if isinstance(persistence_id, str) and persistence_id:
            persistence_id_to_quest[persistence_id] = quest_id

        for objective in quest.get("objectives", []) if isinstance(quest.get("objectives"), list) else []:
            if not isinstance(objective, dict):
                continue
            objective_id = objective.get("id")
            if not isinstance(objective_id, str) or not objective_id:
                continue
            objective_id_to_quest_objectives[objective_id].append(
                {
                    "questId": quest_id,
                    "order": objective.get("order"),
                    "text": objective.get("text"),
                }
            )

        for variable in quest.get("questVariables", []) if isinstance(quest.get("questVariables"), list) else []:
            if not isinstance(variable, dict):
                continue
            for key in ("boolName", "intName"):
                value = variable.get(key)
                if isinstance(value, str) and value:
                    quest_variable_to_quests[value].add(quest_id)

    return {
        "persistenceIdToQuest": sorted_dict(persistence_id_to_quest),
        "objectiveIdToQuestObjectives": {
            key: sorted(values, key=lambda entry: (entry["questId"], entry["order"] if entry["order"] is not None else 999999))
            for key, values in sorted(objective_id_to_quest_objectives.items())
        },
        "questVariableToQuests": {
            key: sorted(values)
            for key, values in sorted(quest_variable_to_quests.items())
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile quest definitions and quest flows into QuestData.json.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "QuestData.json"),
        help="Output path for compiled quest data JSON",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    out_path = Path(args.output)

    print("[DEBUG] CompileQuestData started", flush=True)
    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    issues: dict[str, list[dict[str, Any]]] = {
        "missingFiles": [],
        "parseErrors": [],
        "unresolvedText": [],
    }
    indexes: dict[str, dict[str, set[str]]] = {
        "itemToRequiredByQuests": defaultdict(set),
        "itemToCheckedByQuests": defaultdict(set),
        "itemToInventorySpaceCheckedByQuests": defaultdict(set),
        "itemToRewardedByQuests": defaultdict(set),
        "itemToConsumedByQuests": defaultdict(set),
        "recipeToRewardedByQuests": defaultdict(set),
        "questToFlowFiles": defaultdict(set),
        "progressionRowToQuests": defaultdict(set),
        "entryTagToQuests": defaultdict(set),
    }

    quests, quest_id_by_ref = compile_catalog(source_root, repo_root, issues)
    st_item_names = load_item_name_table(source_root)
    item_display_name_cache: ItemDisplayCache = {}

    flow_count = compile_flow_files(
        source_root,
        repo_root,
        quests,
        quest_id_by_ref,
        st_item_names,
        item_display_name_cache,
        indexes,
        issues,
    )
    progression_rows = compile_progression_triggers(
        source_root,
        repo_root,
        quests,
        quest_id_by_ref,
        st_item_names,
        item_display_name_cache,
        indexes,
        issues,
    )
    finalize_quests(quests)

    compiled_indexes: dict[str, Any] = materialize_indexes(indexes)
    compiled_indexes.update(build_save_lookup_indexes(quests))

    compiled = {
        "version": derive_version_label(source_root),
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "globs": {
            "quests": QUEST_GLOB,
            "flows": FLOW_GLOB,
            "progression": PROGRESSION_QUESTS_FILE,
        },
        "counts": {
            "quests": len(quests),
            "flowFilesParsed": flow_count,
            "progressionRows": progression_rows,
            "unresolvedText": len(issues["unresolvedText"]),
        },
        "quests": sorted_dict(quests),
        "indexes": compiled_indexes,
        "issues": issues,
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote QuestData -> {out_path}", flush=True)
    print(f"[INFO] Quests: {len(quests)}", flush=True)
    print(f"[INFO] Flow files parsed: {flow_count}", flush=True)
    print(f"[INFO] Progression rows: {progression_rows}", flush=True)
    print(
        "[INFO] Issues: "
        f"parseErrors={len(issues['parseErrors'])}, "
        f"unresolvedText={len(issues['unresolvedText'])}",
        flush=True,
    )
    print("[DEBUG] CompileQuestData finished", flush=True)


if __name__ == "__main__":
    main()
