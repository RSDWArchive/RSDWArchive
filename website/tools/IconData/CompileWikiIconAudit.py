import json
from pathlib import Path

def main():
    script_dir = Path(__file__).resolve().parent
    input_path = script_dir / "IconData.json"
    output_path = script_dir / "IconWiki.txt"

    with open(input_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    icons = data.get("icons", [])

    display_names = sorted({
        entry.get("displayName")
        for entry in icons
        if isinstance(entry, dict) and entry.get("displayName")
    })

    lines = []
    lines.append('{| class="wikitable sortable"')
    lines.append("!Image")
    lines.append("!Name")

    for name in display_names:
        lines.append("|-")
        lines.append(f"|[[File:{name}.png|frameless|width=84x84]]")
        lines.append(f"|[[{name}]]")

    lines.append("|}")

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))

    print(f"Done. Extracted {len(display_names)} entries to: {output_path}")

if __name__ == "__main__":
    main()