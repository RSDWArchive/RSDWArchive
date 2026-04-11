"""Compile ST_*.json string table exports into NameData.json."""

from __future__ import annotations

import argparse
import json
import os
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

INDENT = 2
FILE_GLOB = "ST_*.json"
SOURCE_DIR_ENV_VAR = "RSDW_NAME_SOURCE_DIR"
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


def parse_st_export(path: Path) -> tuple[dict[str, Any] | None, str | None]:
    """Return (payload, error_message)."""
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        return None, str(exc)
    if not isinstance(raw, list) or not raw:
        return {"kind": "unknown", "detail": "not_a_non_empty_list"}, None
    first = raw[0]
    if not isinstance(first, dict):
        return {"kind": "unknown", "detail": "first_export_not_object"}, None
    if first.get("Type") == "StringTable":
        st = first.get("StringTable")
        if isinstance(st, dict):
            kte = st.get("KeysToEntries")
            if isinstance(kte, dict):
                flat = {str(k): str(v) for k, v in kte.items()}
                return (
                    {
                        "kind": "stringTable",
                        "exportName": first.get("Name"),
                        "tableNamespace": st.get("TableNamespace"),
                        "keysToEntries": flat,
                        "keyCount": len(flat),
                    },
                    None,
                )
    return {
        "kind": "nonStandard",
        "exportType": first.get("Type"),
        "exportName": first.get("Name"),
        "detail": "expected StringTable with KeysToEntries",
    }, None


def sorted_dict(value: dict[str, Any]) -> dict[str, Any]:
    return {k: value[k] for k in sorted(value.keys())}


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile ST_*.json string tables into NameData.json.")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "NameData.json"),
        help="Output path for compiled JSON",
    )
    args = parser.parse_args()

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_root = resolve_source_root(repo_root)
    out_path = Path(args.output)

    print("[DEBUG] CompileNameData started", flush=True)
    print(f"[DEBUG] Source root: {source_root}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_root.exists():
        print(f"[ERROR] Source root not found: {source_root}", flush=True)
        return

    paths = sorted(source_root.rglob(FILE_GLOB))
    print(f"[DEBUG] Found {len(paths)} files matching {FILE_GLOB}", flush=True)

    entries: dict[str, dict[str, Any]] = {}
    parse_errors: list[dict[str, Any]] = []
    atypical: list[dict[str, Any]] = []
    total_keys = 0

    for st_path in paths:
        rel = str(st_path.relative_to(source_root)).replace("\\", "/")
        parsed, err = parse_st_export(st_path)
        if err is not None:
            parse_errors.append({"path": rel, "error": err})
            continue
        assert parsed is not None
        if parsed.get("kind") != "stringTable":
            atypical.append({"path": rel, "summary": parsed})
            continue
        total_keys += int(parsed.get("keyCount") or 0)
        entries[rel] = {"parsed": parsed}

    compiled = {
        "version": derive_version_label(source_root),
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "sourceRoot": str(source_root),
        "glob": FILE_GLOB,
        "counts": {
            "filesMatched": len(paths),
            "skippedNonStandard": len(atypical),
            "entries": len(entries),
            "totalKeys": total_keys,
        },
        "entries": sorted_dict(entries),
        "issues": {
            "parseErrors": parse_errors,
            "atypicalExports": atypical,
        },
    }

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(compiled, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")

    print(f"[INFO] Wrote NameData -> {out_path}", flush=True)
    print(
        f"[INFO] tables={len(entries)} totalKeys={total_keys} parseErrors={len(parse_errors)} "
        f"skippedNonStandard={len(atypical)}",
        flush=True,
    )


if __name__ == "__main__":
    main()
