import argparse
import json
from pathlib import Path

import pywikibot


def load_pages(path: Path) -> list[dict]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    pages = raw.get("pages", [])
    if not isinstance(pages, list):
        raise ValueError("Input JSON must contain a 'pages' array.")
    return pages


def publish_pages(pages: list[dict], family: str, lang: str, dry_run: bool, max_pages: int, skip_login: bool):
    site = None
    if not dry_run:
        site = pywikibot.Site(lang, family)
        if not skip_login:
            site.login()

    posted = 0
    for item in pages:
        title = str(item.get("title", "")).strip()
        text = str(item.get("text", ""))
        summary = str(item.get("summary", "Bot: update page"))

        if not title:
            continue
        if max_pages > 0 and posted >= max_pages:
            break

        if dry_run:
            preview = text[:240].replace("\n", "\\n")
            print(f"[DRY-RUN] {title} :: {preview}...")
            posted += 1
            continue

        assert site is not None
        page = pywikibot.Page(site, title)
        page.text = text
        page.save(summary=summary, minor=False)
        posted += 1
        print(f"[OK] Saved: {title}")

    print(f"[INFO] Processed pages: {posted}")


def main():
    parser = argparse.ArgumentParser(description="Publish prepared pages JSON to a MediaWiki site using Pywikibot.")
    parser.add_argument("--pages", required=True, help="Path to pages JSON file")
    parser.add_argument("--family", default="rsdwwikidev", help="Pywikibot family name")
    parser.add_argument("--lang", default="en", help="Wiki language code")
    parser.add_argument("--dry-run", action="store_true", help="Print pages without saving")
    parser.add_argument("--max-pages", type=int, default=0, help="Limit pages processed (0 = all)")
    parser.add_argument("--skip-login", action="store_true", help="Skip explicit login call before publishing")
    args = parser.parse_args()

    pages_path = Path(args.pages)
    pages = load_pages(pages_path)
    publish_pages(
        pages=pages,
        family=args.family,
        lang=args.lang,
        dry_run=args.dry_run,
        max_pages=args.max_pages,
        skip_login=args.skip_login,
    )


if __name__ == "__main__":
    main()
