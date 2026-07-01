"""
Compile the single master LocationData.json consumed by the website.

The pipeline runs three internal phases and writes one output file:

  1. Chunk phase
       Walks every `_Generated_` shard under L_World/_Generated_ *and* the main
       L_World.json package, indexing any node that has an `Outer` + a
       `Properties.RelativeLocation` (X, Y, Z). Keys are the normalized Outer
       (Anima vents get an element suffix so paired actors don't collide).

  2. PCG foliage phase
       Rescans the same files for BP_InteractableFoliageISMC_* nodes (PickUps,
       Tree, Sapling, etc.). For each one, world space is resolved in order:
         a) actor root RelativeLocation + TranslatedInstanceSpaceOrigin
            (root = RootComponent0 for InstancedFoliageActor_*; Box for
            BP_PCG_TileSpawner_C)
         b) L_World cell.position + TranslatedInstanceSpaceOrigin fallback
         c) CachedBounds* Origins — pick the entry with the largest SphereRadius
         d) BuiltInstanceBounds center as last resort
       When PerInstanceSMData is present, one row per instance is emitted
       (`…#inst0`, …) from root + instance Translation; the non-instance
       aggregate row is skipped when any instance row was emitted.

  3. Wiki-bounds filter
       Drops positions outside the Leaflet `maxBounds` used by website/map.js
       and website/locationdata.js, drops bad XYZ, and removes any remaining
       PCG aggregate rows that have per-instance siblings. The result overwrites
       LocationData.json — that is the final master.

Output: LocationData.json (always). Pass --debug to additionally emit
PCGLocationData.json (PCG-only flat map) and PCGLocationDataReport.json
(per-entry metadata + merge/filter stats) beside this script.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from functools import partial
from pathlib import Path
from typing import Any, Iterable

TOOLS_DIR = Path(__file__).resolve().parents[1]
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

from map_calibration import (  # noqa: E402
    MAP_X_MAX,
    MAP_X_MIN,
    MAP_Y_MAX,
    MAP_Y_MIN,
    MAP_Z_MAX,
    MAP_Z_MIN,
    map_filter_meta,
)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

INPUT_GLOB = "*.json"
MAX_WORKERS = 16
INDENT = 2

SOURCE_DIR_ENV_VAR = "RSDW_LOCATION_SOURCE_DIR"
JSON_ROOT_ENV_VAR = "RSDW_JSON_ROOT"
DEFAULT_TARGET_VERSION_FOLDER = "0.11.0.3"

MAP_RELATIVE_SOURCE = Path(
    "RSDragonwilds",
    "Content",
    "Maps",
    "World",
    "L_World",
    "_Generated_",
)
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

# World-placed Anima Vent actors share a UAID outer; the per-element tag comes
# from AnimaVentData on the actor, or falls back to InteractionPrompt.Key.
ANIMA_VENT_OUTER_PREFIX = "BP_AnimaVent_C_UAID_"
ANIMA_VENT_ACTOR_TYPE = "BP_AnimaVent_C"
ANIMA_VENT_DATA_NAME_RE = re.compile(r"^AnimaVentData'AVD_(.+)'$")
ANIMA_VENT_INTERACTION_KEY_RE = re.compile(r"^AnimaVent\.InteractionPrompt\.(.+)$")

FOLIAGE_ISMC_TYPE_PREFIX = "BP_InteractableFoliageISMC_"
ACTOR_CLASS_OBJECT_NAME_RE = re.compile(r"^BlueprintGeneratedClass'([^']+)'$")

# Website Leaflet maxBounds — must stay in sync with
# website/shared/map-calibration.js.
WIKI_X_MIN = MAP_X_MIN
WIKI_X_MAX = MAP_X_MAX
WIKI_Y_MIN = MAP_Y_MIN
WIKI_Y_MAX = MAP_Y_MAX
WIKI_Z_MIN = MAP_Z_MIN
WIKI_Z_MAX = MAP_Z_MAX

_INST_RE = re.compile(r"#inst\d+\b")
_INST_SUFFIX_RE = re.compile(r"#inst\d+$")

DEFAULT_OUTPUT = "LocationData.json"
DEFAULT_DEBUG_REPORT = "PCGLocationDataReport.json"
DEFAULT_DEBUG_FLAT = "PCGLocationData.json"


# ---------------------------------------------------------------------------
# Generic helpers
# ---------------------------------------------------------------------------


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[WARN] JSON parse failed: {path} ({exc})", flush=True)
        return None
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Failed reading file: {path} ({exc})", flush=True)
        return None


def iter_nodes(data: Any) -> Iterable[dict[str, Any]]:
    if isinstance(data, dict):
        yield data
        for value in data.values():
            yield from iter_nodes(value)
    elif isinstance(data, list):
        for item in data:
            yield from iter_nodes(item)


def unreal_ref_leaf(value: Any) -> str | None:
    """
    Convert CUE4Parse object-reference dicts into the FModel-style object leaf
    used by the website data. Examples:
      {"ObjectName": "Actor'L_World:PersistentLevel.Foo_UAID_1'"} -> Foo_UAID_1
      "Foo_UAID_1" -> Foo_UAID_1
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


