import os
from pathlib import Path

# === Settings ===
SIZE_LIMIT_MB = 100
SIZE_LIMIT_BYTES = SIZE_LIMIT_MB * 1024 * 1024


def main():
    # Folder where this script is located
    root = Path(__file__).resolve().parent
    gitignore_path = root / ".gitignore"

    large_files = []

    # Walk through all files in this folder and subfolders
    for current_root, dirs, files in os.walk(root):
        for file_name in files:
            file_path = Path(current_root) / file_name

            # Skip the .gitignore itself
            if file_path == gitignore_path:
                continue

            try:
                file_size = file_path.stat().st_size
            except Exception as e:
                print(f"Could not read file: {file_path} | Error: {e}")
                continue

            if file_size > SIZE_LIMIT_BYTES:
                relative_path = file_path.relative_to(root).as_posix()
                large_files.append((relative_path, file_size))

    if not large_files:
        print(f"No files over {SIZE_LIMIT_MB} MB were found.")
        return

    # Sort for cleaner output
    large_files.sort(key=lambda x: x[0].lower())

    # Read existing .gitignore entries if it exists
    existing_lines = set()
    if gitignore_path.exists():
        try:
            with open(gitignore_path, "r", encoding="utf-8") as f:
                existing_lines = {line.strip() for line in f if line.strip()}
        except Exception as e:
            print(f"Could not read existing .gitignore: {e}")

    new_entries = []
    for relative_path, _ in large_files:
        if relative_path not in existing_lines:
            new_entries.append(relative_path)

    # Append new entries
    if new_entries:
        with open(gitignore_path, "a", encoding="utf-8") as f:
            if gitignore_path.exists() and gitignore_path.stat().st_size > 0:
                f.write("\n")
            f.write("# Files over 100 MB\n")
            for entry in new_entries:
                f.write(entry + "\n")

    print(f"Found {len(large_files)} file(s) over {SIZE_LIMIT_MB} MB:\n")
    for relative_path, file_size in large_files:
        size_mb = file_size / (1024 * 1024)
        print(f"{relative_path}  ({size_mb:.2f} MB)")

    if new_entries:
        print(f"\nAdded {len(new_entries)} entrie(s) to: {gitignore_path}")
    else:
        print(f"\nAll large files were already listed in: {gitignore_path}")


if __name__ == "__main__":
    main()