import argparse
import json
import subprocess
from pathlib import Path


DEFAULT_CONFIG_RELATIVE = Path("website", "data.config.json")
DEFAULT_INDEX_OUTPUT_RELATIVE = Path("website", "file-index.json")


def run_step(command: list[str], cwd: Path) -> None:
    printable = " ".join(command)
    print(f"[RUN] {printable}")
    subprocess.run(command, cwd=str(cwd), check=True)


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


def build_file_index(repo_root: Path, dataset_root: Path, out_path: Path) -> None:
    files = []
    for path in sorted(dataset_root.rglob("*")):
        if not path.is_file():
            continue
        rel = path.relative_to(repo_root).as_posix()
        files.append(f"../{rel}")

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps({"files": files}, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {len(files)} indexed files to: {out_path}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Master website update pipeline using website/data.config.json"
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_RELATIVE),
        help="Path to website data config JSON (default: website/data.config.json)",
    )
    parser.add_argument(
        "--skip-compile-data",
        action="store_true",
        help="Skip running website/tools/compiledata.py",
    )
    parser.add_argument(
        "--skip-file-index",
        action="store_true",
        help="Skip rebuilding website/file-index.json",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parent.parent

    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()
    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = load_config(config_path)
    dataset_root = resolve_dataset_root(repo_root, config)
    json_root = dataset_root / "json"
    if not json_root.exists() or not (json_root / "RSDragonwilds").exists():
        raise FileNotFoundError(f"Invalid dataset root/json root from config: {dataset_root}")

    if not args.skip_compile_data:
        run_step(
            [
                "python",
                str(repo_root / "website" / "tools" / "compiledata.py"),
                "--config",
                str(config_path),
            ],
            repo_root,
        )

    if not args.skip_file_index:
        index_out_path = (repo_root / DEFAULT_INDEX_OUTPUT_RELATIVE).resolve()
        build_file_index(repo_root, dataset_root, index_out_path)

    print("[INFO] Website update pipeline completed successfully.")
    print(f"[INFO] Config: {config_path}")
    print(f"[INFO] Dataset root used: {dataset_root}")


if __name__ == "__main__":
    main()