def vec3_from_dict(
    d: Any, keys: tuple[str, str, str] = ("X", "Y", "Z")
) -> tuple[float, float, float] | None:
    if not isinstance(d, dict):
        return None
    try:
        return (float(d[keys[0]]), float(d[keys[1]]), float(d[keys[2]]))
    except (KeyError, TypeError, ValueError):
        return None


def vadd(
    a: tuple[float, float, float], b: tuple[float, float, float]
) -> tuple[float, float, float]:
    return (a[0] + b[0], a[1] + b[1], a[2] + b[2])


def format_xyz(t: tuple[float, float, float]) -> str:
    return f"{t[0]} {t[1]} {t[2]}"


def iter_l_world_top_level_objects(path: Path):
    """Yield each top-level JSON object (L_World.json is a huge array)."""
    try:
        import ijson  # type: ignore

        with open(path, "rb") as f:
            yield from ijson.items(f, "item")
    except ImportError:
        data = load_json(path)
        if data is None:
            return
        if isinstance(data, list):
            yield from data
        else:
            yield data


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


def default_l_world_path_from_generated_dir(generated_dir: Path) -> Path | None:
    """
    Resolve L_World.json from a WorldPartition _Generated_ directory.

    Typical layouts:
      - .../World/L_World/_Generated_/  ->  .../World/L_World.json (sibling of L_World/)
      - .../L_World/_Generated_/        ->  .../L_World/L_World.json (sibling inside)
    """
    g = generated_dir.resolve()
    for candidate in (g.parent / "L_World.json", g.parent.parent / "L_World.json"):
        if candidate.exists():
            return candidate
    return None


# ---------------------------------------------------------------------------
# Source discovery
# ---------------------------------------------------------------------------


def resolve_source_dir(repo_root: Path, here: Path) -> Path:
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
    return here / "_Generated_"


def collect_world_source_files(source_dir: Path) -> list[Path]:
    """
    Every JSON file that makes up the L_World package.

    WorldPartition splits actors across two storage locations:
      - ``L_World/_Generated_/*.json`` — runtime cell shards (most placed actors)
      - ``L_World.json`` — the "always loaded" main package (WP_IsAlwaysLoaded
        actors, root PCG spawners, etc.). Skipping it misses actors that only
        live in the main package (e.g. BP_Spawner_Pumpkin_*_C under
        BP_PCG_TileSpawner_C).
    """
    files = sorted(source_dir.rglob(INPUT_GLOB))
    for candidate in (
        source_dir.parent / "L_World.json",
        source_dir.parent.parent / "L_World.json",
    ):
        if candidate.exists() and candidate not in files:
            files.append(candidate)
            break
    return files


def derive_version_label(source_root: Path) -> str:
    name = source_root.parent.parent.parent.name
    if re.fullmatch(r"\d+(?:\.\d+)+", name):
        return name
    return "unknown"


# ---------------------------------------------------------------------------
# Chunk phase: Outer -> RelativeLocation
# ---------------------------------------------------------------------------


def parse_anima_vent_element_from_data_object_name(object_name: str | None) -> str | None:
    if not isinstance(object_name, str):
        return None
    m = ANIMA_VENT_DATA_NAME_RE.match(object_name.strip())
    return m.group(1) if m else None


def parse_anima_vent_element_from_interaction_key(key: str | None) -> str | None:
    if not isinstance(key, str):
        return None
    m = ANIMA_VENT_INTERACTION_KEY_RE.match(key.strip())
    return m.group(1) if m else None


