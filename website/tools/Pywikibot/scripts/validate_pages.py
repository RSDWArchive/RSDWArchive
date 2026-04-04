import argparse
import json
from pathlib import Path


def load_pages(path: Path) -> list[dict]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    pages = payload.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("Input JSON must contain a 'pages' array.")
    return pages


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate generated wiki pages for common formatting issues.")
    parser.add_argument("--pages", required=True, help="Path to pages JSON")
    args = parser.parse_args()

    pages = load_pages(Path(args.pages))
    issues: list[str] = []

    for page in pages:
        title = str(page.get("title", "<unknown>"))
        text = str(page.get("text", ""))

        if "==Stats==\n*" in text:
            issues.append(f"{title}: Stats section contains bullet list; expected infobox template.")
        if "|skill = \n" in text:
            issues.append(f"{title}: Recipe has empty skill parameter.")
        if "{{Journal entry|" in text and "}}" not in text.split("{{Journal entry|", 1)[1]:
            issues.append(f"{title}: Journal template may be unclosed.")

    if issues:
        print(f"[ERROR] Validation failed with {len(issues)} issue(s):")
        for issue in issues[:200]:
            print(f"- {issue}")
        if len(issues) > 200:
            print(f"... and {len(issues) - 200} more")
        raise SystemExit(1)

    print(f"[INFO] Validation passed for {len(pages)} pages.")


if __name__ == "__main__":
    main()
