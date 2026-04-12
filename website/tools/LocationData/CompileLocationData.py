import json
import os
import argparse
import re
from pathlib import Path
from typing import Any, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed


INPUT_GLOB = "*.json"
MAX_WORKERS = 16
INDENT = 2
OVERWRITE = True
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

# World-placed Anima Vent actors share a UAID outer; element is on the actor (AnimaVentData) or InteractionComponent prompt.
ANIMA_VENT_OUTER_PREFIX = "BP_AnimaVent_C_UAID_"
ANIMA_VENT_ACTOR_TYPE = "BP_AnimaVent_C"
ANIMA_VENT_DATA_NAME_RE = re.compile(r"^AnimaVentData'AVD_(.+)'$")
ANIMA_VENT_INTERACTION_KEY_RE = re.compile(r"^AnimaVent\.InteractionPrompt\.(.+)$")


def resolve_source_dir(repo_root: Path, here: Path) -> Path:
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


def load_json(path: Path) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"[WARN] JSON parse failed: {path} ({exc})", flush=True)
        return None
    except Exception as exc:
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
    Map actor outer name (BP_AnimaVent_C_UAID_...) -> element suffix (e.g. Nature, Fire).
    Prefer AnimaVentData'AVD_*' on the BP actor; fall back to InteractionPrompt.Key on InteractionComponent.
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
            outer = node.get("Outer")
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
    outer = node.get("Outer")
    if not outer:
        return None, None

    props = node.get("Properties") or {}
    rel_loc = props.get("RelativeLocation") or {}

    if not isinstance(rel_loc, dict):
        return None, None

    if not all(k in rel_loc for k in ("X", "Y", "Z")):
        return None, None

    x = rel_loc["X"]
    y = rel_loc["Y"]
    z = rel_loc["Z"]

    return str(outer), f"{x} {y} {z}"


def process_file(path: Path) -> tuple[dict[str, str], int]:
    """
    Returns:
      - dict of Outer -> 'X Y Z'
      - skipped node count
    """
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
        # Last one in this file wins for the same key
        results[key] = xyz

    return results, skipped


def main() -> None:
    parser = argparse.ArgumentParser(description="Compile location chunk data into LocationData.json")
    parser.add_argument(
        "--output",
        default=str(Path(__file__).resolve().parent / "LocationData.json"),
        help="Output path for compiled location data JSON",
    )
    args = parser.parse_args()

    print("[DEBUG] Script started", flush=True)

    here = Path(__file__).resolve().parent
    repo_root = here.parents[2]
    source_dir = resolve_source_dir(repo_root, here)
    out_path = Path(args.output)

    print(f"[DEBUG] Source: {source_dir}", flush=True)
    print(f"[DEBUG] Output: {out_path}", flush=True)

    if not source_dir.exists():
        print(f"[ERROR] Source directory not found: {source_dir}", flush=True)
        return

    if out_path.exists() and not OVERWRITE:
        print(f"[INFO] Output already exists, skipping: {out_path}", flush=True)
        return

    files = sorted(source_dir.rglob(INPUT_GLOB))
    print(f"[DEBUG] Found {len(files)} source JSON files", flush=True)

    if not files:
        print("[WARN] No JSON files found.", flush=True)
        return

    combined: dict[str, str] = {}
    duplicates: list[tuple[str, str, str, str]] = []
    total_skipped = 0

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {executor.submit(process_file, path): path for path in files}

        for i, future in enumerate(as_completed(futures), start=1):
            path = futures[future]

            try:
                file_results, skipped = future.result()
                total_skipped += skipped

                for outer, xyz in file_results.items():
                    if outer in combined and combined[outer] != xyz:
                        duplicates.append((outer, combined[outer], xyz, path.name))
                    combined[outer] = xyz  # last one wins

                if i % 50 == 0 or i == 1 or i == len(futures):
                    print(
                        f"[DEBUG] Completed {i}/{len(futures)} files "
                        f"(current: {path.name})",
                        flush=True,
                    )

            except Exception as exc:
                print(f"[ERROR] Worker failed on {path}: {exc}", flush=True)

    sorted_data = dict(sorted(combined.items()))

    out_path.write_text(
        json.dumps(sorted_data, indent=INDENT, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    print(f"[INFO] Wrote {len(combined)} entries to: {out_path}", flush=True)
    print(f"[INFO] Skipped nodes: {total_skipped}", flush=True)

    if duplicates:
        print(f"[INFO] Duplicate Outer keys overwritten: {len(duplicates)}", flush=True)

    print("[DEBUG] Script finished", flush=True)


if __name__ == "__main__":
    main()