def collect_bp_anima_vent_elements(data: Any) -> dict[str, str]:
    """
    Map actor outer name (BP_AnimaVent_C_UAID_...) -> element suffix (Nature, Fire, …).
    Prefer AnimaVentData'AVD_*' on the BP actor; fall back to InteractionPrompt.Key.
    """
    preferred: dict[str, str] = {}
    fallback: dict[str, str] = {}
    for node in iter_nodes(data):
        if not isinstance(node, dict):
            continue
        if node.get("Type") == ANIMA_VENT_ACTOR_TYPE:
            name = node.get("Name")
            if not isinstance(name, str) or not name.startswith(ANIMA_VENT_OUTER_PREFIX):
                continue
            props = node.get("Properties") or {}
            avd = props.get("AnimaVentData")
            if isinstance(avd, dict):
                el = parse_anima_vent_element_from_data_object_name(avd.get("ObjectName"))
                if el:
                    preferred[name] = el
            continue
        if node.get("Type") == "InteractionComponent":
            outer = unreal_ref_leaf(node.get("Outer"))
            if not isinstance(outer, str) or not outer.startswith(ANIMA_VENT_OUTER_PREFIX):
                continue
            props = node.get("Properties") or {}
            ip = props.get("InteractionPrompt")
            if not isinstance(ip, dict):
                continue
            el = parse_anima_vent_element_from_interaction_key(ip.get("Key"))
            if el and outer not in fallback:
                fallback[outer] = el
    out = dict(fallback)
    out.update(preferred)
    return out


def location_key_for_outer(outer: str, anima_elements: dict[str, str]) -> str:
    if outer.startswith(ANIMA_VENT_OUTER_PREFIX):
        el = anima_elements.get(outer)
        if el:
            return f"{outer}_{el}"
    return outer


def extract_outer_xyz(node: dict[str, Any]) -> tuple[str | None, str | None]:
    outer = unreal_ref_leaf(node.get("Outer"))
    if not outer:
        return None, None
    props = node.get("Properties") or {}
    rel_loc = props.get("RelativeLocation") or {}
    if not isinstance(rel_loc, dict):
        return None, None
    if not all(k in rel_loc for k in ("X", "Y", "Z")):
        return None, None
    return outer, f"{rel_loc['X']} {rel_loc['Y']} {rel_loc['Z']}"


def process_chunk_file(path: Path) -> tuple[dict[str, str], int]:
    """Chunk-phase worker: returns (Outer -> "X Y Z", skipped node count)."""
    results: dict[str, str] = {}
    skipped = 0
    data = load_json(path)
    if data is None:
        return results, skipped
    anima_elements = collect_bp_anima_vent_elements(data)
    for node in iter_nodes(data):
        if not isinstance(node, dict):
            skipped += 1
            continue
        outer, xyz = extract_outer_xyz(node)
        if not outer or not xyz:
            skipped += 1
            continue
        key = location_key_for_outer(outer, anima_elements)
        results[key] = xyz
    return results, skipped


# ---------------------------------------------------------------------------
# PCG foliage phase: BP_InteractableFoliageISMC_*
# ---------------------------------------------------------------------------


def is_interactable_foliage_ismc_type(type_name: Any) -> bool:
    return isinstance(type_name, str) and type_name.startswith(FOLIAGE_ISMC_TYPE_PREFIX)


def parse_actor_class_name(actor_class: Any) -> str | None:
    if not isinstance(actor_class, dict):
        return None
    on = actor_class.get("ObjectName")
    if not isinstance(on, str):
        return None
    m = ACTOR_CLASS_OBJECT_NAME_RE.match(on.strip())
    return m.group(1) if m else None


def flat_location_key(
    actor_class: str, outer: str, name: str, instance_index: int | None = None
) -> str:
    """Unique key for LocationData-shaped map; actorClass prefix keeps it searchable."""
    base = f"{actor_class}::{outer}/{name}"
    if instance_index is not None:
        return f"{base}#inst{instance_index}"
    return base


def build_foliage_root_map(data: Any) -> dict[str, tuple[float, float, float]]:
    """InstancedFoliageActor Outer -> RootComponent0.RelativeLocation."""
    out: dict[str, tuple[float, float, float]] = {}
    for node in iter_nodes(data):
        if not isinstance(node, dict):
            continue
        if node.get("Type") != "SceneComponent":
            continue
        if node.get("Name") != "RootComponent0":
            continue
        outer = unreal_ref_leaf(node.get("Outer"))
        if not isinstance(outer, str):
            continue
        props = node.get("Properties")
        if not isinstance(props, dict):
            continue
        v = vec3_from_dict(props.get("RelativeLocation"))
        if v:
            out[outer] = v
    return out


