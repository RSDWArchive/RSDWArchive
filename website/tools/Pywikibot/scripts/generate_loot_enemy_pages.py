import argparse
import json
import re
from pathlib import Path


DEFAULT_LOOT_JSON = Path(__file__).resolve().parent.parent / "pages" / "LootData.generated.json"
DEFAULT_NPC_JSON = Path(__file__).resolve().parent.parent / "pages" / "NPCData.generated.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "pages" / "pages.npcs.json"
DEFAULT_RELEASE = "15 April 2025"
DEFAULT_UPDATE = "RuneScape: Dragonwilds is out!"


def rarity_text(drop_chance):
    if drop_chance in (100, 100.0):
        return "Always"
    if isinstance(drop_chance, (int, float)):
        value = int(drop_chance) if float(drop_chance).is_integer() else drop_chance
        return f"{value}/100"
    return f"{drop_chance}/100"


def quantity_text(minimum, maximum):
    if minimum == maximum:
        return str(minimum)
    return f"{minimum}-{maximum}"


def simplify_item_name(item_id: str) -> str:
    parts = item_id.split("_")
    if len(parts) >= 3:
        return "_".join(parts[2:])
    return item_id


def humanize_enemy_name(enemy_name: str) -> str:
    base = enemy_name.replace("_", " ")
    # Insert spaces in PascalCase names (e.g., AbyssalDemon -> Abyssal Demon)
    base = re.sub(r"(?<!^)(?=[A-Z])", " ", base)
    return re.sub(r"\s+", " ", base).strip()


def flatten_affinities(affinities: list[dict], target: str) -> str | None:
    values = []
    for entry in affinities:
        if not isinstance(entry, dict):
            continue
        affinity = str(entry.get("affinity", ""))
        if not affinity.endswith(target):
            continue
        tag = str(entry.get("damageTypeTag", ""))
        short = tag.split(".")[-1].strip()
        if short:
            values.append(short)
    if not values:
        return None
    return ", ".join(sorted(set(values)))


def infer_aggressive(gameplay_tags: list[str]) -> str | None:
    tags = set(gameplay_tags)
    if "AI.Aggressive" in tags:
        return "Yes"
    if "AI.Passive" in tags:
        return "No"
    return None


def infer_race(gameplay_tags: list[str]) -> str | None:
    categories: list[str] = []
    for tag in gameplay_tags:
        if not isinstance(tag, str):
            continue
        if ".Category." not in tag:
            continue
        categories.append(tag.split(".Category.", 1)[1].strip())
    if not categories:
        return None
    return ", ".join(sorted(set(filter(None, categories))))


def extract_journal_affinities(journal_text: str) -> tuple[str | None, str | None, str]:
    lines = [line.strip() for line in journal_text.replace("\r\n", "\n").split("\n")]
    weakness = None
    resistance = None
    kept_lines: list[str] = []
    for line in lines:
        if line.lower().startswith("weakness:"):
            value = line.split(":", 1)[1].strip()
            if value:
                weakness = value
            continue
        if line.lower().startswith("resistance:"):
            value = line.split(":", 1)[1].strip()
            if value:
                resistance = value
            continue
        kept_lines.append(line)
    cleaned = "\n".join(kept_lines).strip()
    return weakness, resistance, cleaned


def build_infobox_location(locations: list[str]) -> list[str]:
    if not locations:
        return []
    unique_locations = sorted(set(locations))
    first = unique_locations[0]
    lines = [f"|location = * [[{first}]]"]
    for location in unique_locations[1:]:
        lines.append(f"* [[{location}]]")
    return lines


def sanitize_title_fragment(value: str) -> str:
    # Avoid problematic title characters and accidental subpage nesting.
    out = value.replace("/", " - ")
    out = re.sub(r"[#<>[\]|{}]", "", out)
    out = re.sub(r"\s+", " ", out).strip()
    return out


def build_page_title(enemy_name: str, npc_record: dict | None, title_prefix: str) -> str:
    display = None
    if isinstance(npc_record, dict):
        raw_display = npc_record.get("displayName")
        if isinstance(raw_display, str) and raw_display.strip():
            display = raw_display.strip()
    if not display:
        display = humanize_enemy_name(enemy_name)

    stable_id = enemy_name
    title_core = f"{sanitize_title_fragment(display)} ({sanitize_title_fragment(stable_id)})"
    return f"{title_prefix}{title_core}"


