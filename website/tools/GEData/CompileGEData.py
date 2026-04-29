"""
Scan exported Unreal JSON for gameplay-effect blueprint class paths.

Walks the dataset `json/` tree for files whose name starts with `GE_`, loads each
as a JSON array of exports, finds the export whose `Type` is the blueprint class
name (file stem + `_C` when the stem does not already end with `_C`), and reads
`Class` when it is a `BlueprintGeneratedClass'...'` soft object path.

Writes `GEData.json` in this folder: an object keyed by gameplay-effect type name
with relative path, parsed class path, package path, and `runtimePath` (Unreal
mount style: `/Game/...` for core `RSDragonwilds/Content/...`, or
`/{FeatureName}/...` for plugin game-feature content before `/Content/`).

Source root matches other tools: RSDW_GE_SOURCE_DIR, RSDW_JSON_ROOT, or highest
semver `*/json` under the repo.

Example:
  python CompileGEData.py
  python CompileGEData.py --json-root E:/RSDWArchive/0.11.1/json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

INDENT = 2
SOURCE_DIR_ENV_VAR = "RSDW_GE_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"

# BlueprintGeneratedClass'RSDragonwilds/Content/.../Asset.Asset_C'
_BLUEPRINT_CLASS_RE = re.compile(
    r"^BlueprintGeneratedClass'([^']+)'$",
)

_HERE = Path(__file__).resolve().parent


def _repo_root() -> Path:
    return _HERE.parents[2]


def load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def resolve_json_root(repo_root: Path) -> Path:
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


def gameplay_effect_type_from_json_stem(stem: str) -> str:
    """e.g. GE_Foo -> GE_Foo_C; GE_Foo_C -> GE_Foo_C."""
    if stem.endswith("_C"):
        return stem
    return f"{stem}_C"


def parse_blueprint_generated_class_field(class_value: Any) -> str | None:
    if not isinstance(class_value, str):
        return None
    m = _BLUEPRINT_CLASS_RE.match(class_value.strip())
    if not m:
        return None
    return m.group(1)


def find_actor_export(exports: list[Any], expected_type: str) -> dict[str, Any] | None:
    for item in exports:
        if not isinstance(item, dict):
            continue
        if item.get("Type") != expected_type:
            continue
        inner = parse_blueprint_generated_class_field(item.get("Class"))
        if inner is not None:
            return item
    return None


def class_path_package_prefix(class_path: str) -> str:
    """RSDragonwilds/Content/.../Package.Asset -> package path without .Asset suffix."""
    if "." in class_path:
        return class_path.rsplit(".", 1)[0]
    return class_path


def runtime_path_from_class_path(class_path: str) -> str | None:
    """
    Unreal-style runtime path derived from export `classPath`.

    Split at the first ``/Content/``:
    - If the prefix before it is exactly ``RSDragonwilds``, the runtime path is
      ``/Game/`` + everything after ``/Content/`` (core game content).
    - Otherwise the runtime path is ``/`` + the last segment of that prefix
      (e.g. ``DowdunReach``) + ``/`` + the tail after ``/Content/``.

    Returns None if ``/Content/`` is missing.
    """
    marker = "/Content/"
    idx = class_path.find(marker)
    if idx < 0:
        return None
    before = class_path[:idx]
    after = class_path[idx + len(marker) :]
    if not after:
        return None
    if before == "RSDragonwilds":
        return f"/Game/{after}"
    segs = before.split("/")
    leaf = segs[-1] if segs else ""
    if not leaf:
        return None
    return f"/{leaf}/{after}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Build GEData.json from GE_*.json exports.")
    parser.add_argument(
        "--json-root",
        type=Path,
        default=None,
        help="Dataset json root (folder containing RSDragonwilds/). Overrides env discovery.",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=_HERE / "GEData.json",
        help=f"Output JSON path (default: {_HERE / 'GEData.json'})",
    )
    args = parser.parse_args()

    repo_root = _repo_root()
    json_root = args.json_root.resolve() if args.json_root else resolve_json_root(repo_root)
    if not json_root.exists():
        print(f"[ERROR] JSON root not found: {json_root}", flush=True)
        sys.exit(1)
    if not (json_root / "RSDragonwilds").exists():
        print(f"[ERROR] Expected RSDragonwilds under: {json_root}", flush=True)
        sys.exit(1)

    out_path = args.out.resolve()
    out_path.parent.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] JSON root: {json_root}", flush=True)

    by_type: dict[str, dict[str, Any]] = {}
    scanned = 0
    matched = 0
    skipped_no_array = 0
    skipped_parse = 0
    skipped_no_export = 0
    duplicate_keys = 0
    runtime_path_unset = 0

    for path in sorted(json_root.rglob("GE_*.json")):
        if not path.is_file():
            continue
        scanned += 1
        stem = path.stem
        if not stem.startswith("GE_"):
            continue
        expected_type = gameplay_effect_type_from_json_stem(stem)
        try:
            raw = load_json(path)
        except (OSError, json.JSONDecodeError) as e:
            skipped_parse += 1
            print(f"[WARN] Skip (read/parse): {path.relative_to(json_root)} — {e}", flush=True)
            continue
        if not isinstance(raw, list):
            skipped_no_array += 1
            continue

        export = find_actor_export(raw, expected_type)
        if export is None:
            skipped_no_export += 1
            continue

        class_inner = parse_blueprint_generated_class_field(export.get("Class"))
        if class_inner is None:
            skipped_no_export += 1
            continue

        rel_json = path.relative_to(json_root).as_posix()
        runtime = runtime_path_from_class_path(class_inner)
        if runtime is None:
            runtime_path_unset += 1

        entry = {
            "jsonRelative": rel_json,
            "classPath": class_inner,
            "packagePath": class_path_package_prefix(class_inner),
            "runtimePath": runtime,
        }

        if expected_type in by_type:
            duplicate_keys += 1
            print(
                f"[WARN] Duplicate Type {expected_type!r}: was {by_type[expected_type]['jsonRelative']}, "
                f"now {rel_json}",
                flush=True,
            )
        by_type[expected_type] = entry
        matched += 1

    ordered = dict(sorted(by_type.items()))

    meta = {
        "generatedBy": "website/tools/GEData/CompileGEData.py",
        "jsonRoot": str(json_root),
        "counts": {
            "geJsonFilesScanned": scanned,
            "gameplayEffectsResolved": matched,
            "skippedNotArray": skipped_no_array,
            "skippedReadOrParse": skipped_parse,
            "skippedNoMatchingExport": skipped_no_export,
            "duplicateTypeReplacements": duplicate_keys,
            "runtimePathUnset": runtime_path_unset,
        },
    }

    output_payload = {"_meta": meta, "gameplayEffects": ordered}

    out_path.write_text(
        json.dumps(output_payload, indent=INDENT, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(
        f"[INFO] Wrote {out_path} ({matched} gameplay effects from {scanned} GE_*.json files)",
        flush=True,
    )


if __name__ == "__main__":
    main()
