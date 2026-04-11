"""
Dataset compile utilities.

**Enrichment helpers** — imported by `Compile*Data.py` scripts under `website/tools/` (same
directory on `sys.path`): string tables, item/skill/XP resolution, plan/building summaries, etc.

**Pipeline CLI** — when executed as `python website/tools/compiledata.py`, runs each category
compiler as a subprocess with env from `website/data.config.json`. Importing this module does
not run the pipeline.

Previously split into `compile_enrichment.py` + this file; merged so one module owns shared logic.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any

DEFAULT_CONFIG_RELATIVE = Path("website", "data.config.json")

# Per JSON file: resolved display string and optional source tag (None = loc or ST_ItemNames).
ItemDisplayCache = dict[str, tuple[str | None, str | None]]


# --- Enrichment: shared across Item / Recipe / Spell / Plan / Progression / Vestige ---


def load_item_name_table(source_root: Path) -> dict[str, str]:
    matches = list(source_root.rglob("ST_ItemNames.json"))
    if not matches:
        return {}
    try:
        raw = json.loads(matches[0].read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {}
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        return {}
    entries = raw[0].get("StringTable", {}).get("KeysToEntries", {})
    if not isinstance(entries, dict):
        return {}
    return {str(key): str(value) for key, value in entries.items()}


def parse_object_name_inner(object_name: str) -> str:
    if "'" in object_name:
        parts = object_name.split("'")
        if len(parts) >= 2:
            return parts[1]
    return object_name


def parse_item_id_from_object_name(object_name: str) -> str:
    return parse_object_name_inner(object_name)


def _title_case_words(text: str) -> str:
    parts = [p for p in re.split(r"[\s_]+", text.strip()) if p]
    if not parts:
        return ""
    out: list[str] = []
    for p in parts:
        if len(p) == 1:
            out.append(p.upper())
        else:
            out.append(p[0].upper() + p[1:].lower())
    return " ".join(out)


def _camel_key_to_display(key: str) -> str | None:
    if not key or not key[0].isalpha():
        return None
    s = re.sub(r"([a-z\d])([A-Z])", r"\1 \2", key)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    words = s.split()
    if len(words) < 1:
        return None
    return " ".join(w.capitalize() for w in words)


def item_display_fallback_from_properties(
    props: dict[str, Any],
    export_type: str | None,
) -> tuple[str | None, str | None]:
    """When Name has no loc/ST match, derive a readable label from other properties."""
    weth = props.get("WearableEquipmentDataTableRowHandle")
    if isinstance(weth, dict):
        rn = weth.get("RowName")
        if isinstance(rn, str) and rn.strip():
            return _title_case_words(rn.replace("_", " ")), "fallbackWearableRow"

    name_obj = props.get("Name")
    if isinstance(name_obj, dict):
        k = name_obj.get("Key")
        if isinstance(k, str) and k.strip():
            fake = _camel_key_to_display(k.strip())
            if fake:
                return fake, "fallbackNameKey"

    inn = props.get("InternalName")
    if isinstance(inn, str) and inn.strip():
        return _title_case_words(inn.replace("_", " ")), "fallbackInternalName"

    _ = export_type
    return None, None


def resolve_item_display_from_object_path(
    source_root: Path,
    object_path: str,
    expected_export_name: str,
    st_item_names: dict[str, str],
    cache: ItemDisplayCache,
) -> tuple[str | None, str | None]:
    if not object_path:
        return (None, None)
    package_path = object_path.rsplit(".", 1)[0]
    json_path = source_root / f"{package_path}.json"
    cache_key = str(json_path)
    if cache_key in cache:
        return cache[cache_key]
    if not json_path.exists():
        cache[cache_key] = (None, None)
        return (None, None)
    try:
        raw = json.loads(json_path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        cache[cache_key] = (None, None)
        return (None, None)
    if not isinstance(raw, list):
        cache[cache_key] = (None, None)
        return (None, None)

    target_export = None
    for entry in raw:
        if isinstance(entry, dict) and entry.get("Name") == expected_export_name:
            target_export = entry
            break
    if target_export is None and raw and isinstance(raw[0], dict):
        target_export = raw[0]
    if not isinstance(target_export, dict):
        cache[cache_key] = (None, None)
        return (None, None)

    props = target_export.get("Properties") or {}
    if not isinstance(props, dict):
        cache[cache_key] = (None, None)
        return (None, None)
    name_obj = props.get("Name")
    resolved = resolve_localized_item_name(name_obj, st_item_names)
    if resolved:
        cache[cache_key] = (resolved, None)
        return cache[cache_key]
    fb_text, fb_src = item_display_fallback_from_properties(props, target_export.get("Type"))
    if fb_text:
        cache[cache_key] = (fb_text, fb_src)
        return cache[cache_key]
    cache[cache_key] = (None, None)
    return (None, None)


def parse_data_table_stem_from_object_name(object_name: str) -> str | None:
    inner = parse_object_name_inner(object_name)
    if inner.startswith("DT_"):
        return inner
    return None


def resolve_localized_item_name(name_obj: Any, st_item_names: dict[str, str]) -> str | None:
    if not isinstance(name_obj, dict):
        return None
    for key in ("LocalizedString", "SourceString"):
        v = name_obj.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    k = name_obj.get("Key")
    if isinstance(k, str) and k in st_item_names:
        return st_item_names[k]
    return None


def resolve_localized_plain(lo: Any) -> str | None:
    """Localized text without string-table lookup (e.g. FlavourText when SourceString is set)."""
    if not isinstance(lo, dict):
        return None
    for key in ("LocalizedString", "SourceString"):
        v = lo.get(key)
        if isinstance(v, str) and v.strip():
            return v.strip()
    return None


def enrich_item_entry_display_name(entry: dict[str, Any], st_item_names: dict[str, str]) -> None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    name_obj = props.get("Name")
    resolved = resolve_localized_item_name(name_obj, st_item_names)
    src_tag: str | None = None
    if not resolved:
        resolved, src_tag = item_display_fallback_from_properties(props, entry.get("type"))
    if resolved:
        if "enrichment" not in entry:
            entry["enrichment"] = {}
        entry["enrichment"]["displayName"] = resolved
        if src_tag:
            entry["enrichment"]["displayNameSource"] = src_tag


def enrich_item_entry_flavour_text(entry: dict[str, Any]) -> None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    ft = props.get("FlavourText")
    text = resolve_localized_plain(ft)
    if text:
        if "enrichment" not in entry:
            entry["enrichment"] = {}
        entry["enrichment"]["flavourText"] = text


def enrich_item_entry_skill_used(entry: dict[str, Any], skill_names: dict[str, str]) -> None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    sk = props.get("SkillUsed")
    if not isinstance(sk, dict):
        return
    son = sk.get("ObjectName", "")
    if "SkillData'" not in str(son):
        return
    sid = parse_item_id_from_object_name(str(son))
    if "enrichment" not in entry:
        entry["enrichment"] = {}
    entry["enrichment"]["skillUsed"] = {
        "skillId": sid,
        "displayName": skill_names.get(sid),
        "objectName": son,
    }


def load_skill_display_names(source_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for path in source_root.rglob("SKILL_*.json"):
        stem = path.stem
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(raw, list):
            continue
        for exp in raw:
            if not isinstance(exp, dict):
                continue
            if exp.get("Type") != "SkillData" or exp.get("Name") != stem:
                continue
            props = exp.get("Properties") or {}
            nm = props.get("Name")
            if isinstance(nm, dict):
                ls = nm.get("LocalizedString") or nm.get("SourceString")
                if isinstance(ls, str) and ls.strip():
                    out[stem] = ls.strip()
            break
    return out


def load_xp_event_tables_by_stem(source_root: Path) -> dict[str, dict[str, Any]]:
    by_stem: dict[str, dict[str, Any]] = {}
    for path in source_root.rglob("DT_XPEvents_*.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue
        table = raw[0]
        stem = table.get("Name")
        if not isinstance(stem, str):
            stem = path.stem
        rows = table.get("Rows")
        if isinstance(rows, dict):
            by_stem[stem] = rows
    return by_stem


def load_named_datatable_rows_bundle(
    source_root: Path, table_stems: tuple[str, ...]
) -> dict[str, dict[str, Any]]:
    """Load Rows dicts keyed by DataTable Name stem (e.g. DT_StabilityProfile)."""
    out: dict[str, dict[str, Any]] = {}
    for stem in table_stems:
        rows = _load_one_datatable_rows_by_stem(source_root, stem)
        if rows is not None:
            out[stem] = rows
    return out


def _load_one_datatable_rows_by_stem(source_root: Path, table_stem: str) -> dict[str, Any] | None:
    for path in source_root.rglob(f"{table_stem}.json"):
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
            continue
        table = raw[0]
        rows = table.get("Rows")
        if isinstance(rows, dict):
            return rows
    return None


def resolve_on_craft_xp_event(
    on_craft: Any,
    xp_tables: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    if not isinstance(on_craft, dict):
        return None
    dt = on_craft.get("DataTable") or {}
    object_name = dt.get("ObjectName") if isinstance(dt, dict) else None
    row_name = on_craft.get("RowName")
    if not isinstance(object_name, str) or not isinstance(row_name, str):
        return None
    stem = parse_data_table_stem_from_object_name(object_name)
    if not stem:
        return None
    rows = xp_tables.get(stem)
    if not isinstance(rows, dict) or row_name not in rows:
        return {
            "table": stem,
            "rowName": row_name,
            "resolved": False,
        }
    return {
        "table": stem,
        "rowName": row_name,
        "resolved": True,
        "row": rows[row_name],
    }


def enrich_recipe_entry(
    entry: dict[str, Any],
    source_root: Path,
    st_item_names: dict[str, str],
    skill_names: dict[str, str],
    xp_tables: dict[str, dict[str, Any]],
    item_name_cache: ItemDisplayCache,
    rel_path: str,
    enrichment_misses: list[dict[str, Any]] | None,
) -> None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    en: dict[str, Any] = {}

    def enrich_slots(key: str) -> list[dict[str, Any]]:
        out: list[dict[str, Any]] = []
        slots = props.get(key)
        if not isinstance(slots, list):
            return out
        for slot in slots:
            if not isinstance(slot, dict):
                continue
            item = slot.get("ItemData") or {}
            on = item.get("ObjectName", "") if isinstance(item, dict) else ""
            op = item.get("ObjectPath", "") if isinstance(item, dict) else ""
            iid = parse_item_id_from_object_name(str(on)) if on else ""
            display = None
            display_src: str | None = None
            if isinstance(op, str) and op:
                display, display_src = resolve_item_display_from_object_path(
                    source_root, op, iid, st_item_names, item_name_cache
                )
                if display is None and enrichment_misses is not None and on:
                    enrichment_misses.append(
                        {
                            "type": "itemDisplayUnresolved",
                            "context": "recipe",
                            "recipePath": rel_path,
                            "slotGroup": key,
                            "objectName": on,
                            "objectPath": op,
                        }
                    )
            slot_out: dict[str, Any] = {
                "itemId": iid,
                "displayName": display,
                "count": slot.get("Count"),
                "objectName": on,
                "objectPath": op,
            }
            if display_src:
                slot_out["displayNameSource"] = display_src
            out.append(slot_out)
        return out

    en["itemsConsumed"] = enrich_slots("ItemsConsumed")
    en["itemsCreated"] = enrich_slots("ItemsCreated")

    sk = props.get("SkillUsedToCraft")
    if isinstance(sk, dict):
        son = sk.get("ObjectName", "")
        sid = parse_item_id_from_object_name(str(son)) if "SkillData'" in str(son) else ""
        en["skillUsedToCraft"] = {
            "objectName": son,
            "skillId": sid,
            "displayName": skill_names.get(sid),
        }

    oc = props.get("OnCraftXpEvent")
    if oc is not None:
        en["onCraftXp"] = resolve_on_craft_xp_event(oc, xp_tables)

    if en:
        entry["enrichment"] = en


def collect_cast_xp_events_from_usd_raw(raw: list[Any]) -> list[dict[str, Any]]:
    found: list[dict[str, Any]] = []
    for exp in raw:
        if not isinstance(exp, dict):
            continue
        props = exp.get("Properties") or {}
        if "CastXpEvent" in props:
            found.append(props["CastXpEvent"])
    return found


def collect_items_cost_info_from_usd_raw(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in raw:
        if not isinstance(exp, dict):
            continue
        props = exp.get("Properties") or {}
        info = props.get("ItemsCostInfo")
        if not isinstance(info, list):
            continue
        for slot in info:
            if isinstance(slot, dict):
                out.append(slot)
    return out


def collect_gameplay_effect_refs_from_usd_raw(raw: list[Any]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for exp in raw:
        if not isinstance(exp, dict):
            continue
        props = exp.get("Properties") or {}
        ge = props.get("GameplayEffect")
        if isinstance(ge, dict) and (ge.get("ObjectPath") or ge.get("ObjectName")):
            out.append(ge)
    return out


def gameplay_effect_display_label(ge: dict[str, Any]) -> str | None:
    op = ge.get("ObjectPath")
    if isinstance(op, str) and op.strip():
        tail = op.rsplit("/", 1)[-1]
        return tail.split(".", 1)[0]
    on = ge.get("ObjectName")
    if isinstance(on, str) and "'" in on:
        return parse_object_name_inner(on)
    return None


def enrich_spell_entry(
    entry: dict[str, Any],
    raw: list[Any],
    xp_tables: dict[str, dict[str, Any]],
    source_root: Path,
    st_item_names: dict[str, str],
    item_name_cache: ItemDisplayCache,
    enrichment_misses: list[dict[str, Any]] | None,
    rel_path: str,
) -> None:
    en: dict[str, Any] = {}
    events = collect_cast_xp_events_from_usd_raw(raw)
    if events:
        resolved_list: list[dict[str, Any]] = []
        for ev in events:
            r = resolve_on_craft_xp_event(ev, xp_tables)
            if r:
                resolved_list.append(r)
        if resolved_list:
            en["castXpEvents"] = resolved_list

    cost_slots = collect_items_cost_info_from_usd_raw(raw)
    if cost_slots:
        cost_out: list[dict[str, Any]] = []
        for slot in cost_slots:
            item = slot.get("ItemData") or {}
            on = item.get("ObjectName", "") if isinstance(item, dict) else ""
            op = item.get("ObjectPath", "") if isinstance(item, dict) else ""
            iid = parse_item_id_from_object_name(str(on)) if on else ""
            display = None
            display_src: str | None = None
            if isinstance(op, str) and op:
                display, display_src = resolve_item_display_from_object_path(
                    source_root, op, iid, st_item_names, item_name_cache
                )
                if display is None and enrichment_misses is not None and on:
                    enrichment_misses.append(
                        {
                            "type": "itemDisplayUnresolved",
                            "context": "spellCost",
                            "spellPath": rel_path,
                            "objectName": on,
                            "objectPath": op,
                        }
                    )
            cost_row: dict[str, Any] = {
                "itemId": iid,
                "displayName": display,
                "count": slot.get("Count"),
                "objectName": on,
                "objectPath": op,
            }
            if display_src:
                cost_row["displayNameSource"] = display_src
            cost_out.append(cost_row)
        en["spellItemCosts"] = cost_out

    ge_refs = collect_gameplay_effect_refs_from_usd_raw(raw)
    if ge_refs:
        en["gameplayEffects"] = [
            {
                "objectName": ge.get("ObjectName"),
                "objectPath": ge.get("ObjectPath"),
                "displayLabel": gameplay_effect_display_label(ge),
            }
            for ge in ge_refs
        ]

    if en:
        entry["enrichment"] = en


def json_path_from_object_path(source_root: Path, object_path: str) -> Path | None:
    if not object_path or not isinstance(object_path, str):
        return None
    package = object_path.rsplit(".", 1)[0]
    if not package:
        return None
    p = source_root / f"{package}.json"
    if p.exists():
        return p
    return None


def summarize_building_piece_export(
    raw: list[Any],
    source_root: Path | None = None,
    st_item_names: dict[str, str] | None = None,
    item_name_cache: ItemDisplayCache | None = None,
    xp_tables: dict[str, dict[str, Any]] | None = None,
    stability_tables: dict[str, dict[str, Any]] | None = None,
) -> dict[str, Any] | None:
    if not isinstance(raw, list) or not raw:
        return None
    target = None
    for exp in raw:
        if isinstance(exp, dict) and exp.get("Type") == "BuildingPieceData":
            target = exp
            break
    if target is None:
        target = raw[0] if isinstance(raw[0], dict) else None
    if not isinstance(target, dict):
        return None
    props = target.get("Properties") or {}
    dn = props.get("DisplayName")
    display = None
    if isinstance(dn, dict):
        display = dn.get("LocalizedString") or dn.get("SourceString")
    desc = props.get("Description")
    description = None
    if isinstance(desc, dict):
        description = desc.get("LocalizedString") or desc.get("SourceString")

    piece_tag = props.get("PieceTag")
    tag_name = None
    if isinstance(piece_tag, dict):
        tag_name = piece_tag.get("TagName")

    requirements_out: list[dict[str, Any]] = []
    reqs = props.get("Requirements")
    if (
        isinstance(reqs, list)
        and source_root is not None
        and st_item_names is not None
        and item_name_cache is not None
    ):
        for req in reqs:
            if not isinstance(req, dict):
                continue
            item = req.get("ItemData") or {}
            on = item.get("ObjectName", "") if isinstance(item, dict) else ""
            op = item.get("ObjectPath", "") if isinstance(item, dict) else ""
            iid = parse_item_id_from_object_name(str(on)) if on else ""
            rdisplay = None
            rsrc: str | None = None
            if isinstance(op, str) and op:
                rdisplay, rsrc = resolve_item_display_from_object_path(
                    source_root, op, iid, st_item_names, item_name_cache
                )
            req_row: dict[str, Any] = {
                "amount": req.get("Amount"),
                "itemId": iid,
                "displayName": rdisplay,
                "objectName": on,
                "objectPath": op,
            }
            if rsrc:
                req_row["displayNameSource"] = rsrc
            requirements_out.append(req_row)

    build_xp: dict[str, Any] | None = None
    if xp_tables is not None:
        bxe = props.get("BuildXpEvent")
        if bxe is not None:
            build_xp = resolve_on_craft_xp_event(bxe, xp_tables)

    building_stability: dict[str, Any] | None = None
    if stability_tables is not None:
        sh = props.get("BuildingStabilityProfileRowHandle")
        if isinstance(sh, dict):
            building_stability = resolve_on_craft_xp_event(sh, stability_tables)

    return {
        "assetName": target.get("Name"),
        "assetType": target.get("Type"),
        "displayName": display,
        "description": description,
        "internalName": props.get("InternalName"),
        "pieceTag": tag_name,
        "requirements": requirements_out,
        "buildXp": build_xp,
        "buildingStabilityProfile": building_stability,
    }


def enrich_plan_entry(
    entry: dict[str, Any],
    source_root: Path,
    issues: list[dict[str, Any]],
    rel_path: str,
    st_item_names: dict[str, str],
    item_name_cache: ItemDisplayCache,
    xp_tables: dict[str, dict[str, Any]],
    stability_tables: dict[str, dict[str, Any]],
) -> None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    bpu = props.get("BuildingPieceToUnlock")
    if not isinstance(bpu, dict):
        return
    op = bpu.get("ObjectPath")
    if not isinstance(op, str):
        return
    jpath = json_path_from_object_path(source_root, op)
    if jpath is None or not jpath.exists():
        issues.append(
            {
                "type": "planBuildingPieceMissing",
                "planPath": rel_path,
                "objectPath": op,
            }
        )
        entry["enrichment"] = {"buildingPieceToUnlock": {"objectPath": op, "resolved": False}}
        return
    try:
        raw = json.loads(jpath.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        issues.append({"type": "planBuildingPieceParse", "planPath": rel_path, "error": str(exc)})
        return
    summary = summarize_building_piece_export(
        raw,
        source_root=source_root,
        st_item_names=st_item_names,
        item_name_cache=item_name_cache,
        xp_tables=xp_tables,
        stability_tables=stability_tables,
    )
    entry["enrichment"] = {
        "buildingPieceToUnlock": {
            "objectPath": op,
            "jsonFile": str(jpath.relative_to(source_root)).replace("\\", "/"),
            "resolved": summary is not None,
            "summary": summary,
        }
    }


def enrich_nested_item_refs(
    obj: Any,
    source_root: Path,
    st_item_names: dict[str, str],
    cache: ItemDisplayCache,
    enrichment_misses: list[dict[str, Any]] | None = None,
    context_path: str = "",
) -> None:
    if isinstance(obj, dict):
        on = obj.get("ObjectName")
        op = obj.get("ObjectPath")
        inner = parse_object_name_inner(str(on)) if isinstance(on, str) else ""
        if isinstance(on, str) and isinstance(op, str) and op and "ITEM_" in inner:
            iid = parse_item_id_from_object_name(on)
            name, name_src = resolve_item_display_from_object_path(
                source_root, op, iid, st_item_names, cache
            )
            if name:
                obj["resolvedDisplayName"] = name
                if name_src:
                    obj["resolvedDisplayNameSource"] = name_src
            elif enrichment_misses is not None and on:
                enrichment_misses.append(
                    {
                        "type": "itemDisplayUnresolved",
                        "context": "progression",
                        "tablePath": context_path,
                        "objectName": on,
                        "objectPath": op,
                    }
                )
        for v in obj.values():
            enrich_nested_item_refs(
                v, source_root, st_item_names, cache, enrichment_misses, context_path
            )
    elif isinstance(obj, list):
        for x in obj:
            enrich_nested_item_refs(
                x, source_root, st_item_names, cache, enrichment_misses, context_path
            )


def build_recipe_stem_index(source_root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for p in source_root.rglob("RECIPE_*.json"):
        out[p.stem] = str(p.relative_to(source_root)).replace("\\", "/")
    return out


def enrich_vestige_entry(
    entry: dict[str, Any],
    source_root: Path,
    st_item_names: dict[str, str],
    recipe_index: dict[str, str],
) -> None:
    enrich_item_entry_display_name(entry, st_item_names)
    props = entry.get("properties")
    if not isinstance(props, dict):
        return
    rtu = props.get("RecipesToUnlock")
    if not isinstance(rtu, list) or not rtu:
        return
    resolved: list[dict[str, Any]] = []
    for ref in rtu:
        if not isinstance(ref, dict):
            continue
        on = ref.get("ObjectName", "")
        stem = ""
        if "RecipeData'" in str(on):
            stem = parse_item_id_from_object_name(str(on))
        if not stem.startswith("RECIPE_"):
            continue
        rel = recipe_index.get(stem)
        summ: dict[str, Any] | None = None
        if rel:
            jpath = source_root / rel
            try:
                raw = json.loads(jpath.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                raw = None
            if isinstance(raw, list) and raw and isinstance(raw[0], dict):
                e0 = raw[0]
                rp = e0.get("Properties") or {}
                summ = {
                    "exportName": e0.get("Name"),
                    "exportType": e0.get("Type"),
                    "internalName": rp.get("InternalName"),
                }
        resolved.append(
            {
                "recipeId": stem,
                "sourceFile": rel,
                "resolved": rel is not None,
                "summary": summ,
            }
        )
    if resolved:
        if "enrichment" not in entry:
            entry["enrichment"] = {}
        entry["enrichment"]["recipesToUnlock"] = resolved


def build_recipes_by_item_index(entries: dict[str, dict[str, Any]]) -> dict[str, list[str]]:
    by_item: dict[str, set[str]] = {}
    for rel, compact in entries.items():
        en = compact.get("enrichment") or {}
        for group in ("itemsConsumed", "itemsCreated"):
            for slot in en.get(group) or []:
                if not isinstance(slot, dict):
                    continue
                iid = slot.get("itemId")
                if isinstance(iid, str) and iid:
                    by_item.setdefault(iid, set()).add(rel)
    return {k: sorted(by_item[k]) for k in sorted(by_item.keys())}


# --- Pipeline orchestration (CLI) ---


def run_step(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    printable = " ".join(command)
    print(f"[RUN] {printable}", flush=True)
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def load_config(config_path: Path) -> dict:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {config_path}")
    return payload


def resolve_json_root(repo_root: Path, config: dict) -> Path:
    explicit_json_root = config.get("datasetJsonRoot")
    if isinstance(explicit_json_root, str) and explicit_json_root.strip():
        candidate = Path(explicit_json_root.strip())
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate

    dataset_version = config.get("datasetVersion")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("Config missing required string key: datasetVersion")

    return (repo_root / dataset_version.strip() / "json").resolve()


def validate_json_root(json_root: Path) -> None:
    if not json_root.exists():
        raise FileNotFoundError(f"JSON root not found: {json_root}")
    if not (json_root / "RSDragonwilds").exists():
        raise FileNotFoundError(f"Expected RSDragonwilds under json root: {json_root}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile dataset JSON using website config: Item, Location, Loot, Name, NPC, Plan, "
            "Progression, Recipe, Spell, Vestige, Icon."
        )
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_RELATIVE),
        help="Path to website data config JSON (default: website/data.config.json)",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = load_config(config_path)
    json_root = resolve_json_root(repo_root, config)
    validate_json_root(json_root)

    env = dict(os.environ)
    root_s = str(json_root)
    env["RSDW_JSON_ROOT"] = root_s
    env["RSDW_ITEM_SOURCE_DIR"] = root_s
    env["RSDW_LOCATION_SOURCE_DIR"] = root_s
    env["RSDW_LOOT_SOURCE_DIR"] = root_s
    env["RSDW_NPC_SOURCE_DIR"] = root_s
    env["RSDW_PLAN_SOURCE_DIR"] = root_s
    env["RSDW_PROGRESSION_SOURCE_DIR"] = root_s
    env["RSDW_RECIPE_SOURCE_DIR"] = root_s
    env["RSDW_SPELL_SOURCE_DIR"] = root_s
    env["RSDW_VESTIGE_SOURCE_DIR"] = root_s
    env["RSDW_NAME_SOURCE_DIR"] = root_s

    tools = repo_root / "website" / "tools"

    steps = [
        tools / "ItemData" / "CompileItemData.py",
        tools / "LocationData" / "CompileLocationData.py",
        tools / "LootData" / "CompileLootData.py",
        tools / "NameData" / "CompileNameData.py",
        tools / "NPCData" / "CompileNPCData.py",
        tools / "PlanData" / "CompilePlanData.py",
        tools / "ProgressionData" / "CompileProgressionData.py",
        tools / "RecipeData" / "CompileRecipeData.py",
        tools / "SpellData" / "CompileSpellData.py",
        tools / "VestigeData" / "CompileVestigeData.py",
        tools / "IconData" / "CompileIconData.py",
    ]

    for py in steps:
        run_step(["python", str(py)], repo_root, env)

    print("[INFO] Compile data pipeline completed successfully.")
    print(f"[INFO] Config: {config_path}")
    print(f"[INFO] JSON root used: {json_root}")


if __name__ == "__main__":
    main()
