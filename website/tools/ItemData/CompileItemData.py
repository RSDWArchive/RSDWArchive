"""Compile ITEM_*.json exports into ItemData.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from compiledata import (
    enrich_item_entry_display_name,
    enrich_item_entry_flavour_text,
    enrich_item_entry_skill_used,
    load_item_name_table,
    load_skill_display_names,
)

INDENT = 2
MAX_WORKERS = 16
FILE_GLOB = "ITEM_*.json"
# Mirror Pywikibot `EXCLUDED_FILE_NAME_TOKENS`: mesh-side exports, not gameplay items.
EXCLUDED_FILENAME_SUBSTRINGS = ("_MeshData_",)
SOURCE_DIR_ENV_VAR = "RSDW_ITEM_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"


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


def parse_class_name(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    if "'" in value:
        parts = value.split("'")
        if len(parts) >= 2:
            return parts[1]
    return value


def compact_first_export(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        return None
    exp = raw[0]
    out: dict[str, Any] = {
        "type": exp.get("Type"),
        "name": exp.get("Name"),
        "class": parse_class_name(exp.get("Class")),
    }
    if "Properties" in exp:
        out["properties"] = exp.get("Properties")
    return out


def process_file(path: Path, source_root: Path) -> tuple[str, dict[str, Any] | None, str | None]:
    rel = str(path.relative_to(source_root)).replace("\\", "/")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return rel, None, str(exc)
    compact = compact_first_export(raw)
    if compact is None:
        return rel, None, "unexpected JSON shape"
    return rel, compact, None


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile ITEM_*.json assets into ItemData.json.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "ItemData.json"),
        help="Output path for compiled JSON",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    out_path = Path(args.output)

    print("[DEBUG] CompileItemData started", flush=True)
    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    raw_paths = sorted(source_root.rglob(FILE_GLOB))
    excluded_by_name = 0
    paths: list[Path] = []
    for p in raw_paths:
        if any(tok in p.name for tok in EXCLUDED_FILENAME_SUBSTRINGS):
            excluded_by_name += 1
        else:
            paths.append(p)
    print(
        f"[DEBUG] Found {len(raw_paths)} files matching {FILE_GLOB} "
        f"({excluded_by_name} excluded by name pattern, {len(paths)} to process)",
        flush=True,
    )

    entries: dict[str, dict[str, Any]] = {}
    parse_errors: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futs = {ex.submit(process_file, p, source_root): p for p in paths}
        for fut in as_completed(futs):
            rel, compact, err = fut.result()
            if err is not None:
                parse_errors.append({"path": rel, "error": err})
                continue
            assert compact is not None
            if rel in entries:
                duplicate_keys.append({"path": rel})
            entries[rel] = compact

    st_item_names = load_item_name_table(source_root)
    skill_names = load_skill_display_names(source_root)
    for compact in entries.values():
        enrich_item_entry_display_name(compact, st_item_names)
        enrich_item_entry_flavour_text(compact)
        enrich_item_entry_skill_used(compact, skill_names)

    compiled = {
        "version": derive_version_label(source_root),
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "glob": FILE_GLOB,
        "excludeFilenameSubstrings": list(EXCLUDED_FILENAME_SUBSTRINGS),
        "counts": {
            "filesMatched": len(raw_paths),
            "filesExcludedByName": excluded_by_name,
            "entries": len(entries),
        },
        "entries": sorted_dict(entries),
        "issues": {
            "parseErrors": parse_errors,
            "duplicateKeys": duplicate_keys,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote ItemData -> {out_path}", flush=True)
    print(
        f"[INFO] Issues: parseErrors={len(parse_errors)} duplicateKeys={len(duplicate_keys)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
