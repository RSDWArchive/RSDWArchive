import argparse
import json
import re
from pathlib import Path
from typing import Any
from datetime import datetime, timezone


DEFAULT_CATALOG = Path(__file__).resolve().parent.parent / "pages" / "catalog.items.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "pages" / "pages.armour.json"
DEFAULT_LOOTDATA = Path(__file__).resolve().parents[2] / "LootData" / "LootData.json"


STATION_NAME_MAP = {
    "CraftingTable": "Crafting Table",
    "SmithingAnvil": "Smithing Anvil",
    "JewelersBench": "Jeweler's Bench",
    "RuneAltar": "Rune Altar",
    "FletchingBench": "Fletching Bench",
    "Furnace": "Furnace",
    "Kiln": "Kiln",
    "Loom": "Loom",
    "CookingRange": "Cooking Range",
    "RangeStone": "Range Stone",
    "BrewingCauldron": "Brewing Cauldron",
}

SKILL_NAME_MAP = {
    "SKILL_Artisan": "Artisan",
    "SKILL_Attack": "Attack",
    "SKILL_Construction": "Construction",
    "SKILL_Cooking": "Cooking",
    "SKILL_Farming": "Farming",
    "SKILL_Magic": "Magic",
    "SKILL_Mining": "Mining",
    "SKILL_Runecrafting": "Runecrafting",
    "SKILL_Ranged": "Ranged",
    "SKILL_Woodcutting": "Woodcutting",
}


def humanize_item_id(item_id: str) -> str:
    name = item_id
    for prefix in ("ITEM_", "DA_", "RECIPE_"):
        if name.startswith(prefix):
            name = name[len(prefix) :]
    return name.replace("_", " ")


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_loot_indexes(path: Path) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    if not path.exists():
        return {}, {}
    try:
        payload = load_json(path)
    except Exception:
        return {}, {}
    indexes = payload.get("indexes") if isinstance(payload, dict) else {}
    if not isinstance(indexes, dict):
        return {}, {}
    item_to_enemies = indexes.get("itemToEnemies")
    item_to_chests = indexes.get("itemToChestProfiles")
    if not isinstance(item_to_enemies, dict):
        item_to_enemies = {}
    if not isinstance(item_to_chests, dict):
        item_to_chests = {}
    return item_to_enemies, item_to_chests


