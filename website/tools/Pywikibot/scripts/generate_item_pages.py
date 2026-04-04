import argparse
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from generate_armour_pages import (
    DEFAULT_CATALOG,
    DEFAULT_LOOTDATA,
    STATION_NAME_MAP,
    format_recipe_block,
    generate_armour_pages_payload,
    load_json,
    load_loot_indexes,
)


DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "pages" / "pages.items.json"


def parse_categories(raw: str, all_categories: list[str]) -> list[str]:
    value = (raw or "all").strip()
    if not value or value.lower() == "all":
        return all_categories
    requested = [part.strip() for part in value.split(",") if part.strip()]
    seen = set()
    out: list[str] = []
    for item in requested:
        if item in seen:
            continue
        seen.add(item)
        out.append(item)
    return out


def title_case_category(category: str) -> str:
    return category.replace("_", " ").title().replace(" ", "")


def display_category_name(category: str) -> str:
    return category.replace("_", " ").title()


def humanize_item_id(item_id: str) -> str:
    value = item_id or ""
    for prefix in ("ITEM_", "RECIPE_", "DA_"):
        if value.startswith(prefix):
            value = value[len(prefix) :]
    return value.replace("_", " ").strip()


def sanitize_title_fragment(value: str) -> str:
    out = str(value or "")
    out = out.replace("/", " - ")
    out = out.replace("[", "(").replace("]", ")")
    out = re.sub(r"[#<>|{}]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def format_stat_value(value: Any) -> str:
    if isinstance(value, float):
        text = f"{value:.4f}".rstrip("0").rstrip(".")
        return text if text else "0"
    if isinstance(value, (list, tuple)):
        return ", ".join(format_stat_value(part) for part in value) if value else "-"
    if isinstance(value, dict):
        if "DamageType" in value and "Value" in value:
            return f"{value.get('DamageType')}: {format_stat_value(value.get('Value'))}"
        return json.dumps(value, ensure_ascii=False, sort_keys=True)
    return str(value)


def clean_damage_type(value: str) -> str:
    tail = value.split(".")[-1]
    return tail.replace("_", " ").strip()


def infer_weapon_type(item: dict[str, Any]) -> str:
    tags = item.get("itemFilterTags") or []
    tags_text = " ".join(str(tag) for tag in tags)
    if "Weapon.Ranged" in tags_text:
        return "Ranged Weapon"
    if "Weapon.Magic" in tags_text:
        return "Magic Weapon"
    return "Melee Weapon"


def infer_attack_style(item: dict[str, Any]) -> str:
    item_id = str(item.get("itemId") or "")
    parts = item_id.split("_")
    if len(parts) >= 2:
        return parts[1].replace("_", " ")
    return "Weapon"


def build_weapon_stats_template(item: dict[str, Any]) -> list[str]:
    stats = item.get("stats") or {}
    power = stats.get("PowerLevel")
    durability = stats.get("BaseDurability")
    block = stats.get("BlockingDamageNegation")
    damage_multi = stats.get("DamageMultiplier")
    crit = stats.get("CriticalHitChanceIncrease")
    base_damage = stats.get("BaseDamage")
    additional_damage = stats.get("AdditionalDamage")
    damage_types = stats.get("DamageTypes") or []

    lines = ["==Stats==", "{{Infobox Weapon"]
    if power is not None:
        lines.append(f"| power = {format_stat_value(power)}")
    if durability is not None:
        lines.append(f"| durability = {format_stat_value(durability)}")
    if damage_types:
        first_damage_type = clean_damage_type(str(damage_types[0]))
        lines.append(f"| damagetype = {first_damage_type}")
    lines.append(f"| attackstyle = {infer_attack_style(item)}")
    if base_damage is not None:
        lines.append(f"| basedmg = {format_stat_value(base_damage)}")
    if additional_damage is not None:
        lines.append(f"| additionaldmg = {format_stat_value(additional_damage)}")
    if damage_multi is not None:
        lines.append(f"| damagemulti = {format_stat_value(damage_multi)}")
    if block is not None:
        lines.append(f"| block = {format_stat_value(block)}")
    if crit is not None:
        lines.append(f"| criticalchance = {format_stat_value(crit)}")
    lines.append("}}")

    name = item.get("displayName") or item.get("itemId") or "Weapon"
    lines.append(f"[[File:{name} (Equipped).jpg|thumb|An {name} as seen when equipped by a player]]")
    lines.append("")
    return lines


def build_tool_stats_template(item: dict[str, Any]) -> list[str]:
    stats = item.get("stats") or {}
    lines = ["==Stats==", "{{Infobox Tool"]
    if stats.get("PowerLevel") is not None:
        lines.append(f"|power = {format_stat_value(stats.get('PowerLevel'))}")
    if stats.get("BaseDurability") is not None:
        lines.append(f"|durability = {format_stat_value(stats.get('BaseDurability'))}")
    lines.append("}}")
    lines.append("")
    return lines


def is_trinket_item(item: dict[str, Any]) -> bool:
    class_name = str(item.get("className") or "")
    if "TrinketItemData" in class_name:
        return True
    tags = item.get("itemFilterTags") or []
    return any("Trinket" in str(tag) for tag in tags)


def is_shield_item(item: dict[str, Any]) -> bool:
    class_name = str(item.get("className") or "")
    item_id = str(item.get("itemId") or "")
    if "ShieldData" in class_name:
        return True
    if "_Shield_" in item_id or "Aspis" in item_id:
        return True
    tags = item.get("itemFilterTags") or []
    return any("Shield" in str(tag) for tag in tags)


def build_trinket_stats_template(item: dict[str, Any]) -> list[str]:
    stats = item.get("stats") or {}
    lines = ["==Stats==", "{{Infobox Trinket"]
    if stats.get("BaseDurability") is not None:
        lines.append(f"|durability = {format_stat_value(stats.get('BaseDurability'))}")
    if stats.get("Weight") is not None:
        lines.append(f"|carryweight = {format_stat_value(stats.get('Weight'))}")
    description = str(item.get("description") or "").strip()
    if description:
        lines.append(f"|specialeffect = {description}")
    lines.append("}}")
    lines.append("")
    return lines


def build_shield_stats_template(item: dict[str, Any]) -> list[str]:
    stats = item.get("stats") or {}
    lines = ["==Stats==", "{{Infobox Armour"]
    if stats.get("PowerLevel") is not None:
        lines.append(f"|power = {format_stat_value(stats.get('PowerLevel'))}")
    if stats.get("BaseDurability") is not None:
        lines.append(f"|durability = {format_stat_value(stats.get('BaseDurability'))}")
    if stats.get("BlockingDamageNegation") is not None:
        lines.append(f"|block = {format_stat_value(stats.get('BlockingDamageNegation'))}")
    lines.append("}}")
    lines.append("")
    return lines


def build_recipe_lines(
    recipe: dict[str, Any] | None,
    journal: dict[str, Any] | None,
    items: dict[str, Any],
) -> list[str]:
    if not recipe:
        return []
    facility_name = None
    if journal:
        station_row = journal.get("stationRow")
        if isinstance(station_row, str):
            facility_name = STATION_NAME_MAP.get(station_row, station_row)
    lines = format_recipe_block(recipe, items, facility_name)
    lines.append("")
    created = recipe.get("createdItems", [])
    if created:
        lines.append("===Recipe tree===")
        first_output_id = created[0].get("itemId")
        first_output_name = (items.get(first_output_id) or {}).get("displayName") or humanize_item_id(str(first_output_id or "Unknown"))
        lines.append(f"{{{{Crafting Tree|{first_output_name}}}}}")
        lines.append("")
    return lines


def build_generic_item_page(
    item: dict[str, Any],
    recipe: dict[str, Any] | None,
    journal: dict[str, Any] | None,
    items: dict[str, Any],
    category: str,
    include_products: bool,
    include_item_sources: bool,
) -> str:
    name = item.get("displayName") or item.get("itemId") or "Unknown Item"
    description = item.get("description") or ""
    stats = item.get("stats") or {}

    category_label = display_category_name(category)
    item_type = category_label
    if category == "weapon":
        item_type = infer_weapon_type(item)
    elif category == "tool":
        item_type = "Tool"
    elif category == "equipment_other" and is_shield_item(item):
        item_type = "Shield"
    elif is_trinket_item(item):
        item_type = "Trinket"
    lines: list[str] = [
        "{{Infobox Item",
        f"|name = {name}",
        f"|image = {name}.png",
        f"|type = {item_type}",
    ]
    if description:
        lines.append(f"|description = {description}")
    if stats.get("Weight") is not None:
        lines.append(f"|weight = {stats.get('Weight')}")
    if stats.get("MaxStackSize") is not None:
        lines.append(f"|stacklimit = {stats.get('MaxStackSize')}")
    lines.append("}}")
    lines.append(f"'''{name}''' is a {category_label.lower()} item.")
    lines.append("")

    if category == "weapon":
        lines.extend(build_weapon_stats_template(item))
    elif category == "tool":
        lines.extend(build_tool_stats_template(item))
    elif category == "equipment_other" and is_shield_item(item):
        lines.extend(build_shield_stats_template(item))
    elif is_trinket_item(item):
        lines.extend(build_trinket_stats_template(item))
    # For unsupported categories, avoid freeform bullet stats.
    lines.extend(build_recipe_lines(recipe, journal, items))

    if include_products:
        lines.append("==Products==")
        lines.append(f"{{{{Uses material list|{name}}}}}")
        lines.append("")
    if include_item_sources:
        lines.append("==Item sources==")
        lines.append(f"{{{{Drop sources list|{name}}}}}")
        lines.append("")

    # Keep generated pages wiki-facing (no raw debug/data sections in main content).

    if journal:
        lines.append("==Journal==")
        descriptions = journal.get("descriptionPages") or []
        journal_text = descriptions[0] if descriptions else ""
        lines.append("{{Journal entry|")
        lines.append(journal_text)
        lines.append("}}")
        lines.append("")

    lines.append("<!-- Generated by generate_item_pages.py -->")
    lines.append("")
    return "\n".join(lines)


def build_quality_report(pages: list[dict[str, Any]]) -> dict[str, Any]:
    report = {
        "totalPages": len(pages),
        "withRecipeSection": 0,
        "withJournalSection": 0,
        "withProductsSection": 0,
        "withItemSourcesSection": 0,
        "weaponInfoboxCount": 0,
        "armourInfoboxCount": 0,
        "toolInfoboxCount": 0,
        "trinketInfoboxCount": 0,
        "recipeSkillEmptyCount": 0,
    }
    for page in pages:
        text = str(page.get("text", ""))
        if "==Recipe==" in text:
            report["withRecipeSection"] += 1
        if "==Journal==" in text:
            report["withJournalSection"] += 1
        if "==Products==" in text:
            report["withProductsSection"] += 1
        if "==Item sources==" in text:
            report["withItemSourcesSection"] += 1
        if "{{Infobox Weapon" in text:
            report["weaponInfoboxCount"] += 1
        if "{{Infobox Armour" in text:
            report["armourInfoboxCount"] += 1
        if "{{Infobox Tool" in text:
            report["toolInfoboxCount"] += 1
        if "{{Infobox Trinket" in text:
            report["trinketInfoboxCount"] += 1
        if "|skill = \n" in text:
            report["recipeSkillEmptyCount"] += 1
    return report


def ensure_unique_page_titles(pages: list[dict[str, Any]]) -> dict[str, Any]:
    title_to_indexes: dict[str, list[int]] = {}
    for idx, page in enumerate(pages):
        title = str(page.get("title", "")).strip()
        if not title:
            continue
        title_to_indexes.setdefault(title, []).append(idx)

    duplicate_groups = {title: indexes for title, indexes in title_to_indexes.items() if len(indexes) > 1}
    if not duplicate_groups:
        return {
            "duplicateTitleGroups": 0,
            "pagesRetitled": 0,
        }

    all_titles = {str(page.get("title", "")).strip() for page in pages if str(page.get("title", "")).strip()}
    retitled = 0
    for original_title, indexes in sorted(duplicate_groups.items()):
        for page_index in indexes:
            page = pages[page_index]
            meta = page.get("meta") if isinstance(page.get("meta"), dict) else {}
            item_id = str(meta.get("itemId", "")).strip()
            if item_id:
                candidate = f"{original_title} ({item_id})"
            else:
                candidate = f"{original_title} (dup-{page_index + 1})"

            suffix = 2
            unique_title = candidate
            while unique_title in all_titles:
                unique_title = f"{candidate}-{suffix}"
                suffix += 1

            page["title"] = unique_title
            all_titles.add(unique_title)
            retitled += 1

    return {
        "duplicateTitleGroups": len(duplicate_groups),
        "pagesRetitled": retitled,
    }


def generate_generic_category_pages_payload(
    payload: dict[str, Any],
    category: str,
    item_ids: list[str],
    item_to_enemies: dict[str, list[str]],
    item_to_chests: dict[str, list[str]],
    *,
    limit: int = 0,
    title_prefix_root: str = "User:RSDWArchiveBot/",
    summary: str = "Bot: update generated item page",
    include_products: bool = False,
    include_item_sources: bool = False,
) -> dict[str, Any]:
    items = payload.get("items", {})
    recipes = payload.get("recipes", {})
    journals = payload.get("journals", {})
    category_items: list[tuple[str, dict[str, Any]]] = []
    for item_id in item_ids:
        item = items.get(item_id)
        if isinstance(item, dict):
            category_items.append((item_id, item))
    category_items.sort(key=lambda pair: (pair[1].get("displayName") or pair[0]))
    if limit > 0:
        category_items = category_items[:limit]

    pages: list[dict[str, Any]] = []
    pages_with_products = 0
    pages_with_sources = 0
    for item_id, item in category_items:
        created_by = item.get("links", {}).get("createdByRecipes", [])
        recipe = recipes.get(created_by[0]) if created_by else None
        journal_ids = item.get("links", {}).get("journalEntries", [])
        journal = journals.get(journal_ids[0]) if journal_ids else None

        has_products_data = bool(item.get("links", {}).get("requiredInRecipes"))
        has_source_data = bool(item_to_enemies.get(item_id) or item_to_chests.get(item_id))
        use_products = include_products or has_products_data
        use_item_sources = include_item_sources or has_source_data
        if use_products:
            pages_with_products += 1
        if use_item_sources:
            pages_with_sources += 1

        page_name = sanitize_title_fragment(item.get("displayName") or item_id)
        section = title_case_category(category)
        text = build_generic_item_page(
            item=item,
            recipe=recipe,
            journal=journal,
            items=items,
            category=category,
            include_products=use_products,
            include_item_sources=use_item_sources,
        )
        pages.append(
            {
                "title": f"{title_prefix_root}{section}/{page_name}",
                "text": text,
                "summary": summary,
                "meta": {
                    "category": category,
                    "itemId": item_id,
                    "recipeId": recipe.get("recipeId") if recipe else None,
                    "journalId": journal.get("journalId") if journal else None,
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
        "pages": pages,
        "report": {
            "category": category,
            "candidateItems": len(category_items),
            "totalPages": len(pages),
            "pagesWithProductsSection": pages_with_products,
            "pagesWithItemSourcesSection": pages_with_sources,
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate wiki page payloads for all item categories")
    parser.add_argument("--catalog", default=str(DEFAULT_CATALOG), help="Path to catalog.items.json")
    parser.add_argument("--lootdata", default=str(DEFAULT_LOOTDATA), help="Path to LootData.json for source checks")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output pages JSON")
    parser.add_argument("--categories", default="all", help='Comma-separated categories or "all"')
    parser.add_argument("--limit-per-category", type=int, default=0, help="Max pages per category (0=all)")
    parser.add_argument("--title-prefix", default="User:RSDWArchiveBot/", help="Page title prefix root")
    parser.add_argument("--summary", default="Bot: update generated item page", help="Edit summary")
    parser.add_argument("--include-products", action="store_true", help="Force include Products section")
    parser.add_argument("--include-item-sources", action="store_true", help="Force include Item sources section")
    args = parser.parse_args()

    catalog_path = Path(args.catalog)
    lootdata_path = Path(args.lootdata)
    output_path = Path(args.output)
    payload = load_json(catalog_path)

    indexes = payload.get("indexes", {})
    items_by_category = indexes.get("itemsByCategory") if isinstance(indexes, dict) else {}
    if not isinstance(items_by_category, dict):
        items_by_category = {}
    available_categories = sorted(items_by_category.keys())
    selected_categories = parse_categories(args.categories, available_categories)

    item_to_enemies, item_to_chests = load_loot_indexes(lootdata_path)

    pages: list[dict[str, Any]] = []
    processed_categories: dict[str, dict[str, Any]] = {}
    skipped_categories: list[dict[str, Any]] = []

    for category in selected_categories:
        category_count = len(items_by_category.get(category, [])) if category in items_by_category else 0
        if category == "armour":
            result = generate_armour_pages_payload(
                payload,
                item_to_enemies,
                item_to_chests,
                limit=args.limit_per_category,
                title_prefix=f"{args.title_prefix}Armour/",
                summary=args.summary,
                include_products=args.include_products,
                include_item_sources=args.include_item_sources,
            )
            pages.extend(result.get("pages", []))
            processed_categories[category] = result.get("report", {})
            continue

        if category not in items_by_category:
            skipped_categories.append(
                {
                    "category": category,
                    "itemCount": category_count,
                    "reason": "Category not found in catalog index.",
                }
            )
            continue

        result = generate_generic_category_pages_payload(
            payload,
            category,
            items_by_category.get(category, []),
            item_to_enemies,
            item_to_chests,
            limit=args.limit_per_category,
            title_prefix_root=args.title_prefix,
            summary=args.summary,
            include_products=args.include_products,
            include_item_sources=args.include_item_sources,
        )
        pages.extend(result.get("pages", []))
        processed_categories[category] = result.get("report", {})

    output_payload = {
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "catalogUsed": str(catalog_path),
        "lootdataUsed": str(lootdata_path) if lootdata_path.exists() else None,
        "selectedCategories": selected_categories,
        "availableCategories": available_categories,
        "pages": pages,
        "report": {
            "totalPages": len(pages),
            "processedCategories": processed_categories,
            "skippedCategories": skipped_categories,
        },
        "quality": build_quality_report(pages),
    }
    dedupe_report = ensure_unique_page_titles(output_payload["pages"])
    output_payload["report"]["titleCollisions"] = dedupe_report
    output_payload["quality"]["duplicateTitleGroups"] = dedupe_report["duplicateTitleGroups"]
    output_payload["quality"]["pagesRetitledForUniqueTitles"] = dedupe_report["pagesRetitled"]

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output_payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    quality_path = output_path.with_suffix(".quality.json")
    quality_path.write_text(json.dumps(output_payload["quality"], indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {len(pages)} pages to: {output_path}")
    print(f"[INFO] Wrote quality report to: {quality_path}")
    print(f"[INFO] Processed categories: {', '.join(sorted(processed_categories.keys())) or '(none)'}")
    if skipped_categories:
        print(f"[INFO] Skipped categories: {len(skipped_categories)}")


if __name__ == "__main__":
    main()