def build_pcg_tile_spawner_box_root_map(data: Any) -> dict[str, tuple[float, float, float]]:
    """
    BP_PCG_TileSpawner_C Outer -> Box component RelativeLocation.

    Tile spawners use BoxComponent named "Box" as RootComponent (not RootComponent0).
    Interactable ISMCs attach to that Box; world position is
    Box.RelativeLocation + TranslatedInstanceSpaceOrigin / PerInstanceSMData.Translation.
    """
    out: dict[str, tuple[float, float, float]] = {}
    for node in iter_nodes(data):
        if not isinstance(node, dict):
            continue
        if node.get("Type") != "BoxComponent":
            continue
        if node.get("Name") != "Box":
            continue
        outer = unreal_ref_leaf(node.get("Outer"))
        if not isinstance(outer, str) or not outer.startswith("BP_PCG_TileSpawner_C"):
            continue
        props = node.get("Properties")
        if not isinstance(props, dict):
            continue
        v = vec3_from_dict(props.get("RelativeLocation"))
        if v:
            out[outer] = v
    return out


def build_combined_foliage_root_map(data: Any) -> dict[str, tuple[float, float, float]]:
    """Merge InstancedFoliageActor roots and PCG tile spawner Box roots (disjoint outers)."""
    combined = dict(build_foliage_root_map(data))
    combined.update(build_pcg_tile_spawner_box_root_map(data))
    return combined


def origin_from_bounds_value(val: Any) -> tuple[float, float, float] | None:
    if not isinstance(val, dict):
        return None
    origin = val.get("Origin")
    if not isinstance(origin, dict):
        return None
    if not all(k in origin for k in ("X", "Y", "Z")):
        return None
    try:
        return (float(origin["X"]), float(origin["Y"]), float(origin["Z"]))
    except (TypeError, ValueError):
        return None


def sphere_radius_from_bounds_value(val: Any) -> float:
    if not isinstance(val, dict):
        return 0.0
    sr = val.get("SphereRadius")
    if isinstance(sr, (int, float)):
        return float(sr)
    return 0.0


def pick_world_space_xyz_bounds_heuristic(
    props: dict[str, Any],
) -> tuple[float, float, float] | None:
    """
    Prefer CachedBounds* entries with the largest SphereRadius (world aggregate),
    not max(|coord|) which often picks bogus small or grid-aligned bounds.
    Falls back to BuiltInstanceBounds center.
    """
    best: tuple[float, float, float] | None = None
    best_score = -1.0
    for key, val in props.items():
        if not isinstance(key, str) or not key.startswith("CachedBounds"):
            continue
        if not isinstance(val, dict) or not val.get("bIsValid"):
            continue
        inner = val.get("Value")
        if not isinstance(inner, dict):
            continue
        o = origin_from_bounds_value(inner)
        if not o:
            continue
        score = sphere_radius_from_bounds_value(inner)
        if score > best_score:
            best_score = score
            best = o
    if best is not None:
        return best

    bb = props.get("BuiltInstanceBounds")
    if isinstance(bb, dict):
        mn = bb.get("Min")
        mx = bb.get("Max")
        if isinstance(mn, dict) and isinstance(mx, dict):
            if all(k in mn and k in mx for k in ("X", "Y", "Z")):
                try:
                    return (
                        (float(mn["X"]) + float(mx["X"])) / 2.0,
                        (float(mn["Y"]) + float(mx["Y"])) / 2.0,
                        (float(mn["Z"]) + float(mx["Z"])) / 2.0,
                    )
                except (TypeError, ValueError):
                    pass
    return None


def compute_l_world_world_xyz(
    cell_props: dict[str, Any] | None,
    root: tuple[float, float, float] | None,
    translated: tuple[float, float, float] | None,
) -> tuple[float, float, float] | None:
    """Prefer root + translated; else cell.position + translated."""
    if not translated:
        return None
    if root is not None:
        return vadd(root, translated)
    pos = vec3_from_dict(cell_props.get("position")) if cell_props else None
    if pos is not None:
        return vadd(pos, translated)
    return None


def per_instance_translations(node: dict[str, Any]) -> list[tuple[float, float, float]]:
    """Per-instance translations from node-level PerInstanceSMData (not Properties)."""
    raw = node.get("PerInstanceSMData")
    if not isinstance(raw, list):
        return []
    out: list[tuple[float, float, float]] = []
    for inst in raw:
        if not isinstance(inst, dict):
            continue
        td = inst.get("TransformData")
        if not isinstance(td, dict):
            continue
        t = vec3_from_dict(td.get("Translation"))
        if t:
            out.append(t)
    return out