def infer_power_level(enemy_data: dict) -> str | None:
    values: list[float] = []
    for source in enemy_data.get("sources", []):
        value = source.get("minimumPowerLevel")
        if isinstance(value, (int, float)):
            values.append(float(value))
    if not values:
        return None
    low = min(values)
    high = max(values)
    if low == high:
        return str(int(low)) if low.is_integer() else str(low)
    low_text = str(int(low)) if low.is_integer() else str(low)
    high_text = str(int(high)) if high.is_integer() else str(high)
    return f"{low_text}-{high_text}"


def build_enemy_wikicode(
    enemy_name: str,
    drops: list[dict],
    simplify_names: bool,
    npc_record: dict | None,
    power_level: str | None,
    release: str,
    update: str,
) -> str:
    fallback_page_name = humanize_enemy_name(enemy_name)
    page_name = fallback_page_name
    health = None
    weakness = None
    resistance = None
    immune = None
    aggressive = None
    race = None
    location = None
    respawn = None
    description = None
    location_values: list[str] = []
    if isinstance(npc_record, dict):
        display_name = npc_record.get("displayName")
        if isinstance(display_name, str) and display_name.strip():
            page_name = display_name.strip()
        combat = npc_record.get("combat", {})
        if isinstance(combat, dict):
            health = combat.get("maxHealth")
            affinities = combat.get("damageTypeAffinities", [])
            if isinstance(affinities, list):
                weakness = flatten_affinities(affinities, "Weakness")
                resistance = flatten_affinities(affinities, "Resistance")
                immune = flatten_affinities(affinities, "Immune")
        classification = npc_record.get("classification", {})
        if isinstance(classification, dict):
            gameplay_tags = classification.get("gameplayTags", [])
            if isinstance(gameplay_tags, list):
                tag_values = [str(tag) for tag in gameplay_tags]
                aggressive = infer_aggressive(tag_values)
                race = infer_race(tag_values)
        journal = npc_record.get("journal", {})
        if isinstance(journal, dict):
            locations = journal.get("locations", [])
            if isinstance(locations, list):
                location_values = [str(item).strip() for item in locations if isinstance(item, str) and item.strip()]
                if location_values:
                    location = ", ".join(sorted(set(location_values)))
            raw_description = journal.get("description")
            if isinstance(raw_description, str) and raw_description.strip():
                description = raw_description.replace("\r\n", "\n").strip()
        spawning = npc_record.get("spawning", {})
        if isinstance(spawning, dict):
            spawn_power = spawning.get("powerLevel")
            if isinstance(spawn_power, str) and spawn_power.strip():
                power_level = spawn_power.strip()
            spawn_respawn = spawning.get("respawn")
            if isinstance(spawn_respawn, str) and spawn_respawn.strip():
                respawn = spawn_respawn.strip()
            elif spawning.get("shouldRespawn") is False:
                respawn = "No"

    lines = [
        f"{{{{External|rs={page_name}|os={page_name}}}}}",
        "{{Infobox Monster",
        f"|name = {page_name}",
        f"|image = {page_name}.png",
        f"|release = {release}",
        f"|update = {update}",
    ]
    if power_level:
        lines.append(f"|power_level = {power_level}")
    if isinstance(health, (int, float)):
        health_text = str(int(health)) if float(health).is_integer() else str(health)
        lines.append(f"|health = {health_text}")
    lines.extend(build_infobox_location(location_values))
    if race:
        lines.append(f"|race = {race}")
    journal_weakness = None
    journal_resistance = None
    if description:
        journal_weakness, journal_resistance, description = extract_journal_affinities(description)
    if not weakness:
        weakness = journal_weakness
    if not resistance:
        resistance = journal_resistance
    if weakness:
        lines.append(f"|weakness = {weakness}")
    if resistance:
        lines.append(f"|resistance = {resistance}")
    if immune:
        lines.append(f"|immune = {immune}")
    if aggressive:
        lines.append(f"|aggressive = {aggressive}")
    if respawn:
        lines.append(f"|respawn = {respawn}")
    lines.extend(
        [
        "}}",
        f"The '''{page_name}''' is a monster.",
        "",
        "==Location==",
        f"{{{{Map|{page_name}}}}}",
        "",
        "==Drops==",
        ]
    )

    always_drops = []
    other_drops = []
    for drop in drops:
        item_id = str(drop.get("itemId", ""))
        drop_display_name = drop.get("itemDisplayName")
        if isinstance(drop_display_name, str) and drop_display_name.strip():
            display_name = drop_display_name.strip()
        else:
            display_name = simplify_item_name(item_id) if simplify_names else item_id
        qty = quantity_text(drop.get("minimumDropAmount"), drop.get("maximumDropAmount"))
        rarity = rarity_text(drop.get("dropChance"))
        drop_line = f"{{{{DropsLine|name={display_name}|quantity={qty}|rarity={rarity}}}}}"
        if rarity == "Always":
            always_drops.append(drop_line)
        else:
            other_drops.append(drop_line)

    if always_drops:
        lines.append("===100%===")
        lines.append("{{DropsTableHead}}")
        lines.extend(always_drops)
        lines.append("{{DropsTableBottom}}")
        lines.append("")
    if other_drops:
        lines.append("===Other===")
        lines.append("{{DropsTableHead}}")
        lines.extend(other_drops)
        lines.append("{{DropsTableBottom}}")
    lines.append("")
    lines.append("==Journal==")
    lines.append("{{Journal_entry|")
    lines.append(description or "Journal entry pending.")
    lines.append("}}")
    lines.append("")
    lines.append("<!-- Generated by generate_loot_enemy_pages.py -->")
    lines.append("")
    return "\n".join(lines)


