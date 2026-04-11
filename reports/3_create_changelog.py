import os
import re
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
BASE_DIR = SCRIPT_DIR / "reports"
INPUT_FILE = BASE_DIR / "json_full_diff_report.txt"
OUTPUT_DIR = BASE_DIR / "changelog"
INDEX_FILE = "index.txt"


def clean_path(path: str) -> str:
    path = path.strip().strip('"')
    path = path.replace("\\", "/")
    return path


def short_path(path: str) -> str:
    """
    Trim long absolute paths down to the useful part after /json/
    """
    path = clean_path(path)
    marker = "/json/"
    idx = path.lower().find(marker)
    if idx != -1:
        return path[idx + len(marker):]
    return path


def safe_filename(name: str, max_len: int = 120) -> str:
    name = re.sub(r'[<>:"/\\|?*]+', "_", name)
    name = re.sub(r"_+", "_", name).strip("._ ")
    if len(name) > max_len:
        name = name[:max_len].rstrip("._ ")
    return name or "unnamed"


def split_diff_blocks(text: str):
    """
    Split on lines starting with 'diff --git '
    """
    pattern = re.compile(r'(?=^diff --git )', re.MULTILINE)
    return [b.strip() for b in pattern.split(text) if b.strip()]


def parse_diff_git_line(line: str):
    """
    Handles both:
      diff --git "a/path" "b/path"
      diff --git a/path b/path
    Returns (old_path, new_path)
    """
    # Quoted form
    m = re.match(r'^diff --git\s+"a/(.*?)"\s+"b/(.*?)"$', line)
    if m:
        return clean_path(m.group(1)), clean_path(m.group(2))

    # Unquoted form
    m = re.match(r'^diff --git\s+a/(.*?)\s+b/(.*?)$', line)
    if m:
        return clean_path(m.group(1)), clean_path(m.group(2))

    return "", ""


def parse_block(block: str):
    lines = block.splitlines()

    info = {
        "raw": block,
        "old_path": "",
        "new_path": "",
        "display_name": "",
        "is_rename": False,
        "similarity": None,
        "added_lines": 0,
        "removed_lines": 0,
        "has_hunks": False,
        "change_type": "Modified",
    }

    if lines:
        old_path, new_path = parse_diff_git_line(lines[0])
        info["old_path"] = old_path
        info["new_path"] = new_path

    for line in lines:
        if line.startswith("similarity index "):
            m = re.search(r"(\d+)%", line)
            if m:
                info["similarity"] = int(m.group(1))

        elif line.startswith("rename from "):
            info["is_rename"] = True
            path = line[len("rename from "):].strip()
            info["old_path"] = clean_path(path)

        elif line.startswith("rename to "):
            info["is_rename"] = True
            path = line[len("rename to "):].strip()
            info["new_path"] = clean_path(path)

        elif line.startswith("@@ "):
            info["has_hunks"] = True

    for line in lines:
        if line.startswith("+++ ") or line.startswith("--- "):
            continue
        if line.startswith("+"):
            info["added_lines"] += 1
        elif line.startswith("-"):
            info["removed_lines"] += 1

    base_source = info["new_path"] or info["old_path"] or "unknown"
    info["display_name"] = os.path.basename(base_source)

    if info["is_rename"] and info["has_hunks"]:
        info["change_type"] = "Renamed + Modified"
    elif info["is_rename"]:
        info["change_type"] = "Renamed"
    else:
        info["change_type"] = "Modified"

    return info


def write_block_file(out_dir: Path, idx: int, info: dict):
    stem = Path(info["display_name"]).stem or f"change_{idx:04d}"
    filename = f"{idx:04d}_{safe_filename(stem)}.txt"
    out_path = out_dir / filename

    with out_path.open("w", encoding="utf-8") as f:
        f.write(f"Change #{idx:04d}\n")
        f.write(f"Type: {info['change_type']}\n")
        if info["similarity"] is not None:
            f.write(f"Similarity: {info['similarity']}%\n")
        f.write(f"Old Path: {short_path(info['old_path'])}\n")
        f.write(f"New Path: {short_path(info['new_path'])}\n")
        f.write(f"Added Lines: {info['added_lines']}\n")
        f.write(f"Removed Lines: {info['removed_lines']}\n")
        f.write("\n")
        f.write("=" * 80 + "\n")
        f.write(info["raw"])
        f.write("\n")

    return filename


def main():
    if not INPUT_FILE.exists():
        raise FileNotFoundError(f"Could not find {INPUT_FILE}")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    text = INPUT_FILE.read_text(encoding="utf-8", errors="ignore")
    blocks = split_diff_blocks(text)
    parsed = [parse_block(block) for block in blocks]

    index_lines = []
    index_lines.append("JSON FULL DIFF - HUMANIZED INDEX")
    index_lines.append("")
    index_lines.append(f"Total change blocks: {len(parsed)}")
    index_lines.append("")

    renamed_only = 0
    renamed_modified = 0
    modified_only = 0

    for i, info in enumerate(parsed, start=1):
        if info["change_type"] == "Renamed":
            renamed_only += 1
        elif info["change_type"] == "Renamed + Modified":
            renamed_modified += 1
        elif info["change_type"] == "Modified":
            modified_only += 1

        filename = write_block_file(OUTPUT_DIR, i, info)

        index_lines.append(f"[{i:04d}] {filename}")
        index_lines.append(f"  Type: {info['change_type']}")
        if info["similarity"] is not None:
            index_lines.append(f"  Similarity: {info['similarity']}%")
        index_lines.append(f"  Old: {short_path(info['old_path'])}")
        index_lines.append(f"  New: {short_path(info['new_path'])}")
        index_lines.append(f"  +{info['added_lines']} / -{info['removed_lines']}")
        index_lines.append("")

    summary_lines = [
        "SUMMARY",
        f"Modified only: {modified_only}",
        f"Renamed only: {renamed_only}",
        f"Renamed + Modified: {renamed_modified}",
        "",
    ]

    index_path = OUTPUT_DIR / INDEX_FILE
    with index_path.open("w", encoding="utf-8") as f:
        f.write("\n".join(summary_lines + index_lines))

    print(f"Done. Wrote {len(parsed)} split files to: {OUTPUT_DIR}")
    print(f"Index file: {index_path}")


if __name__ == "__main__":
    main()