def process_pcg_file(
    path: Path,
    spatial_index: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], int, int]:
    """PCG-phase worker: returns (entries keyed by outer/name[#inst], skipped, seen)."""
    out: dict[str, dict[str, Any]] = {}
    skipped = 0
    seen = 0

    data = load_json(path)
    if data is None:
        return out, skipped, seen

    chunk_name = path.name
    chunk_stem = path.stem
    cell_props = spatial_index.get(chunk_stem) if spatial_index else None
    root_map = build_combined_foliage_root_map(data)

    for node in iter_nodes(data):
        if not isinstance(node, dict):
            continue
        type_name = node.get("Type")
        if not is_interactable_foliage_ismc_type(type_name):
            continue
        seen += 1
        outer = unreal_ref_leaf(node.get("Outer"))
        name = node.get("Name")
        if not isinstance(outer, str) or not isinstance(name, str):
            skipped += 1
            continue
        props = node.get("Properties")
        if not isinstance(props, dict):
            skipped += 1
            continue
        ac = parse_actor_class_name(props.get("ActorClass"))
        if not ac:
            skipped += 1
            continue

        translated = vec3_from_dict(props.get("TranslatedInstanceSpaceOrigin"))
        root = root_map.get(outer)

        def add_entry(
            internal_key: str,
            t: tuple[float, float, float],
            method: str,
            flat_key: str,
            inst_idx: int | None,
        ) -> None:
            row: dict[str, Any] = {
                "xyz": format_xyz(t),
                "componentType": type_name,
                "actorClass": ac,
                "outer": outer,
                "name": name,
                "flatKey": flat_key,
                "sourceChunk": chunk_name,
                "positionMethod": method,
            }
            if inst_idx is not None:
                row["instanceIndex"] = inst_idx
            out[internal_key] = row

        inst_vecs = per_instance_translations(node)
        # Per-instance: root + instance Translation. IFA uses RootComponent0; PCG tile
        # spawners use Box (see build_combined_foliage_root_map). Do not use
        # cell+Translation for PCG without Box — that was the bad pumpkin path.
        inst_only_eligible = bool(
            inst_vecs
            and (
                outer.startswith("InstancedFoliageActor_")
                or outer.startswith("BP_PCG_TileSpawner_C")
            )
        )
        if inst_only_eligible:
            added_any = False
            for i, t in enumerate(inst_vecs):
                wi: tuple[float, float, float] | None = None
                if root is not None:
                    wi = vadd(root, t)
                elif cell_props is not None and outer.startswith("InstancedFoliageActor_"):
                    wi = compute_l_world_world_xyz(cell_props, None, t)
                if wi is None:
                    continue
                method = (
                    "per_instance_root_plus_translation"
                    if root is not None
                    else "l_world_cell_plus_translated"
                )
                add_entry(
                    f"{outer}/{name}#inst{i}",
                    wi,
                    method,
                    flat_location_key(ac, outer, name, i),
                    i,
                )
                added_any = True
            if added_any:
                continue

        xyz: tuple[float, float, float] | None = None
        position_method: str | None = None

        if cell_props is not None and translated is not None:
            xyz = compute_l_world_world_xyz(cell_props, root, translated)
            if xyz is not None:
                position_method = (
                    "l_world_root_plus_translated"
                    if root is not None
                    else "l_world_cell_plus_translated"
                )

        if xyz is None:
            xyz = pick_world_space_xyz_bounds_heuristic(props)
            if xyz is not None:
                position_method = "bounds_heuristic"

        if xyz is None:
            skipped += 1
            continue

        add_entry(
            f"{outer}/{name}",
            xyz,
            position_method or "unknown",
            flat_location_key(ac, outer, name),
            None,
        )

    return out, skipped, seen


def build_pcg_flat_map(combined: dict[str, dict[str, Any]]) -> dict[str, str]:
    """LocationData.json-shaped dict: flatKey -> xyz string."""
    out: dict[str, str] = {}
    for entry in combined.values():
        fk = entry.get("flatKey")
        xyz = entry.get("xyz")
        if isinstance(fk, str) and isinstance(xyz, str):
            out[fk] = xyz
    return out


def merge_chunk_and_pcg(
    chunk_based: dict[str, str],
    pcg_flat: dict[str, str],
) -> tuple[dict[str, str], int, int]:
    """Chunk values win on key collision (PCG skipped for that key)."""
    merged = dict(chunk_based)
    same = 0
    different = 0
    for k, v in pcg_flat.items():
        if k not in merged:
            merged[k] = v
            continue
        if merged[k] == v:
            same += 1
        else:
            different += 1
    return merged, same, different


