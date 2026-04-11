import os

# =========================================================
# CONFIG
# All input/output lives in a "reports" folder next to this script
# =========================================================
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
BASE_DIR = os.path.join(SCRIPT_DIR, "reports")
os.makedirs(BASE_DIR, exist_ok=True)

JSON_REPORT = os.path.join(BASE_DIR, "json_name_status_report.txt")
TEXTURES_REPORT = os.path.join(BASE_DIR, "textures_name_status_report.txt")
OUTPUT_REPORT = os.path.join(BASE_DIR, "clean_diff_report.txt")

OLD_VERSION = "0.11.0.3"
NEW_VERSION = "0.11.0.8"


def clean_path(path: str) -> str:
    """
    Remove quotes and normalize slashes for readability.
    """
    path = path.strip().strip('"')
    path = path.replace("\\", "/")
    return path


def make_relative_label(path: str, kind: str) -> str:
    """
    Trim the long absolute path down to something cleaner.
    Example:
    E:/Github/RSDWArchive/0.11.0.8/json/RSDragonwilds/... -> RSDragonwilds/...
    """
    path = clean_path(path)

    marker = f"/{kind}/"
    idx = path.lower().find(marker.lower())
    if idx != -1:
        return path[idx + len(marker):]

    return path


def parse_name_status_report(filepath: str, kind: str):
    """
    Parse git diff --name-status style output.

    Handles:
    A    "path"
    D    "path"
    M    "path"
    R100 "old_path" "new_path"

    Returns:
    {
        "added": [],
        "deleted": [],
        "modified": [],
        "renamed": [(score, old_path, new_path)],
    }
    """
    results = {
        "added": [],
        "deleted": [],
        "modified": [],
        "renamed": [],
    }

    if not os.path.exists(filepath):
        raise FileNotFoundError(f"Missing file: {filepath}")

    with open(filepath, "r", encoding="utf-8", errors="ignore") as f:
        for raw_line in f:
            line = raw_line.strip()
            if not line:
                continue

            parts = line.split("\t")
            status = parts[0].strip()

            if status == "A" and len(parts) >= 2:
                results["added"].append(make_relative_label(parts[1], kind))

            elif status == "D" and len(parts) >= 2:
                results["deleted"].append(make_relative_label(parts[1], kind))

            elif status == "M" and len(parts) >= 2:
                results["modified"].append(make_relative_label(parts[1], kind))

            elif status.startswith("R") and len(parts) >= 3:
                score = status[1:] if len(status) > 1 else "?"
                old_path = make_relative_label(parts[1], kind)
                new_path = make_relative_label(parts[2], kind)
                results["renamed"].append((score, old_path, new_path))

    results["added"].sort(key=str.lower)
    results["deleted"].sort(key=str.lower)
    results["modified"].sort(key=str.lower)
    results["renamed"].sort(key=lambda x: (x[1].lower(), x[2].lower()))

    return results


def write_section(out, title: str, items: list[str]):
    out.write(f"{title} ({len(items)}):\n")
    if not items:
        out.write("  None\n\n")
        return

    for item in items:
        out.write(f"  - {item}\n")
    out.write("\n")


def write_renamed_section(out, renamed_items):
    out.write(f"Renamed ({len(renamed_items)}):\n")
    if not renamed_items:
        out.write("  None\n\n")
        return

    for score, old_path, new_path in renamed_items:
        out.write(f"  - [{score}%] {old_path} -> {new_path}\n")
    out.write("\n")


def write_summary_block(out, label: str, parsed: dict):
    out.write("==================================================\n")
    out.write(f"{label}\n")
    out.write("==================================================\n\n")

    write_section(out, "Added", parsed["added"])
    write_section(out, "Modified", parsed["modified"])
    write_section(out, "Removed", parsed["deleted"])
    write_renamed_section(out, parsed["renamed"])


def main():
    json_data = parse_name_status_report(JSON_REPORT, "json")
    texture_data = parse_name_status_report(TEXTURES_REPORT, "textures")

    with open(OUTPUT_REPORT, "w", encoding="utf-8") as out:
        out.write(f"From {OLD_VERSION} to {NEW_VERSION}\n\n")
        out.write("This report groups files into easier-to-read sections.\n")
        out.write("Rename entries are shown separately so they do not get mixed in with added/removed files.\n\n")

        write_summary_block(out, "JSON", json_data)
        write_summary_block(out, "TEXTURES", texture_data)

        out.write("==================================================\n")
        out.write("TOTALS\n")
        out.write("==================================================\n\n")

        out.write(
            f"JSON: Added={len(json_data['added'])}, "
            f"Modified={len(json_data['modified'])}, "
            f"Removed={len(json_data['deleted'])}, "
            f"Renamed={len(json_data['renamed'])}\n"
        )

        out.write(
            f"TEXTURES: Added={len(texture_data['added'])}, "
            f"Modified={len(texture_data['modified'])}, "
            f"Removed={len(texture_data['deleted'])}, "
            f"Renamed={len(texture_data['renamed'])}\n"
        )

    print(f"Done. Wrote report to: {OUTPUT_REPORT}")


if __name__ == "__main__":
    main()