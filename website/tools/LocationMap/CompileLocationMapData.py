"""
Build LocationMapData.json: categorized actor pins for LocationMap.html.

Reads website/tools/LocationData/LocationData.json (one entry per placed actor
or per PCG foliage instance, value = "x y z"), parses each key into its asset
class, applies the rules in category-rules.json (drops first, then ordered
categories, with a fallback bucket), and writes a compact per-category list of
points.

Output schema:
{
  "_meta": { "generatedBy": ..., "counts": { ... }, "topUncategorized": [...] },
  "categories": {
    "<category>": {
      "label": "...",
      "icon": "icons/...png",
      "points": [ /* present when this category has no subcategories */ ],
      "subcategories": {
        "<sub>": {
          "label": "...",
          "icon": "icons/...png",
          "points": [
            { "name": "<asset>", "uaid": "<uaid or null>", "x": <num>, "y": <num>, "z": <num> },
            ...
          ]
        }
      }
    },
    ...
  }
}
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
from collections import Counter, OrderedDict
from pathlib import Path
from typing import Any

INDENT = 2

_HERE = Path(__file__).resolve().parent
_DEFAULT_INPUT = _HERE.parent / "LocationData" / "LocationData.json"
_DEFAULT_RULES = _HERE / "category-rules.json"
_DEFAULT_OUTPUT = _HERE / "LocationMapData.json"
_DEFAULT_ICONDATA = _HERE.parent / "IconData" / "IconData.json"
_REPO_ROOT = _HERE.parents[2]
_WEBSITE_ROOT = _HERE.parents[1]
_DEFAULT_CONFIG = _REPO_ROOT / "website" / "data.config.json"
# Folder where referenced icon PNGs are copied so the website is self-contained
# (GitHub Pages publishes only the website/ folder, so we cannot reference
# ../0.11.1.4/...).
_ICON_OUT_DIR = _HERE / "icons"
# Path emitted in LocationMapData.json (relative to LocationMap.html, which
# lives at website/LocationMap.html).
_ICON_WEB_PREFIX = "tools/LocationMap/icons"

# Placed-actor key:    <Asset>_UAID_<hex>_<id>
# Foliage-instance key: <Spawner>::InstancedFoliageActor_<...>/<ISMC>_C_<n>#inst<i>
_UAID_RE = re.compile(
    r"^(?P<asset>.+?)_UAID_(?P<uaid>[0-9A-Fa-f]+(?:_[0-9A-Fa-f]+)?_[0-9]+)"
    r"(?:_(?P<variant>[A-Za-z0-9]+))?$"
)
# Fallback: some actors carry a bare _<longhex>_<digits> suffix without a UAID literal,
# e.g. BP_Trap_Fire_v1_C_c664e899a429c1db_10. Strip it so we collapse instances.
_HEX_SUFFIX_RE = re.compile(r"^(?P<asset>.+?_C)_[0-9A-Fa-f]{12,}_[0-9]+$")
# Foliage / spawner-instance key: <Asset>::<Spawner>_C_<...>/<ISMC>_<n>#inst<i>
# (covers ::InstancedFoliageActor_..., ::BP_PCG_TileSpawner_C_..., etc.)
_FOLIAGE_RE = re.compile(r"^(?P<asset>.+?)::")


def parse_asset_class(key: str) -> tuple[str, str | None, str | None]:
    """Return (asset class, uaid-or-None, variant-or-None) for a LocationData key.

    Some actors (notably BP_AnimaVent_C) encode an element variant after the UAID,
    e.g. ..._UAID_<hex>_<id>_Law. We surface that as 'variant' so subcategory rules
    can target a synthetic match key '<asset>/<variant>'."""
    m = _UAID_RE.match(key)
    if m:
        return m.group("asset"), m.group("uaid"), m.group("variant")
    m = _HEX_SUFFIX_RE.match(key)
    if m:
        return m.group("asset"), None, None
    m = _FOLIAGE_RE.match(key)
    if m:
        return m.group("asset"), None, None
    return key, None, None


def parse_position(value: Any) -> tuple[float, float, float] | None:
    if not isinstance(value, str):
        return None
    parts = value.strip().split()
    if len(parts) != 3:
        return None
    try:
        return float(parts[0]), float(parts[1]), float(parts[2])
    except ValueError:
        return None


def display_path(path: Path) -> str:
    try:
        return path.resolve().relative_to(_REPO_ROOT).as_posix()
    except ValueError:
        return str(path)


def resolve_texture_root_from_config(config_path: Path) -> Path | None:
    if not config_path.exists():
        return None
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"[WARN] Could not read texture root config {config_path}: {exc}", flush=True)
        return None
    if not isinstance(config, dict):
        return None

    explicit = config.get("datasetTexturesRoot")
    if isinstance(explicit, str) and explicit.strip():
        candidate = Path(explicit.strip())
        return candidate if candidate.is_absolute() else (_REPO_ROOT / candidate).resolve()

    version = config.get("datasetVersion")
    if isinstance(version, str) and version.strip():
        return (_REPO_ROOT / version.strip()).resolve()
    return None


def resolve_texture_root(icondata_path: Path, config_path: Path) -> Path | None:
    env_root = os.environ.get("RSDW_TEXTURE_ROOT")
    if env_root:
        candidate = Path(env_root)
        if candidate.exists():
            return candidate
        print(f"[WARN] RSDW_TEXTURE_ROOT does not exist: {candidate}", flush=True)

    if icondata_path.exists():
        payload = json.loads(icondata_path.read_text(encoding="utf-8"))
        png_root_str = payload.get("pngRoot") if isinstance(payload, dict) else None
        if isinstance(png_root_str, str) and png_root_str.strip():
            png_root = Path(png_root_str)
            if png_root.exists():
                return png_root
            print(
                f"[WARN] IconData.pngRoot does not exist: {png_root}; "
                f"falling back to {config_path}",
                flush=True,
            )
        else:
            print("[WARN] IconData.json missing 'pngRoot'; falling back to config.", flush=True)
    else:
        print(f"[WARN] IconData.json not found at {icondata_path}; falling back to config.", flush=True)

    config_root = resolve_texture_root_from_config(config_path)
    if config_root and config_root.exists():
        return config_root
    if config_root:
        print(f"[WARN] Texture root from config does not exist: {config_root}", flush=True)
    return None


def build_icon_index(icondata_path: Path, config_path: Path) -> dict[str, str]:
    """
    Returns { 'T_Icon_Foo': '<path-relative-to-website-root>' } for every
    T_Icon_*.png we can locate under IconData.pngRoot. The website is served
    from website/, so paths are returned with the appropriate '../' prefix
    so that <img src="<path>"> works directly from any HTML in website/.
    """
    png_root = resolve_texture_root(icondata_path, config_path)
    if png_root is None:
        print("[WARN] No valid texture root found; iconRef will not be resolved.", flush=True)
        return {}

    # Glob all T_Icon_*.png and T_Map_Icon_*.png files under the version textures tree.
    # Map stem -> absolute source path so we can copy referenced icons into the
    # website/ tree later (so they ship with GitHub Pages).
    index: dict[str, str] = {}
    for pattern in ("T_Icon_*.png", "T_Icons_*.png", "T_Map_Icon_*.png", "T_NavIcons_*.png"):
        for png in png_root.rglob(pattern):
            stem = png.stem
            if stem in index:
                continue  # keep first hit; duplicates are extremely rare
            index[stem] = str(png.resolve())
    print(f"[INFO] Indexed {len(index)} icon PNGs from {png_root}", flush=True)
    return index


def resolve_icon(icon_field: Any, icon_ref: Any, icon_index: dict[str, str],
                 referenced: set[str]) -> str | None:
    """Prefer iconRef when it resolves; otherwise fall back to literal icon path.

    Returns the website-relative path that will exist after copy_referenced_icons()
    runs, and records the stem in `referenced` so the source PNG gets copied.
    """
    if isinstance(icon_ref, str) and icon_ref:
        # Allow either 'T_Icon_Foo' or 'T_Icon_Foo.png'.
        stem = icon_ref[:-4] if icon_ref.lower().endswith(".png") else icon_ref
        if stem in icon_index:
            referenced.add(stem)
            return f"{_ICON_WEB_PREFIX}/{stem}.png"
        print(f"[WARN] Unresolved iconRef: {icon_ref!r}", flush=True)
    if isinstance(icon_field, str) and icon_field:
        return icon_field
    return None


def copy_referenced_icons(referenced: set[str], icon_index: dict[str, str]) -> int:
    """Copy each referenced icon's source PNG into _ICON_OUT_DIR.

    Removes any stale PNGs in _ICON_OUT_DIR that are no longer referenced so the
    folder stays small. Returns the number of icons present after sync.
    """
    _ICON_OUT_DIR.mkdir(parents=True, exist_ok=True)
    wanted = {f"{stem}.png" for stem in referenced}
    # Remove stale icons.
    for existing in _ICON_OUT_DIR.glob("*.png"):
        if existing.name not in wanted:
            try:
                existing.unlink()
            except OSError:
                pass
    # Copy in new/updated icons.
    for stem in sorted(referenced):
        src = icon_index.get(stem)
        if not src:
            continue
        dst = _ICON_OUT_DIR / f"{stem}.png"
        try:
            shutil.copyfile(src, dst)
        except OSError as exc:
            print(f"[WARN] Failed to copy icon {stem}: {exc}", flush=True)
    return len(list(_ICON_OUT_DIR.glob("*.png")))


def compile_rules(rules_payload: dict) -> tuple[list[re.Pattern], list[dict], dict]:
    drop_raw = rules_payload.get("drop", []) or []
    drop_patterns = [re.compile(p) for p in drop_raw if isinstance(p, str)]

    categories_raw = rules_payload.get("categories", []) or []
    compiled: list[dict] = []
    for entry in categories_raw:
        if not isinstance(entry, dict):
            continue
        match_list = entry.get("match", []) or []
        subcats_raw = entry.get("subcategories", []) or []
        subcats: list[dict] = []
        for sub in subcats_raw:
            if not isinstance(sub, dict):
                continue
            sub_match = sub.get("match", []) or []
            subcats.append({
                "subcategory": sub["subcategory"],
                "label": sub.get("label", sub["subcategory"]),
                "icon": sub.get("icon"),
                "iconRef": sub.get("iconRef"),
                "patterns": [re.compile(p) for p in sub_match if isinstance(p, str)],
            })
        compiled.append(
            {
                "category": entry["category"],
                "label": entry.get("label", entry["category"]),
                "icon": entry.get("icon"),
                "iconRef": entry.get("iconRef"),
                "patterns": [re.compile(p) for p in match_list if isinstance(p, str)],
                "subcategories": subcats,
            }
        )

    fallback = rules_payload.get("fallback") or {
        "category": "other",
        "label": "Other",
        "icon": None,
    }
    return drop_patterns, compiled, fallback


def classify(asset: str, drop_patterns: list[re.Pattern], categories: list[dict], variant: str | None = None) -> tuple[str | None, str | None]:
    """
    Returns (category, subcategory):
      (None, None)            -> drop
      ("", None)              -> fallback bucket (no category match)
      ("<cat>", None)         -> matched a leaf category (no subcategories)
      ("<cat>", "<sub>")      -> matched a category and one of its subcategories
      ("<cat>", "")           -> matched a category that has subcategories but none hit
                                 (caller should send this to '<cat>_other').

    Subcategory regexes are tested against a synthetic '<asset>/<variant>' key
    when a variant is present (so rules like '^BP_AnimaVent_C/Law$' can target
    one element of a multi-element actor) AND against the bare asset class.
    """
    sub_match_keys = [asset]
    if variant:
        sub_match_keys.insert(0, f"{asset}/{variant}")
    for pat in drop_patterns:
        if pat.search(asset):
            return None, None
    for cat in categories:
        for pat in cat["patterns"]:
            if pat.search(asset):
                if not cat["subcategories"]:
                    return cat["category"], None
                for sub in cat["subcategories"]:
                    for spat in sub["patterns"]:
                        for mk in sub_match_keys:
                            if spat.search(mk):
                                return cat["category"], sub["subcategory"]
                return cat["category"], ""
    return "", None


def main() -> None:
    parser = argparse.ArgumentParser(description="Build LocationMapData.json from LocationData.json.")
    parser.add_argument("--input", type=Path, default=_DEFAULT_INPUT,
                        help=f"Input LocationData.json (default: {_DEFAULT_INPUT})")
    parser.add_argument("--rules", type=Path, default=_DEFAULT_RULES,
                        help=f"category-rules.json (default: {_DEFAULT_RULES})")
    parser.add_argument("--out", type=Path, default=_DEFAULT_OUTPUT,
                        help=f"Output LocationMapData.json (default: {_DEFAULT_OUTPUT})")
    parser.add_argument("--icondata", type=Path, default=_DEFAULT_ICONDATA,
                        help=f"IconData.json for resolving iconRef -> PNG path (default: {_DEFAULT_ICONDATA})")
    parser.add_argument("--config", type=Path, default=_DEFAULT_CONFIG,
                        help=f"website data config fallback for texture root (default: {_DEFAULT_CONFIG})")
    parser.add_argument("--top-unknown", type=int, default=40,
                        help="Report this many most-common uncategorized asset classes in _meta.")
    args = parser.parse_args()

    in_path = args.input.resolve()
    rules_path = args.rules.resolve()
    out_path = args.out.resolve()

    if not in_path.exists():
        print(f"[ERROR] Input not found: {in_path}", flush=True)
        sys.exit(1)
    if not rules_path.exists():
        print(f"[ERROR] Rules file not found: {rules_path}", flush=True)
        sys.exit(1)

    print(f"[INFO] Reading {in_path}", flush=True)
    location_data = json.loads(in_path.read_text(encoding="utf-8"))
    if not isinstance(location_data, dict):
        print("[ERROR] LocationData.json must be a JSON object.", flush=True)
        sys.exit(1)

    rules_payload = json.loads(rules_path.read_text(encoding="utf-8"))
    drop_patterns, categories, fallback = compile_rules(rules_payload)
    icon_index = build_icon_index(args.icondata.resolve(), args.config.resolve())
    referenced_icons: set[str] = set()

    # Pre-build the output container in declared category/subcategory order.
    bucket_meta: OrderedDict[str, dict[str, Any]] = OrderedDict()
    for cat in categories:
        cat_payload: dict[str, Any] = {
            "label": cat["label"],
            "icon": resolve_icon(cat["icon"], cat.get("iconRef"), icon_index, referenced_icons),
        }
        if cat["subcategories"]:
            sub_payload: OrderedDict[str, dict[str, Any]] = OrderedDict()
            for sub in cat["subcategories"]:
                sub_payload[sub["subcategory"]] = {
                    "label": sub["label"],
                    "icon": resolve_icon(sub["icon"], sub.get("iconRef"), icon_index, referenced_icons),
                    "points": [],
                }
            # Auto-create a per-parent fallback bucket for assets that match the
            # parent rule but none of the subcategories.
            sub_payload["_other"] = {
                "label": f"{cat['label']} (other)",
                "icon": cat_payload["icon"],
                "points": [],
            }
            cat_payload["subcategories"] = sub_payload
        else:
            cat_payload["points"] = []
        bucket_meta[cat["category"]] = cat_payload

    fallback_key = fallback.get("category", "other")
    bucket_meta[fallback_key] = {
        "label": fallback.get("label", "Other"),
        "icon": fallback.get("icon"),
        "points": [],
    }

    counts: Counter = Counter()                          # parent-level counts
    sub_counts: dict[str, Counter] = {}                  # parent -> Counter(sub -> n)
    asset_per_bucket: dict[str, Counter] = {}            # composite key -> Counter(asset -> n)
    unknown_asset_counts: Counter = Counter()
    dropped = 0
    bad_position = 0
    total = 0

    def composite_key(cat: str, sub: str | None) -> str:
        return f"{cat}/{sub}" if sub else cat

    for key, value in location_data.items():
        total += 1
        asset, uaid, variant = parse_asset_class(key)
        cat, sub = classify(asset, drop_patterns, categories, variant)
        if cat is None:
            dropped += 1
            continue

        pos = parse_position(value)
        if pos is None:
            bad_position += 1
            continue

        if cat == "":
            # No category matched -> global fallback.
            target_cat = fallback_key
            target_sub: str | None = None
            unknown_asset_counts[asset] += 1
            point_list = bucket_meta[target_cat]["points"]
        else:
            target_cat = cat
            cat_payload = bucket_meta[target_cat]
            if "subcategories" in cat_payload:
                target_sub = sub if sub else "_other"
                point_list = cat_payload["subcategories"][target_sub]["points"]
            else:
                target_sub = None
                point_list = cat_payload["points"]

        x, y, z = pos
        point_list.append({
            "name": asset,
            "uaid": uaid,
            "x": x,
            "y": y,
            "z": z,
        })
        counts[target_cat] += 1
        if target_sub is not None:
            sub_counts.setdefault(target_cat, Counter())[target_sub] += 1
        asset_per_bucket.setdefault(composite_key(target_cat, target_sub), Counter())[asset] += 1

    # Drop empty subcategories and empty categories from the output (always keep fallback).
    out_categories: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
    for cat_key, cat_payload in bucket_meta.items():
        if "subcategories" in cat_payload:
            kept_subs: "OrderedDict[str, dict[str, Any]]" = OrderedDict()
            for sub_key, sub_payload in cat_payload["subcategories"].items():
                if sub_payload["points"]:
                    kept_subs[sub_key] = sub_payload
            if kept_subs:
                out_payload = dict(cat_payload)
                out_payload["subcategories"] = kept_subs
                out_categories[cat_key] = out_payload
        else:
            if cat_payload["points"]:
                out_categories[cat_key] = cat_payload

    meta = {
        "generatedBy": "website/tools/LocationMap/CompileLocationMapData.py",
        "input": display_path(in_path),
        "rules": display_path(rules_path),
        "counts": {
            "totalEntries": total,
            "droppedByRules": dropped,
            "skippedBadPosition": bad_position,
            "perCategory": dict(counts),
            "perSubcategory": {cat: dict(sc) for cat, sc in sub_counts.items()},
        },
        "topAssetsPerBucket": {
            bucket: cnt.most_common(15)
            for bucket, cnt in asset_per_bucket.items()
            if cnt
        },
        "topUncategorized": unknown_asset_counts.most_common(args.top_unknown),
    }

    payload = {"_meta": meta, "categories": out_categories}

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(
        json.dumps(payload, indent=INDENT, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )

    icon_count = copy_referenced_icons(referenced_icons, icon_index)
    print(f"[INFO] Synced {icon_count} icon PNGs into {_ICON_OUT_DIR}", flush=True)
    print(f"[INFO] Wrote {out_path}", flush=True)
    print(f"[INFO] {total} entries -> "
          f"{sum(counts.values())} kept ({dropped} dropped, {bad_position} bad pos)",
          flush=True)
    for cat, n in counts.most_common():
        print(f"        {n:>7}  {cat}", flush=True)
        for sub, sn in sub_counts.get(cat, Counter()).most_common():
            print(f"        {sn:>7}    `- {sub}", flush=True)
    if unknown_asset_counts:
        print(f"[INFO] {len(unknown_asset_counts)} distinct uncategorized asset classes "
              f"(top {args.top_unknown} listed in _meta.topUncategorized).", flush=True)


if __name__ == "__main__":
    main()