# ---------------------------------------------------------------------------
# Wiki-bounds filter
# ---------------------------------------------------------------------------


def parse_xyz(value: str) -> tuple[float, float, float] | None:
    parts = value.split()
    if len(parts) != 3:
        return None
    try:
        return (float(parts[0]), float(parts[1]), float(parts[2]))
    except ValueError:
        return None


def in_wiki_bounds(x: float, y: float, z: float) -> bool:
    return (
        WIKI_X_MIN <= x <= WIKI_X_MAX
        and WIKI_Y_MIN <= y <= WIKI_Y_MAX
        and WIKI_Z_MIN <= z <= WIKI_Z_MAX
    )


def dedupe_pcg_aggregate_when_inst_exists(
    flat: dict[str, str],
) -> tuple[dict[str, str], int]:
    """
    Drop `ActorClass::BP_PCG_TileSpawner_C_.../ComponentName` when any
    `.../ComponentName#instN` exists for the same base key.

    We want one marker per spawn; per-instance rows are the accurate ones.
    """
    inst_bases: set[str] = set()
    for k in flat:
        if "BP_PCG_TileSpawner_C" not in k:
            continue
        if not _INST_SUFFIX_RE.search(k):
            continue
        inst_bases.add(_INST_SUFFIX_RE.sub("", k))
    if not inst_bases:
        return flat, 0
    out = dict(flat)
    dropped = 0
    for k in list(out.keys()):
        if "BP_PCG_TileSpawner_C" not in k:
            continue
        if _INST_SUFFIX_RE.search(k):
            continue
        if k in inst_bases:
            del out[k]
            dropped += 1
    return out, dropped


def is_foliage_pcg_aggregate(key: str) -> bool:
    """True for flat keys like Spawner::.../BP_InteractableFoliageISMC_* without #inst."""
    if "::" not in key:
        return False
    if "BP_InteractableFoliageISMC" not in key:
        return False
    if _INST_RE.search(key):
        return False
    return True


def filter_to_wiki_bounds(
    merged: dict[str, str],
) -> tuple[dict[str, str], dict[str, int]]:
    """Drop out-of-bounds coords, bad XYZ, PCG aggregates shadowed by #inst rows."""
    input_keys = len(merged)
    merged, dropped_pcg_dup_agg = dedupe_pcg_aggregate_when_inst_exists(merged)
    out: dict[str, str] = {}
    dropped_foliage_aggregate = 0
    dropped_oob = 0
    dropped_bad_xyz = 0

    for k, v in merged.items():
        if is_foliage_pcg_aggregate(k):
            dropped_foliage_aggregate += 1
            continue
        xyz = parse_xyz(v)
        if xyz is None:
            dropped_bad_xyz += 1
            continue
        if not in_wiki_bounds(*xyz):
            dropped_oob += 1
            continue
        out[k] = v

    stats: dict[str, int] = {
        "inputKeys": input_keys,
        "keptKeys": len(out),
        "droppedPcgDupAggregate": dropped_pcg_dup_agg,
        "droppedFoliagePcgAggregate": dropped_foliage_aggregate,
        "droppedOutOfWikiBounds": dropped_oob,
        "droppedBadXYZ": dropped_bad_xyz,
    }
    return dict(sorted(out.items())), stats


def wiki_filter_meta() -> dict[str, Any]:
    return {
        "wikiBounds": map_filter_meta(),
        "dropFoliagePcgWithoutInst": True,
        "dropPcgDupAggregateWhenInstExists": True,
        "source": "website/shared/map-calibration.js + website/tools/map_calibration.py; Z band heuristic",
    }


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------


def run_chunk_phase(files: list[Path]) -> tuple[dict[str, str], int, int]:
    """Returns (Outer -> 'X Y Z', skipped nodes, duplicate-key count)."""
    combined: dict[str, str] = {}
    duplicate_count = 0
    total_skipped = 0
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_chunk_file, path): path for path in files}
        for i, future in enumerate(as_completed(futures), start=1):
            path = futures[future]
            try:
                file_results, skipped = future.result()
                total_skipped += skipped
                for outer, xyz in file_results.items():
                    if outer in combined and combined[outer] != xyz:
                        duplicate_count += 1
                    combined[outer] = xyz
                if i % 50 == 0 or i == 1 or i == len(futures):
                    print(
                        f"[DEBUG] Chunk phase {i}/{len(futures)} (current: {path.name})",
                        flush=True,
                    )
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] Chunk worker failed on {path}: {exc}", flush=True)
    return combined, total_skipped, duplicate_count


