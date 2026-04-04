import argparse
import json
import re
from pathlib import Path


def safe_filename(title: str) -> str:
    cleaned = re.sub(r'[<>:"/\\|?*]+', "_", title)
    cleaned = cleaned.strip().replace(" ", "_")
    return cleaned or "untitled"


def main() -> None:
    parser = argparse.ArgumentParser(description="Export pages JSON to plain text files for manual copy/paste testing.")
    parser.add_argument("--pages", required=True, help="Path to pages JSON (format: {\"pages\":[...]})")
    parser.add_argument("--out-dir", required=True, help="Output directory for .txt files")
    parser.add_argument("--combined", action="store_true", help="Also write one combined preview file")
    parser.add_argument("--clean", action="store_true", help="Delete existing .txt files in output directory before export")
    args = parser.parse_args()

    pages_path = Path(args.pages)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    if args.clean:
        for existing in out_dir.glob("*.txt"):
            existing.unlink()

    payload = json.loads(pages_path.read_text(encoding="utf-8"))
    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("Input JSON must contain a 'pages' array.")

    combined_chunks = []
    count = 0
    for page in pages:
        title = str(page.get("title", "")).strip()
        text = str(page.get("text", ""))
        if not title:
            continue

        filename = f"{safe_filename(title)}.txt"
        target = out_dir / filename
        target.write_text(text, encoding="utf-8")
        count += 1

        if args.combined:
            combined_chunks.append(f"===== {title} =====\n{text}\n")

    if args.combined:
        (out_dir / "_combined_preview.txt").write_text("\n".join(combined_chunks), encoding="utf-8")

    print(f"[INFO] Exported {count} page text files to: {out_dir}")


if __name__ == "__main__":
    main()