def build_npc_lookup(npc_payload: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    npcs = npc_payload.get("npcs", {})
    if not isinstance(npcs, dict):
        return {}, {}
    by_id: dict[str, dict] = {}
    for npc_id, record in npcs.items():
        if isinstance(record, dict):
            by_id[str(npc_id)] = record
    by_loot_row: dict[str, dict] = {}
    for record in by_id.values():
        loot = record.get("loot", {})
        if not isinstance(loot, dict):
            continue
        loot_row = loot.get("enemyLootRowName")
        if not isinstance(loot_row, str) or not loot_row:
            continue
        # First record wins to keep deterministic behavior.
        by_loot_row.setdefault(loot_row, record)
    return by_id, by_loot_row


def main():
    parser = argparse.ArgumentParser(description="Generate NPC/monster wiki pages from compiled LootData + NPCData")
    parser.add_argument("--loot-json", default=str(DEFAULT_LOOT_JSON), help="Path to LootData.json")
    parser.add_argument("--npc-json", default=str(DEFAULT_NPC_JSON), help="Path to compiled NPCData.json")
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT), help="Path to output pages JSON")
    parser.add_argument("--limit", type=int, default=0, help="Max enemies to output (0 = all)")
    parser.add_argument("--title-prefix", default="User:RSDWArchiveBot/Loot/Enemy/", help="Wiki page title prefix")
    parser.add_argument("--summary", default="Bot: update generated enemy loot table", help="Edit summary")
    parser.add_argument("--simplify-names", action="store_true", help="Strip first two underscore groups from item IDs")
    parser.add_argument("--release", default=DEFAULT_RELEASE, help="Release string for infobox monster")
    parser.add_argument("--update", default=DEFAULT_UPDATE, help="Update string for infobox monster")
    args = parser.parse_args()

    loot_path = Path(args.loot_json)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.loads(loot_path.read_text(encoding="utf-8"))
    npc_payload = {}
    npc_path = Path(args.npc_json)
    if npc_path.exists():
        npc_payload = json.loads(npc_path.read_text(encoding="utf-8"))
    npc_by_id, npc_by_loot_row = build_npc_lookup(npc_payload)

    enemies = payload.get("enemies", {})
    if not isinstance(enemies, dict):
        raise ValueError("LootData.json missing valid enemies section")

    pages = []
    enemy_names = sorted(enemies.keys())
    if args.limit > 0:
        enemy_names = enemy_names[: args.limit]

    for enemy_name in enemy_names:
        enemy_data = enemies.get(enemy_name, {})
        drops = enemy_data.get("drops", [])
        if not drops:
            continue

        power_level = infer_power_level(enemy_data)
        npc_record = npc_by_loot_row.get(enemy_name) or npc_by_id.get(enemy_name)
        text = build_enemy_wikicode(
            enemy_name,
            drops,
            args.simplify_names,
            npc_record,
            power_level,
            args.release,
            args.update,
        )
        title = build_page_title(enemy_name, npc_record, args.title_prefix)
        pages.append(
            {
                "title": title,
                "text": text,
                "summary": args.summary,
            }
        )

    output_path.write_text(json.dumps({"pages": pages}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {len(pages)} pages to: {output_path}")


if __name__ == "__main__":
    main()
