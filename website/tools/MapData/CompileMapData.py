"""
Compile WorldPartition chunk-boundary GeoJSON overlays for website/Map.html.

Reads the `WorldPartitionRuntimeCellDataSpatialHash` records from the active
dataset's `L_World.json` and writes two GeoJSON overlays that Leaflet loads
directly in `website/map.js`:

  - ChunkWorldMapBounds_ContentBounds.geojson
      Per-chunk actor AABB (from `ContentBounds.Min`/`Max`).
  - ChunkWorldMapBounds_GridCell.geojson
      Per-chunk nominal tile (position +/- Extent in XY).

Source discovery mirrors the LocationData pipeline: RSDW_LOCATION_SOURCE_DIR
and RSDW_JSON_ROOT env vars are honoured, and otherwise the highest semver
folder under the repo is used.

Example:
  python CompileMapData.py
  python CompileMapData.py --l-world "E:/path/to/L_World.json" --out-dir .
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

SOURCE_DIR_ENV_VAR = "RSDW_LOCATION_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
MAP_RELATIVE_SOURCE = Path(
    "RSDragonwilds",
    "Content",
    "Maps",
    "World",
    "L_World",
    "_Generated_",
)
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"
REPO_RELATIVE_SOURCE_FALLBACK = Path(
    DEFAULT_TARGET_VERSION_FOLDER,
    "json",
    "RSDragonwilds",
    "Content",
    "Maps",
    "World",
    "L_World",
    "_Generated_",
)

_HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------------------
# Source discovery (kept in-sync with LocationData/CompileLocationData.py)
# ---------------------------------------------------------------------------


def _repo_root() -> Path:
    return _HERE.parents[2]


def resolve_generated_dir(repo_root: Path) -> Path:
    """Resolve the L_World/_Generated_ directory for the active dataset."""
    source_override = os.getenv(SOURCE_DIR_ENV_VAR, "").strip()
    if source_override:
        candidate = Path(source_override)
        if (candidate / "RSDragonwilds").exists():
            return candidate / MAP_RELATIVE_SOURCE
        if (candidate / "json" / "RSDragonwilds").exists():
            return candidate / "json" / MAP_RELATIVE_SOURCE
        return candidate

    json_override = os.getenv(JSON_ROOT_ENV_VAR, "").strip()
    if json_override:
        candidate = Path(json_override)
        if (candidate / "RSDragonwilds").exists():
            return candidate / MAP_RELATIVE_SOURCE
        if (candidate / "json" / "RSDragonwilds").exists():
            return candidate / "json" / MAP_RELATIVE_SOURCE
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
            candidates.append((parsed, json_dir / MAP_RELATIVE_SOURCE))
    if candidates:
        candidates.sort(key=lambda entry: entry[0], reverse=True)
        return candidates[0][1]

    fallback = repo_root / REPO_RELATIVE_SOURCE_FALLBACK
    if fallback.exists():
        return fallback
    return _HERE / "_Generated_"


def resolve_l_world_path(explicit: Path | None) -> Path | None:
    """Find L_World.json: explicit override, or sibling of the _Generated_ folder."""
    if explicit is not None:
        return explicit.resolve()
    generated_dir = resolve_generated_dir(_repo_root()).resolve()
    for candidate in (
        generated_dir.parent / "L_World.json",
        generated_dir.parent.parent / "L_World.json",
    ):
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# L_World.json iteration
# ---------------------------------------------------------------------------


def iter_l_world_top_level_objects(path: Path):
    """Yield each top-level JSON object (L_World.json is a huge array)."""
    try:
        import ijson  # type: ignore

        with open(path, "rb") as f:
            yield from ijson.items(f, "item")
    except ImportError:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            print(f"[ERROR] Failed reading {path}: {exc}", flush=True)
            return
        if isinstance(data, list):
            yield from data
        else:
            yield data


def unreal_ref_leaf(value: Any) -> str | None:
    """
    Convert CUE4Parse object-reference dicts into the FModel-style object leaf
    used as the chunk id.
    """
    if isinstance(value, dict):
        value = value.get("ObjectName") or value.get("AssetPathName")
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if "'" in text:
        parts = text.split("'")
        if len(parts) >= 2 and parts[1]:
            text = parts[1]
    if ":" in text:
        text = text.split(":", 1)[1]
    if "." in text:
        text = text.rsplit(".", 1)[-1]
    if "/" in text:
        text = text.rsplit("/", 1)[-1]
    return text or None


def extract_spatial_hash_by_outer(l_world: Path) -> dict[str, dict[str, Any]]:
    """Map chunk stem (Outer) -> Properties of WorldPartitionRuntimeCellDataSpatialHash."""
    out: dict[str, dict[str, Any]] = {}
    for obj in iter_l_world_top_level_objects(l_world):
        if not isinstance(obj, dict):
            continue
        if obj.get("Type") != "WorldPartitionRuntimeCellDataSpatialHash":
            continue
        outer = unreal_ref_leaf(obj.get("Outer"))
        props = obj.get("Properties")
        if not isinstance(outer, str) or not isinstance(props, dict):
            continue
        out[outer] = props
    return out


# ---------------------------------------------------------------------------
# Geometry
# ---------------------------------------------------------------------------


def xy_ring_from_min_max(min_d: dict[str, Any], max_d: dict[str, Any]) -> list[list[float]]:
    """Closed [x,y] ring from an axis-aligned box."""
    mn_x = float(min_d["X"])
    mn_y = float(min_d["Y"])
    mx_x = float(max_d["X"])
    mx_y = float(max_d["Y"])
    return [
        [mn_x, mn_y],
        [mx_x, mn_y],
        [mx_x, mx_y],
        [mn_x, mx_y],
        [mn_x, mn_y],
    ]


def xy_ring_grid_cell(position: dict[str, Any], extent: float) -> list[list[float]] | None:
    """Square in XY: center position, half-size extent on each axis."""
    try:
        px = float(position["X"])
        py = float(position["Y"])
        e = float(extent)
    except (KeyError, TypeError, ValueError):
        return None
    return [
        [px - e, py - e],
        [px + e, py - e],
        [px + e, py + e],
        [px - e, py + e],
        [px - e, py - e],
    ]


def build_chunk_entries(index: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for stem in sorted(index.keys()):
        props = index[stem]
        bb = props.get("ContentBounds")
        pos = props.get("position")
        ext = props.get("Extent")

        entry: dict[str, Any] = {
            "id": stem,
            "gridName": props.get("GridName"),
        }

        if isinstance(bb, dict) and isinstance(bb.get("Min"), dict) and isinstance(bb.get("Max"), dict):
            try:
                entry["contentBoundsRingXY"] = xy_ring_from_min_max(bb["Min"], bb["Max"])
            except (KeyError, TypeError, ValueError):
                entry["contentBoundsRingXY"] = None

        if isinstance(pos, dict) and ext is not None:
            ring = xy_ring_grid_cell(pos, float(ext))
            if ring:
                entry["gridCellRingXY"] = ring

        rows.append(entry)
    return rows


def to_geojson(features: list[dict[str, Any]], ring_key: str) -> dict[str, Any]:
    gj_features: list[dict[str, Any]] = []
    for f in features:
        rid = f.get("id")
        ring = f.get(ring_key)
        if not ring or not isinstance(rid, str):
            continue
        gj_features.append(
            {
                "type": "Feature",
                "properties": {
                    "id": rid,
                    "gridName": f.get("gridName"),
                },
                "geometry": {
                    "type": "Polygon",
                    "coordinates": [ring],
                },
            }
        )
    return {"type": "FeatureCollection", "features": gj_features}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile WorldPartition chunk-boundary GeoJSON overlays for website/Map.html "
            "from L_World.json."
        ),
    )
    parser.add_argument(
        "--l-world",
        type=Path,
        default=None,
        help="Path to L_World.json (default: auto-discover via RSDW env vars / repo scan).",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        default=_HERE,
        help="Directory for the ChunkWorldMapBounds_*.geojson files (default: this folder).",
    )
    args = parser.parse_args()

    l_world = resolve_l_world_path(args.l_world)
    if l_world is None or not l_world.exists():
        print(f"[ERROR] L_World.json not found (looked at: {l_world})", flush=True)
        sys.exit(1)

    out_dir = args.out_dir.resolve()
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] Reading: {l_world}", flush=True)
    index = extract_spatial_hash_by_outer(l_world)
    chunks = build_chunk_entries(index)
    print(f"[INFO] {len(chunks)} WorldPartition cells", flush=True)

    for ring_key, suffix in (
        ("contentBoundsRingXY", "ContentBounds"),
        ("gridCellRingXY", "GridCell"),
    ):
        gj = to_geojson(chunks, ring_key)
        path = out_dir / f"ChunkWorldMapBounds_{suffix}.geojson"
        path.write_text(
            json.dumps(gj, indent=INDENT, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[INFO] Wrote {path} ({len(gj['features'])} features)", flush=True)


if __name__ == "__main__":
    main()
