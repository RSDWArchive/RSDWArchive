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

    for node in iter_nodes(data):
        if not isinstance(node, dict):
            skipped += 1
            continue

        outer, xyz = extract_outer_xyz(node)
        if not outer or not xyz:
            skipped += 1
            continue

        # Last one in this file wins for the same Outer
        results[outer] = xyz

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