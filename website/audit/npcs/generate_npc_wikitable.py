"""
Read website/tools/NPCData/NPCData.json and print a MediaWiki sortable wikitable
for auditing: Image + Name columns like icon audits (File: {title}.png), without
checking that files exist. One row per unique displayName (title-cased), no dupes.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def title_case_words(label: str) -> str:
    """Capitalize the first letter of each whitespace-separated word (e.g. 'Tree seed' -> 'Tree Seed')."""
    return " ".join(w.capitalize() for w in label.split())


def build_wikitable(npcs: dict[str, dict]) -> tuple[str, int]:
    seen: set[str] = set()
    names: list[str] = []
    for entry in npcs.values():
        if not isinstance(entry, dict):
            continue
        raw = entry.get("displayName")
        if not isinstance(raw, str) or not raw.strip():
            continue
        name = title_case_words(raw.strip())
        key = name.casefold()
        if key in seen:
            continue
        seen.add(key)
        names.append(name)

    names.sort(key=lambda n: n.casefold())

    lines = [
        '{| class="wikitable sortable"',
        "!Image",
        "!Name",
    ]
    for name in names:
        lines.append("|-")
        lines.append(f"|[[File:{name}.png|frameless|width=84x84]]")
        lines.append(f"|[[{name}]]")

    lines.append("|}")
    return "\n".join(lines) + "\n", len(names)


def main() -> None:
    repo = repo_root_from_script()
    default_in = repo / "website" / "tools" / "NPCData" / "NPCData.json"
    default_out = Path(__file__).resolve().parent / "npc_wikitable.txt"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=default_in,
        help=f"Path to NPCData.json (default: {default_in})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=default_out,
        help=f"Output wikitext file (default: {default_out})",
    )
    parser.add_argument(
        "--stdout",
        action="store_true",
        help="Print wikitext to stdout instead of writing --output",
    )
    args = parser.parse_args()

    in_path = args.input
    path = in_path.resolve() if in_path.is_absolute() else (repo / in_path).resolve()
    if not path.is_file():
        print(f"Error: input not found: {path}", file=sys.stderr)
        sys.exit(1)

    data = json.loads(path.read_text(encoding="utf-8"))
    npcs = data.get("npcs")
    if not isinstance(npcs, dict):
        print("Error: NPCData.json missing 'npcs' object", file=sys.stderr)
        sys.exit(1)

    text, n_rows = build_wikitable(npcs)

    if args.stdout:
        sys.stdout.write(text)
    else:
        out_arg = args.output
        out = out_arg.resolve() if out_arg.is_absolute() else (repo / out_arg).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out} ({n_rows} unique NPC names).", flush=True)


if __name__ == "__main__":
    main()