def sanitize_title_fragment(value: str) -> str:
    out = str(value or "")
    out = out.replace("/", " - ")
    out = out.replace("[", "(").replace("]", ")")
    out = re.sub(r"[#<>|{}]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def select_armour_candidates(items: dict[str, Any], indexes: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    by_category = indexes.get("itemsByCategory") if isinstance(indexes, dict) else None
    if isinstance(by_category, dict):
        armour_ids = by_category.get("armour")
        if isinstance(armour_ids, list):
            candidates = []
            for item_id in armour_ids:
                item = items.get(item_id)
                if isinstance(item, dict):
                    candidates.append((item_id, item))
            if candidates:
                return candidates

    # Fallback for older catalogs that don't include the category index.
    candidates = []
    for item_id, item in items.items():
        if item.get("className") != "UScriptClass'WearableEquipmentData'":
            continue
        tags = item.get("itemFilterTags") or []
        if not any("ItemFilter.Type.Equipment.Armour" in str(tag) for tag in tags):
            continue
        candidates.append((item_id, item))
    return candidates


def format_recipe_block(recipe: dict[str, Any], items: dict[str, Any], facility: str | None) -> list[str]:
    lines = ["==Recipe==", "{{Recipe"]
    if facility:
        lines.append(f"|facility = {facility}")

    skill_id = recipe.get("skillUsedToCraft")
    skill_name = SKILL_NAME_MAP.get(skill_id, skill_id or "")
    if skill_name:
        lines.append(f"|skill = {skill_name}")

    skill_xp = recipe.get("skillXpAwarded")
    if skill_xp is not None:
        lines.append(f"|skillxp = {skill_xp}")

    consumed = recipe.get("consumedItems", [])
    for idx, entry in enumerate(consumed, start=1):
        item_id = entry.get("itemId")
        display = (items.get(item_id) or {}).get("displayName") or humanize_item_id(str(item_id or "Unknown"))
        lines.append(f"|mat{idx} = {display}")
        lines.append(f"|mat{idx}qty = {entry.get('count', 1)}")

    created = recipe.get("createdItems", [])
    if created:
        created_item = created[0]
        out_id = created_item.get("itemId")
        out_name = (items.get(out_id) or {}).get("displayName") or humanize_item_id(str(out_id or "Unknown"))
        lines.append(f"|output1 = {out_name}")
        if created_item.get("count") not in (None, 1):
            lines.append(f"|output1qty = {created_item.get('count')}")

    lines.append("}}")
    return lines


def build_armour_page(
    item: dict[str, Any],
    recipe: dict[str, Any] | None,
    journal: dict[str, Any] | None,
    wearable_equipment: dict[str, Any] | None,
    items: dict[str, Any],
    facility_name: str | None,
    include_products: bool,
    include_item_sources: bool,
) -> str:
    name = item.get("displayName") or item.get("itemId")
    description = item.get("description") or ""
    weight = (item.get("stats") or {}).get("Weight")
    power = (item.get("stats") or {}).get("PowerLevel")
    durability = (item.get("stats") or {}).get("BaseDurability")
    image = f"{name}.png"

    lines: list[str] = [
        "{{Infobox Item",
        f"|name = {name}",
        f"|image = {image}",
        "|type = Armour",
    ]
    if weight is not None:
        lines.append(f"|weight = {weight}")
    if description:
        lines.append(f"|description = {description}")
    lines.append("}}")
    lines.append(f"'''{name}''' is an armour item.")
    lines.append("")
    lines.append("==Stats==")
    lines.append("{{Infobox Armour")
    if power is not None:
        lines.append(f"|power = {power}")
    if durability is not None:
        lines.append(f"|durability = {durability}")
    if wearable_equipment:
        raw = wearable_equipment.get("raw") if isinstance(wearable_equipment.get("raw"), dict) else {}
        derived = (
            wearable_equipment.get("derivedDisplayDefence")
            if isinstance(wearable_equipment.get("derivedDisplayDefence"), dict)
            else {}
        )
        melee_def = derived.get("melee")
        if melee_def is None:
            melee_def = raw.get("defense")
        if melee_def is None:
            melee_def = raw.get("meleeResistance")
        if melee_def is not None:
            lines.append(f"|meleedefence = {melee_def}")
        ranged_def = derived.get("ranged")
        if ranged_def is None:
            ranged_def = raw.get("rangedResistance")
        if ranged_def is not None:
            lines.append(f"|rangeddefence = {ranged_def}")
        magic_def = derived.get("magic")
        if magic_def is None:
            magic_def = raw.get("magicResistance")
        if magic_def is not None:
            lines.append(f"|magicdefence = {magic_def}")
    lines.append("}}")
    lines.append("")

    if recipe:
        lines.extend(format_recipe_block(recipe, items, facility_name))
        lines.append("")
        lines.append("===Recipe tree===")
        lines.append(f"{{{{Crafting Tree|{name}}}}}")
        lines.append("")

    if include_products:
        lines.append("==Products==")
        lines.append(f"{{{{Uses material list|{name}}}}}")
        lines.append("")
    if include_item_sources:
        lines.append("==Item sources==")
        lines.append(f"{{{{Drop sources list|{name}}}}}")
        lines.append("")
    lines.append("==Journal==")
    journal_text = ""
    if journal:
        descriptions = journal.get("descriptionPages") or []
        if descriptions:
            journal_text = descriptions[0]
    lines.append("{{Journal entry|")
    lines.append(journal_text)
    lines.append("}}")
    lines.append("")
    lines.append("<!-- Generated by generate_armour_pages.py -->")
    lines.append("")
    return "\n".join(lines)


def generate_armour_pages_payload(
    payload: dict[str, Any],
    item_to_enemies: dict[str, list[str]],
    item_to_chests: dict[str, list[str]],
    *,
    limit: int = 0,
    title_prefix: str = "User:RSDWArchiveBot/Armour/",
    summary: str = "Bot: update generated armour page",
    include_products: bool = False,
    include_item_sources: bool = False,
) -> dict[str, Any]:
    items = payload.get("items", {})
    indexes = payload.get("indexes", {})
    recipes = payload.get("recipes", {})
    journals = payload.get("journals", {})

    candidates = select_armour_candidates(items, indexes)
    candidates.sort(key=lambda pair: (pair[1].get("displayName") or pair[0]))
    if limit > 0:
        candidates = candidates[:limit]

    pages = []
    pages_with_products = 0
    pages_with_sources = 0
    for item_id, item in candidates:
        created_by = item.get("links", {}).get("createdByRecipes", [])
        recipe = recipes.get(created_by[0]) if created_by else None

        journal_ids = item.get("links", {}).get("journalEntries", [])
        journal = journals.get(journal_ids[0]) if journal_ids else None
        facility_name = None
        if journal:
            station_row = journal.get("stationRow")
            if isinstance(station_row, str):
                facility_name = STATION_NAME_MAP.get(station_row, station_row)

        wearable_equipment = item.get("wearableEquipment") if isinstance(item.get("wearableEquipment"), dict) else None

        has_products_data = bool(item.get("links", {}).get("requiredInRecipes"))
        has_source_data = bool(item_to_enemies.get(item_id) or item_to_chests.get(item_id))
        use_products = include_products or has_products_data
        use_item_sources = include_item_sources or has_source_data
        if use_products:
            pages_with_products += 1
        if use_item_sources:
            pages_with_sources += 1

        page_name = sanitize_title_fragment(item.get("displayName") or item_id)
        text = build_armour_page(
            item=item,
            recipe=recipe,
            journal=journal,
            wearable_equipment=wearable_equipment,
            items=items,
            facility_name=facility_name,
            include_products=use_products,
            include_item_sources=use_item_sources,
        )
        pages.append(
            {
                "title": f"{title_prefix}{page_name}",
                "text": text,
                "summary": summary,
                "meta": {
                    "category": "armour",
                    "itemId": item_id,
                    "recipeId": recipe.get("recipeId") if recipe else None,
                    "journalId": journal.get("journalId") if journal else None,
                    "wearableRowName": wearable_equipment.get("rowName") if wearable_equipment else None,
                    "hasDerivedDisplayDefence": bool(
                        wearable_equipment and isinstance(wearable_equipment.get("derivedDisplayDefence"), dict)
                    ),
                    "validation": {
                        "hasProductsData": has_products_data,
                        "hasItemSourceData": has_source_data,
                        "includedProductsSection": use_products,
                        "includedItemSourcesSection": use_item_sources,
                        "sourceMatches": {
                            "enemyCount": len(item_to_enemies.get(item_id, [])),
                            "chestProfileCount": len(item_to_chests.get(item_id, [])),
                        },
                    },
                },
            }
        )

    return {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "pages": pages,
        "report": {
            "category": "armour",
            "candidateItems": len(candidates),
            "totalPages": len(pages),
            "pagesWithProductsSection": pages_with_products,
            "pagesWithItemSourcesSection": pages_with_sources,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate armour wiki pages from catalog.items.json")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="Path to catalog.items.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output pages JSON")
    parser.add_argument("--lootdata", default=str(DEFAULT_LOOTDATA), help="Path to LootData.json for source checks")
    parser.add_argument("--limit", type=int, default=0, help="Max pages to emit (0=all)")
    parser.add_argument("--title-prefix", default="User:RSDWArchiveBot/Armour/", help="Page title prefix")
    parser.add_argument("--summary", default="Bot: update generated armour page", help="Edit summary")
    parser.add_argument("--include-products", action="store_true", help="Include {{Uses material list|...}} section")
    parser.add_argument("--include-item-sources", action="store_true", help="Include {{Drop sources list|...}} section")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    output_path = Path(args.output)
    lootdata_path = Path(args.lootdata)
    payload = load_json(catalog_path)

    item_to_enemies, item_to_chests = load_loot_indexes(lootdata_path)
    output_payload = generate_armour_pages_payload(
        payload,
        item_to_enemies,
        item_to_chests,
        limit=args.limit,
        title_prefix=args.title_prefix,
        summary=args.summary,
        include_products=args.include_products,
        include_item_sources=args.include_item_sources,
    )

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_payload["report"]["lootdataUsed"] = str(lootdata_path) if lootdata_path.exists() else None
    output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {output_payload.get('report', {}).get('totalPages', 0)} armour pages to: {output_path}")


if __name__ == "__main__":
    main()
