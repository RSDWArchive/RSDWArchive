"""
Read website/tools/IconData/IconData.json and print a MediaWiki sortable wikitable
for auditing (File: uses display-name-based .png; Name column uses the same title for [[links]]).
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


def build_wikitable(icons: list[dict]) -> str:
    lines = [
        '{| class="wikitable sortable"',
        "!Image",
        "!Name",
    ]
    rows: list[tuple[str, str]] = []
    for row in icons:
        raw = row.get("displayName")
        if not isinstance(raw, str) or not raw.strip():
            continue
        name = title_case_words(raw.strip())
        rows.append((name, name))

    rows.sort(key=lambda x: x[0].casefold())

    for name, _ in rows:
        lines.append("|-")
        lines.append(f"|[[File:{name}.png|frameless|width=84x84]]")
        lines.append(f"|[[{name}]]")

    lines.append("|}")
    return "\n".join(lines) + "\n"


def main() -> None:
    repo = repo_root_from_script()
    default_in = repo / "website" / "tools" / "IconData" / "IconData.json"
    default_out = Path(__file__).resolve().parent / "icon_wikitable.txt"

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=default_in,
        help=f"Path to IconData.json (default: {default_in})",
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
    icons = data.get("icons")
    if not isinstance(icons, list):
        print("Error: IconData.json missing 'icons' array", file=sys.stderr)
        sys.exit(1)

    text = build_wikitable(icons)

    if args.stdout:
        sys.stdout.write(text)
    else:
        out_arg = args.output
        out = out_arg.resolve() if out_arg.is_absolute() else (repo / out_arg).resolve()
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(text, encoding="utf-8")
        print(f"Wrote {out} ({len(icons)} icon rows processed).", flush=True)


if __name__ == "__main__":
    main()
