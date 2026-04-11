"""
Print summary statistics for compiled *Data.json files (quality / coverage audit).

Run from repo root:
  python website/tools/audit_datasets.py

Or with explicit repo root:
  python website/tools/audit_datasets.py --repo E:/Github/RSDWArchive
"""

from __future__ import annotations

import argparse
import json
import random
import sys
from pathlib import Path
from typing import Any


def _repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def audit_item_data(path: Path) -> None:
    print(f"\n=== ItemData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    n = len(entries)
    counts = data.get("counts") or {}
    excl = counts.get("filesExcludedByName")
    if isinstance(excl, int) and excl > 0:
        print(f"  counts.filesExcludedByName (e.g. _MeshData_): {excl}")
    print(f"  entries: {n}")
    if n == 0:
        return
    with_display = sum(
        1
        for e in entries.values()
        if isinstance(e, dict) and (e.get("enrichment") or {}).get("displayName")
    )
    with_flavour = sum(
        1
        for e in entries.values()
        if isinstance(e, dict) and (e.get("enrichment") or {}).get("flavourText")
    )
    with_skill = sum(
        1
        for e in entries.values()
        if isinstance(e, dict) and (e.get("enrichment") or {}).get("skillUsed")
    )
    print(f"  enrichment.displayName: {with_display} ({100 * with_display / n:.1f}%)")
    print(f"  enrichment.flavourText: {with_flavour} ({100 * with_flavour / n:.1f}%)")
    print(f"  enrichment.skillUsed: {with_skill} ({100 * with_skill / n:.1f}%)")
    sample = random.sample(list(entries.items()), min(3, n))
    for rel, ent in sample:
        name = (ent.get("enrichment") or {}).get("displayName") if isinstance(ent, dict) else None
        print(f"  sample: {rel[:72]}... | displayName={name!r}" if len(rel) > 72 else f"  sample: {rel} | displayName={name!r}")


def audit_recipe_data(path: Path) -> None:
    print(f"\n=== RecipeData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    misses = (data.get("issues") or {}).get("enrichmentMisses") or []
    idx = data.get("indexes") or {}
    rbi = idx.get("recipesByItemId") or {}
    print(f"  entries: {len(entries)}")
    print(f"  issues.enrichmentMisses: {len(misses)}")
    print(f"  indexes.recipesByItemId keys: {len(rbi)}")
    if misses:
        print(f"  first miss: {misses[0]}")


def audit_spell_data(path: Path) -> None:
    print(f"\n=== SpellData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    misses = (data.get("issues") or {}).get("enrichmentMisses") or []
    with_costs = sum(
        1
        for e in entries.values()
        if isinstance(e, dict) and (e.get("enrichment") or {}).get("spellItemCosts")
    )
    with_ge = sum(
        1
        for e in entries.values()
        if isinstance(e, dict) and (e.get("enrichment") or {}).get("gameplayEffects")
    )
    util = sum(1 for e in entries.values() if isinstance(e, dict) and e.get("primaryExportSource") == "UtilitySpellData")
    print(f"  entries: {len(entries)}")
    print(f"  primaryExportSource=UtilitySpellData: {util}")
    print(f"  with spellItemCosts: {with_costs}")
    print(f"  with gameplayEffects: {with_ge}")
    print(f"  issues.enrichmentMisses: {len(misses)}")


def audit_plan_data(path: Path) -> None:
    print(f"\n=== PlanData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    pbi = (data.get("issues") or {}).get("planBuildingPieces") or []
    with_stab = 0
    for e in entries.values():
        if not isinstance(e, dict):
            continue
        s = ((e.get("enrichment") or {}).get("buildingPieceToUnlock") or {}).get("summary") or {}
        if s.get("buildingStabilityProfile"):
            with_stab += 1
    print(f"  entries: {len(entries)}")
    print(f"  summaries with buildingStabilityProfile: {with_stab}")
    print(f"  issues.planBuildingPieces: {len(pbi)}")


def audit_progression_data(path: Path) -> None:
    print(f"\n=== ProgressionData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    tables = data.get("tables") or {}
    misses = (data.get("issues") or {}).get("enrichmentMisses") or []
    total_rows = 0
    with_resolved = 0
    for tbl in tables.values():
        rows = tbl.get("rows") or {}
        if not isinstance(rows, dict):
            continue
        for row in rows.values():
            total_rows += 1
            if _row_has_resolved_display(row):
                with_resolved += 1
    print(f"  tables: {len(tables)}")
    print(f"  row payloads scanned (approx): {total_rows}")
    print(f"  rows containing resolvedDisplayName somewhere: {with_resolved} (heuristic)")
    print(f"  issues.enrichmentMisses: {len(misses)}")


def _row_has_resolved_display(obj: Any) -> bool:
    if isinstance(obj, dict):
        if "resolvedDisplayName" in obj:
            return True
        return any(_row_has_resolved_display(v) for v in obj.values())
    if isinstance(obj, list):
        return any(_row_has_resolved_display(x) for x in obj)
    return False


def audit_vestige_data(path: Path) -> None:
    print(f"\n=== VestigeData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    unresolved = 0
    for e in entries.values():
        rtu = ((e.get("enrichment") or {}).get("recipesToUnlock")) or []
        if not isinstance(rtu, list):
            continue
        for r in rtu:
            if isinstance(r, dict) and r.get("resolved") is False:
                unresolved += 1
    print(f"  entries: {len(entries)}")
    print(f"  recipesToUnlock unresolved slots: {unresolved}")


def audit_loot_data(path: Path) -> None:
    print(f"\n=== LootData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    issues = data.get("issues") or {}
    print(f"  enemies: {len(data.get('enemies') or {})}")
    print(f"  chests: {len(data.get('chests') or {})}")
    print(f"  issues.missingReferences: {len(issues.get('missingReferences') or [])}")


def audit_npc_data(path: Path, loot_path: Path | None) -> None:
    print(f"\n=== NPCData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    npcs = data.get("npcs") or {}
    issues = data.get("issues") or {}
    print(f"  npcs: {len(npcs)}")
    print(f"  issues.missingLinks: {len(issues.get('missingLinks') or [])}")
    if loot_path and loot_path.exists():
        loot = load_json(loot_path)
        enemies = loot.get("enemies") or {}
        missing_loot = 0
        checked = 0
        for rec in npcs.values():
            if not isinstance(rec, dict):
                continue
            loot = rec.get("loot") if isinstance(rec.get("loot"), dict) else {}
            row = loot.get("enemyLootRowName")
            if not isinstance(row, str) or row in ("", "None"):
                continue
            checked += 1
            if row not in enemies:
                missing_loot += 1
        print(f"  NPCs with enemyLootRowName (non-empty): {checked}")
        print(f"  ...with no LootData.enemies key: {missing_loot} (join gap)")


def audit_name_data(path: Path) -> None:
    print(f"\n=== NameData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    entries = data.get("entries") or {}
    counts = data.get("counts") or {}
    issues = data.get("issues") or {}
    print(f"  string tables (files): {len(entries)}")
    sk = counts.get("skippedNonStandard")
    if isinstance(sk, int):
        print(f"  counts.skippedNonStandard (not in entries): {sk}")
    print(f"  counts.totalKeys: {counts.get('totalKeys', '?')}")
    print(f"  issues.parseErrors: {len(issues.get('parseErrors') or [])}")
    print(f"  issues.atypicalExports (skipped non-stringTable ST_): {len(issues.get('atypicalExports') or [])}")
    if entries:
        sample_key = next(iter(sorted(entries.keys())))
        print(f"  sample path: {sample_key[:90]}..." if len(sample_key) > 90 else f"  sample path: {sample_key}")


def audit_location_data(path: Path) -> None:
    print(f"\n=== LocationData ({path}) ===")
    try:
        data = load_json(path)
    except Exception as exc:  # noqa: BLE001
        print(f"  ERROR: {exc}")
        return
    if isinstance(data, dict) and "entries" in data:
        entries = data.get("entries") or {}
    else:
        entries = data if isinstance(data, dict) else {}
    print(f"  location keys: {len(entries)} (large file expected)")
    if entries:
        k = next(iter(entries))
        print(f"  sample key: {k[:80]}..." if len(k) > 80 else f"  sample key: {k}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit compiled *Data.json summary stats.")
    parser.add_argument(
        "--repo",
        type=Path,
        default=None,
        help="Repository root (default: parent of website/)",
    )
    args = parser.parse_args()
    repo = args.repo.resolve() if args.repo else _repo_root_from_script()
    tools = repo / "website" / "tools"

    paths = {
        "item": tools / "ItemData" / "ItemData.json",
        "recipe": tools / "RecipeData" / "RecipeData.json",
        "spell": tools / "SpellData" / "SpellData.json",
        "plan": tools / "PlanData" / "PlanData.json",
        "progression": tools / "ProgressionData" / "ProgressionData.json",
        "vestige": tools / "VestigeData" / "VestigeData.json",
        "loot": tools / "LootData" / "LootData.json",
        "name": tools / "NameData" / "NameData.json",
        "npc": tools / "NPCData" / "NPCData.json",
        "location": tools / "LocationData" / "LocationData.json",
    }

    print(f"Repository root: {repo}")
    random.seed(42)

    for key, p in paths.items():
        if not p.exists():
            print(f"\n=== {key} MISSING: {p} ===")
            continue
        if key == "item":
            audit_item_data(p)
        elif key == "recipe":
            audit_recipe_data(p)
        elif key == "spell":
            audit_spell_data(p)
        elif key == "plan":
            audit_plan_data(p)
        elif key == "progression":
            audit_progression_data(p)
        elif key == "vestige":
            audit_vestige_data(p)
        elif key == "loot":
            audit_loot_data(p)
        elif key == "name":
            audit_name_data(p)
        elif key == "npc":
            audit_npc_data(p, paths["loot"])
        elif key == "location":
            audit_location_data(p)

    print("\nDone.")


if __name__ == "__main__":
    main()