def run_pcg_phase(
    files: list[Path],
    spatial_index: dict[str, dict[str, Any]] | None,
) -> tuple[dict[str, dict[str, Any]], int, int, int]:
    """Returns (entries by outer/name[#inst], skipped, seen, duplicate-key count)."""
    combined: dict[str, dict[str, Any]] = {}
    duplicates = 0
    total_skipped = 0
    total_seen = 0
    worker = partial(process_pcg_file, spatial_index=spatial_index)
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(worker, p): p for p in files}
        for future in as_completed(futures):
            path = futures[future]
            try:
                file_entries, skipped, seen = future.result()
                total_skipped += skipped
                total_seen += seen
                for key, entry in file_entries.items():
                    if key in combined and combined[key]["xyz"] != entry["xyz"]:
                        duplicates += 1
                    combined[key] = entry
            except Exception as exc:  # noqa: BLE001
                print(f"[ERROR] PCG worker failed on {path}: {exc}", flush=True)
    return combined, total_skipped, total_seen, duplicates


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Compile the wiki-filtered LocationData.json master from the L_World "
            "WorldPartition export: chunk Outer/RelativeLocation + PCG foliage ISMC "
            "instances, filtered to the website map bounds. Pass --debug to also "
            "write PCG debug sidecars."
        )
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help=f"Output path for the master LocationData JSON (default: {DEFAULT_OUTPUT}).",
    )
    parser.add_argument(
        "--l-world",
        type=Path,
        default=None,
        help="Path to L_World.json (default: sibling of _Generated_ / L_World.json).",
    )
    parser.add_argument(
        "--no-l-world",
        action="store_true",
        help="Do not load L_World.json for the PCG phase (bounds heuristic only).",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help=(
            f"Also write debug sidecars beside this script: {DEFAULT_DEBUG_FLAT} "
            f"(PCG-only flat map) and {DEFAULT_DEBUG_REPORT} (per-entry metadata "
            "+ filter/merge stats)."
        ),
    )
    args = parser.parse_args()

    print("[INFO] CompileLocationData start", flush=True)

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_dir = resolve_source_dir(repo_root, here)
    out_path = (args.output if args.output is not None else here / DEFAULT_OUTPUT).resolve()

    print(f"[INFO] Source: {source_dir}", flush=True)
    print(f"[INFO] Output: {out_path}", flush=True)

    if not source_dir.exists():
        print(f"[ERROR] Source directory not found: {source_dir}", flush=True)
        sys.exit(1)

    files = collect_world_source_files(source_dir)
    shard_count = sum(1 for p in files if p.parent == source_dir or source_dir in p.parents)
    main_count = len(files) - shard_count
    print(
        f"[INFO] Found {len(files)} source JSON files "
        f"({shard_count} _Generated_ shards + {main_count} L_World main package)",
        flush=True,
    )
    if not files:
        print("[WARN] No JSON files found; nothing to do.", flush=True)
        sys.exit(1)

    # -- Chunk phase --------------------------------------------------------
    chunk_data, chunk_skipped, chunk_duplicates = run_chunk_phase(files)
    print(f"[INFO] Chunk phase: {len(chunk_data)} keys, skipped {chunk_skipped} nodes", flush=True)
    if chunk_duplicates:
        print(
            f"[INFO] Chunk phase: {chunk_duplicates} Outer keys overwritten (last wins)",
            flush=True,
        )

    # -- PCG foliage phase --------------------------------------------------
    l_world_path: Path | None = None
    spatial_index: dict[str, dict[str, Any]] | None = None
    if not args.no_l_world:
        l_world_path = args.l_world
        if l_world_path is None:
            l_world_path = default_l_world_path_from_generated_dir(source_dir)
        else:
            l_world_path = Path(l_world_path).resolve()
        if l_world_path is not None and l_world_path.exists():
            print(f"[INFO] L_World spatial hash: {l_world_path}", flush=True)
            spatial_index = extract_spatial_hash_by_outer(l_world_path)
            print(f"[INFO] Loaded {len(spatial_index)} WorldPartition cells", flush=True)
        else:
            print(
                f"[WARN] L_World.json not found ({l_world_path}); "
                "PCG phase using bounds heuristic only.",
                flush=True,
            )
            l_world_path = None

    pcg_entries, pcg_skipped, pcg_seen, pcg_duplicates = run_pcg_phase(files, spatial_index)
    pcg_flat = build_pcg_flat_map(pcg_entries)
    print(
        f"[INFO] PCG phase: {pcg_seen} foliage ISMC nodes seen, "
        f"{len(pcg_entries)} entries, {len(pcg_flat)} flat keys, skipped {pcg_skipped}",
        flush=True,
    )
    if pcg_duplicates:
        print(
            f"[INFO] PCG phase: {pcg_duplicates} duplicate outer/name keys "
            "with differing xyz (last wins)",
            flush=True,
        )

    # -- Merge + wiki filter -----------------------------------------------
    merged, merge_same, merge_diff = merge_chunk_and_pcg(chunk_data, pcg_flat)
    raw_merged_count = len(merged)
    final_map, filter_stats = filter_to_wiki_bounds(merged)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(final_map, indent=INDENT, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    added = raw_merged_count - len(chunk_data)
    print(
        f"[INFO] Merged {raw_merged_count} raw keys "
        f"(chunk-only: {len(chunk_data)}, new from PCG: {added})",
        flush=True,
    )
    if merge_diff:
        print(
            f"[INFO] PCG keys also in chunk data with different xyz (kept chunk): {merge_diff}",
            flush=True,
        )
    print(
        f"[INFO] Wiki filter: kept {filter_stats['keptKeys']}, "
        f"dropped {filter_stats['droppedOutOfWikiBounds']} OOB, "
        f"{filter_stats['droppedFoliagePcgAggregate']} foliage-PCG aggregates, "
        f"{filter_stats['droppedPcgDupAggregate']} PCG dup aggregates, "
        f"{filter_stats['droppedBadXYZ']} bad XYZ",
        flush=True,
    )
    print(
        f"[INFO] Wrote final master ({filter_stats['keptKeys']} keys) -> {out_path}",
        flush=True,
    )

    # -- Debug sidecars (opt-in) -------------------------------------------
    if args.debug:
        report_path = (here / DEFAULT_DEBUG_REPORT).resolve()
        flat_path = (here / DEFAULT_DEBUG_FLAT).resolve()
        report_payload: dict[str, Any] = {
            "version": derive_version_label(source_dir),
            "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
            "sourceRoot": str(source_dir.resolve()),
            "lWorldJson": str(l_world_path) if l_world_path else None,
            "description": (
                "BP_InteractableFoliageISMC_* (PickUps, Tree, Sapling, …): L_World "
                "spatial hash + root+translated when available; else CachedBounds "
                "(largest SphereRadius); per-instance rows from PerInstanceSMData "
                "when present."
            ),
            "counts": {
                "filesScanned": len(files),
                "chunkKeys": len(chunk_data),
                "chunkSkippedNodes": chunk_skipped,
                "chunkDuplicateKeyOverwrites": chunk_duplicates,
                "foliageIsmcNodesSeen": pcg_seen,
                "pcgEntries": len(pcg_entries),
                "pcgFlatKeys": len(pcg_flat),
                "pcgSkippedNoActorClassOrPosition": pcg_skipped,
                "pcgDuplicateOuterNameKeys": pcg_duplicates,
                "worldPartitionCells": len(spatial_index) if spatial_index else 0,
                "mergeRawMergedKeys": raw_merged_count,
                "mergeCollisionsSameValue": merge_same,
                "mergeCollisionsDifferentValueIgnored": merge_diff,
                "finalKeys": filter_stats["keptKeys"],
                "droppedFoliagePcgAggregate": filter_stats["droppedFoliagePcgAggregate"],
                "droppedOutOfWikiBounds": filter_stats["droppedOutOfWikiBounds"],
                "droppedBadXYZ": filter_stats["droppedBadXYZ"],
                "droppedPcgDupAggregate": filter_stats["droppedPcgDupAggregate"],
            },
            "wikiFilter": wiki_filter_meta(),
            "entries": dict(sorted(pcg_entries.items())),
        }
        report_path.write_text(
            json.dumps(report_payload, indent=INDENT, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"[INFO] Wrote debug report ({len(pcg_entries)} entries) -> {report_path}", flush=True)

        flat_sorted = dict(sorted(pcg_flat.items()))
        flat_path.write_text(
            json.dumps(flat_sorted, indent=INDENT, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(
            f"[INFO] Wrote debug PCG flat map ({len(pcg_flat)} keys) -> {flat_path}",
            flush=True,
        )

    print("[INFO] CompileLocationData done", flush=True)


if __name__ == "__main__":
    main()
