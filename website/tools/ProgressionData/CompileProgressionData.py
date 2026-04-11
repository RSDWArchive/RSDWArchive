"""Compile DT_Progression_*.json DataTables into ProgressionData.json."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))
from compiledata import enrich_nested_item_refs, load_item_name_table

INDENT = 2
FILE_GLOB = "DT_Progression_*.json"
SOURCE_DIR_ENV_VAR = "RSDW_PROGRESSION_SOURCE_DIR"
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


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def read_progression_table(path: Path, source_root: Path, repo_root: Path) -> tuple[str, dict[str, Any] | None, str | None]:
    rel = str(path.relative_to(source_root)).replace("\\", "/")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return rel, None, str(exc)

    if not isinstance(raw, list) or not raw or not isinstance(raw[0], dict):
        return rel, None, "unexpected JSON shape"

    table = raw[0]
    if table.get("Type") != "DataTable":
        pass  # still allow

    name = table.get("Name")
    if not isinstance(name, str):
        name = path.stem

    rows = table.get("Rows")
    if not isinstance(rows, dict):
        return rel, None, "missing Rows object"

    meta: dict[str, Any] = {
        "file": str(path.relative_to(repo_root)).replace("\\", "/"),
        "type": table.get("Type"),
        "name": name,
        "rowCount": len(rows),
    }
    if "Properties" in table:
        meta["rowStruct"] = (table.get("Properties") or {}).get("RowStruct")

    out: dict[str, Any] = {
        "meta": meta,
        "rows": sorted_dict(rows),
    }
    return rel, out, None


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile DT_Progression_*.json tables into ProgressionData.json.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "ProgressionData.json"),
        help="Output path for compiled JSON",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    out_path = Path(args.output)

    print("[DEBUG] CompileProgressionData started", flush=True)
    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    paths = sorted(source_root.rglob(FILE_GLOB))
    print(f"[DEBUG] Found {len(paths)} files matching {FILE_GLOB}", flush=True)

    tables: dict[str, dict[str, Any]] = {}
    parse_errors: list[dict[str, Any]] = []
    duplicate_keys: list[dict[str, Any]] = []

    for path in paths:
        rel, table, err = read_progression_table(path, source_root, repo_root)
        if err is not None:
            parse_errors.append({"path": rel, "error": err})
            continue
        assert table is not None
        if rel in tables:
            duplicate_keys.append({"path": rel})
        tables[rel] = table

    st_item_names = load_item_name_table(source_root)
    item_name_cache: dict[str, tuple[str | None, str | None]] = {}
    enrichment_misses: list[dict[str, Any]] = []
    for rel, tbl in tables.items():
        rows = tbl.get("rows")
        if isinstance(rows, dict):
            for row in rows.values():
                enrich_nested_item_refs(
                    row,
                    source_root,
                    st_item_names,
                    item_name_cache,
                    enrichment_misses,
                    rel,
                )

    compiled = {
        "version": derive_version_label(source_root),
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "glob": FILE_GLOB,
        "counts": {"filesMatched": len(paths), "tables": len(tables)},
        "tables": sorted_dict(tables),
        "issues": {
            "parseErrors": parse_errors,
            "duplicateKeys": duplicate_keys,
            "enrichmentMisses": enrichment_misses,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote ProgressionData -> {out_path}", flush=True)
    print(
        f"[INFO] Issues: parseErrors={len(parse_errors)} duplicateKeys={len(duplicate_keys)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
