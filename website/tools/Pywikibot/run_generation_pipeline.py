import argparse
import json
import os
import subprocess
from pathlib import Path


DEFAULT_CONFIG_RELATIVE = Path("website", "data.config.json")


def run_step(command: list[str], cwd: Path, env: dict[str, str]) -> None:
    printable = " ".join(command)
    print(f"[RUN] {printable}")
    subprocess.run(command, cwd=str(cwd), env=env, check=True)


def load_config(config_path: Path) -> dict:
    payload = json.loads(config_path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"Config must be a JSON object: {config_path}")
    return payload


def resolve_dataset_root(repo_root: Path, config: dict) -> Path:
    explicit_json_root = config.get("datasetJsonRoot")
    if isinstance(explicit_json_root, str) and explicit_json_root.strip():
        json_root = Path(explicit_json_root.strip())
        if not json_root.is_absolute():
            json_root = (repo_root / json_root).resolve()
        return json_root.parent

    dataset_version = config.get("datasetVersion")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("Config missing required string key: datasetVersion")

    return (repo_root / dataset_version.strip()).resolve()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run full wiki-data pipeline: loot compile -> item catalog -> page generation"
    )
    parser.add_argument(
        "--dataset-root",
        help="Path to dataset version root, e.g. E:/Github/RSDWArchive/0.12.0.0",
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_RELATIVE),
        help="Path to website data config JSON (default: website/data.config.json)",
    )
    parser.add_argument(
        "--categories",
        default="all",
        help='Comma-separated categories for generate_item_pages.py, or "all"',
    )
    parser.add_argument(
        "--limit-per-category",
        type=int,
        default=0,
        help="Optional cap per category for page generation (0=all)",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip validate_pages.py step after page generation",
    )
    parser.add_argument(
        "--skip-text-export",
        action="store_true",
        help="Skip exporting generated pages JSON files to .txt folders",
    )
    parser.add_argument(
        "--item-title-prefix",
        default="User:RSDWArchive/",
        help='Title prefix root for generated item pages, e.g. "User:RSDWArchive/"',
    )
    parser.add_argument(
        "--npc-title-prefix",
        default="User:RSDWArchive/Loot/Enemy/",
        help='Title prefix for generated npc pages, e.g. "User:RSDWArchive/Loot/Enemy/"',
    )
    parser.add_argument(
        "--sandbox-index-title",
        default="User:RSDWArchive",
        help='Title for generated sandbox index page, e.g. "User:RSDWArchive"',
    )
    args = parser.parse_args()

    pywikibot_dir = Path(__file__).resolve().parent
    repo_root = pywikibot_dir.parents[2]
    version_root: Path
    if args.dataset_root:
        version_root = Path(args.dataset_root).resolve()
    else:
        config_path = Path(args.config)
        if not config_path.is_absolute():
            config_path = (repo_root / config_path).resolve()
        if not config_path.exists():
            raise FileNotFoundError(
                f"Config not found: {config_path}. "
                "Pass --dataset-root or provide a valid --config path."
            )
        config = load_config(config_path)
        version_root = resolve_dataset_root(repo_root, config)

    json_root = version_root / "json"
    if not json_root.exists():
        raise FileNotFoundError(f"Expected json root not found: {json_root}")
    if not (json_root / "RSDragonwilds").exists():
        raise FileNotFoundError(f"Expected RSDragonwilds folder not found under: {json_root}")

    scripts_dir = pywikibot_dir / "scripts"
    pages_dir = pywikibot_dir / "pages"
    generated_lootdata_path = pages_dir / "LootData.generated.json"
    generated_npcdata_path = pages_dir / "NPCData.generated.json"
    generated_lootdata_path.parent.mkdir(parents=True, exist_ok=True)

    env = dict(os.environ)
    # Shared root hint for scripts that consume either json root or version root.
    env["RSDW_JSON_ROOT"] = str(json_root)
    env["RSDW_LOOT_SOURCE_DIR"] = str(json_root)
    env["RSDW_NPC_SOURCE_DIR"] = str(json_root)

    run_step(
        [
            "python",
            str(repo_root / "website" / "tools" / "LootData" / "CompileLootData.py"),
            "--output",
            str(generated_lootdata_path),
        ],
        repo_root,
        env,
    )
    run_step(
        [
            "python",
            str(repo_root / "website" / "tools" / "NPCData" / "CompileNPCData.py"),
            "--output",
            str(generated_npcdata_path),
        ],
        repo_root,
        env,
    )
    run_step(
        ["python", str(scripts_dir / "build_item_catalog.py")],
        repo_root,
        env,
    )

    generate_cmd = [
        "python",
        str(scripts_dir / "generate_item_pages.py"),
        "--categories",
        args.categories,
        "--lootdata",
        str(generated_lootdata_path),
        "--title-prefix",
        args.item_title_prefix,
    ]
    if args.limit_per_category > 0:
        generate_cmd.extend(["--limit-per-category", str(args.limit_per_category)])
    run_step(generate_cmd, repo_root, env)

    npc_pages_output = pages_dir / "pages.npcs.json"
    run_step(
        [
            "python",
            str(scripts_dir / "generate_loot_enemy_pages.py"),
            "--loot-json",
            str(generated_lootdata_path),
            "--npc-json",
            str(generated_npcdata_path),
            "--output",
            str(npc_pages_output),
            "--title-prefix",
            args.npc_title_prefix,
        ],
        repo_root,
        env,
    )
    sandbox_index_output = pages_dir / "pages.sandbox-index.json"
    run_step(
        [
            "python",
            str(scripts_dir / "generate_sandbox_index_page.py"),
            "--items-pages",
            str(pages_dir / "pages.items.json"),
            "--npcs-pages",
            str(npc_pages_output),
            "--output",
            str(sandbox_index_output),
            "--title",
            args.sandbox_index_title,
        ],
        repo_root,
        env,
    )

    if not args.skip_validate:
        run_step(
            [
                "python",
                str(scripts_dir / "validate_pages.py"),
                "--pages",
                str(pages_dir / "pages.items.json"),
            ],
            repo_root,
            env,
        )

    if not args.skip_text_export:
        page_json_outputs = [
            pages_dir / "pages.items.json",
            npc_pages_output,
            sandbox_index_output,
        ]
        for pages_json in page_json_outputs:
            if not pages_json.exists():
                continue
            out_dir = pages_dir / f"{pages_json.stem}.txt"
            run_step(
                [
                    "python",
                    str(scripts_dir / "export_pages_text.py"),
                    "--pages",
                    str(pages_json),
                    "--out-dir",
                    str(out_dir),
                    "--combined",
                    "--clean",
                ],
                repo_root,
                env,
            )

    print("[INFO] Pipeline completed successfully.")
    print(f"[INFO] Dataset root: {version_root}")
    print(f"[INFO] JSON root used: {json_root}")


if __name__ == "__main__":
    main()
