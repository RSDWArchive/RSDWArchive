"""Build IconData.json: T_Icon_*.png files under the dataset version tree paired with display names from compiled datasets."""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

_TOOLS = Path(__file__).resolve().parent.parent
if str(_TOOLS) not in sys.path:
    sys.path.insert(0, str(_TOOLS))

from compiledata import load_config  # noqa: E402

DEFAULT_CONFIG_RELATIVE = Path("website", "data.config.json")
INDENT = 2

DATASETS: tuple[tuple[str, str], ...] = (
    ("ItemData", "ItemData.json"),
    ("PlanData", "PlanData.json"),
    ("SpellData", "SpellData.json"),
    ("VestigeData", "VestigeData.json"),
)


def repo_root_from_script() -> Path:
    return Path(__file__).resolve().parents[3]


def resolve_dataset_version_root(repo_root: Path, config: dict[str, Any]) -> Path:
    explicit = config.get("datasetTexturesRoot")
    if isinstance(explicit, str) and explicit.strip():
        p = Path(explicit.strip())
        return p if p.is_absolute() else (repo_root / p).resolve()
    ver = config.get("datasetVersion")
    if not isinstance(ver, str) or not ver.strip():
        raise ValueError("Config missing datasetVersion (or datasetTexturesRoot)")
    return (repo_root / ver.strip()).resolve()


def parse_inner_texture_name(object_name: str) -> str | None:
    if "'" not in object_name:
        return None
    parts = object_name.split("'")
    if len(parts) < 2:
        return None
    inner = parts[1]
    return inner if inner.startswith("T_Icon_") else None


def texture_id_from_object_path(object_path: str) -> str | None:
    s = object_path.replace("\\", "/").strip()
    if not s:
        return None
    seg = s.rstrip("/").split("/")[-1]
    if seg.endswith(".0"):
        seg = seg[:-2]
    return seg if seg.startswith("T_Icon_") else None


def iter_t_icon_texture_ids(obj: Any) -> Iterator[str]:
    if isinstance(obj, dict):
        on = obj.get("ObjectName")
        if isinstance(on, str):
            tid = parse_inner_texture_name(on)
            if tid:
                yield tid
        op = obj.get("ObjectPath")
        if isinstance(op, str):
            tid = texture_id_from_object_path(op)
            if tid:
                yield tid
        for v in obj.values():
            yield from iter_t_icon_texture_ids(v)
    elif isinstance(obj, list):
        for x in obj:
            yield from iter_t_icon_texture_ids(x)


def display_item_like(entry: dict[str, Any]) -> str | None:
    props = entry.get("properties")
    if isinstance(props, dict):
        name = props.get("Name")
        if isinstance(name, dict):
            s = name.get("LocalizedString") or name.get("SourceString")
            if isinstance(s, str) and s.strip():
                return s.strip()
    en = entry.get("enrichment")
    if isinstance(en, dict):
        dn = en.get("displayName")
        if isinstance(dn, str) and dn.strip():
            return dn.strip()
    return None


def display_spell(entry: dict[str, Any]) -> str | None:
    props = entry.get("properties")
    if not isinstance(props, dict):
        return None
    sd = props.get("SpellDisplayName")
    if isinstance(sd, dict):
        s = sd.get("LocalizedString") or sd.get("SourceString")
        if isinstance(s, str) and s.strip():
            return s.strip()
    return None


def collect_png_basenames(version_root: Path) -> set[str]:
    """Basenames e.g. T_Icon_Foo.png -> stem T_Icon_Foo included in set as filename for output."""
    out: set[str] = set()
    if not version_root.is_dir():
        return out
    for p in version_root.rglob("*.png"):
        if not p.is_file():
            continue
        if "T_Icon_" not in p.name:
            continue
        out.add(p.name)
    return out


def index_dataset(
    path: Path,
    dataset_label: str,
    display_fn,
) -> list[tuple[str, str, str, str]]:
    """Rows: (texture_id, display, dataset_label, entry_key)."""
    if not path.is_file():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except OSError:
        return []
    entries = raw.get("entries")
    if not isinstance(entries, dict):
        return []
    rows: list[tuple[str, str, str, str]] = []
    for key, entry in entries.items():
        if not isinstance(entry, dict):
            continue
        disp = display_fn(entry)
        if not disp:
            continue
        seen: set[str] = set()
        for tid in iter_t_icon_texture_ids(entry):
            if tid in seen:
                continue
            seen.add(tid)
            rows.append((tid, disp, dataset_label, str(key)))
    return rows


def build_texture_to_displays(
    rows: list[tuple[str, str, str, str]],
) -> tuple[dict[str, set[str]], dict[str, list[tuple[str, str, str]]]]:
    """texture_id -> set of display strings; texture_id -> list of (display, dataset, key) for provenance."""
    by_tex: dict[str, set[str]] = defaultdict(set)
    prov: dict[str, list[tuple[str, str, str]]] = defaultdict(list)
    for tid, disp, dsl, ekey in rows:
        by_tex[tid].add(disp)
        prov[tid].append((disp, dsl, ekey))
    return by_tex, prov


def pick_source(prov_list: list[tuple[str, str, str]], chosen_display: str) -> tuple[str, str]:
    candidates = [(d, ds, k) for d, ds, k in prov_list if d == chosen_display]
    candidates.sort(key=lambda x: (x[1], x[2]))
    return candidates[0][1], candidates[0][2]


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Pair T_Icon_*.png under dataset version with display names from compiled tool JSON.",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_RELATIVE),
        help="Path to website data config JSON",
    )
    args = parser.parse_args()

    repo = repo_root_from_script()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo / config_path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = load_config(config_path)
    version_root = resolve_dataset_version_root(repo, config)

    tools_dir = repo / "website" / "tools"
    all_rows: list[tuple[str, str, str, str]] = []
    for label, fname in DATASETS:
        p = tools_dir / label / fname
        if label == "SpellData":
            fn = display_spell
        else:
            fn = display_item_like
        all_rows.extend(index_dataset(p, label, fn))

    by_tex, prov = build_texture_to_displays(all_rows)
    png_names = collect_png_basenames(version_root)

    icons_out: list[dict[str, Any]] = []
    for png_name in sorted(png_names):
        if not png_name.lower().endswith(".png"):
            continue
        stem = png_name[: -len(".png")]
        if stem not in by_tex:
            continue
        displays = by_tex[stem]
        if len(displays) != 1:
            continue
        (display_name,) = tuple(displays)
        src_ds, src_key = pick_source(prov[stem], display_name)
        icons_out.append(
            {
                "fileName": png_name,
                "displayName": display_name,
                "sourceDataset": src_ds,
                "sourceEntryKey": src_key,
            }
        )

    ver = config.get("datasetVersion")
    if not isinstance(ver, str):
        ver = "unknown"

    payload = {
        "version": ver,
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "pngRoot": str(version_root),
        "counts": {
            "pngTIconCandidates": len(png_names),
            "iconsWritten": len(icons_out),
            "textureIdsIndexed": len(by_tex),
        },
        "icons": icons_out,
    }

    out_path = tools_dir / "IconData" / "IconData.json"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=INDENT, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {out_path} ({len(icons_out)} icons).", flush=True)


if __name__ == "__main__":
    main()
