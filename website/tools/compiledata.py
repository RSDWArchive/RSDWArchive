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


def resolve_json_root(repo_root: Path, config: dict) -> Path:
    explicit_json_root = config.get("datasetJsonRoot")
    if isinstance(explicit_json_root, str) and explicit_json_root.strip():
        candidate = Path(explicit_json_root.strip())
        if not candidate.is_absolute():
            candidate = (repo_root / candidate).resolve()
        return candidate

    dataset_version = config.get("datasetVersion")
    if not isinstance(dataset_version, str) or not dataset_version.strip():
        raise ValueError("Config missing required string key: datasetVersion")

    return (repo_root / dataset_version.strip() / "json").resolve()


def validate_json_root(json_root: Path) -> None:
    if not json_root.exists():
        raise FileNotFoundError(f"JSON root not found: {json_root}")
    if not (json_root / "RSDragonwilds").exists():
        raise FileNotFoundError(f"Expected RSDragonwilds under json root: {json_root}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Compile LocationData, LootData, and NPCData using website config."
    )
    parser.add_argument(
        "--config",
        default=str(DEFAULT_CONFIG_RELATIVE),
        help="Path to website data config JSON (default: website/data.config.json)",
    )
    args = parser.parse_args()

    script_path = Path(__file__).resolve()
    repo_root = script_path.parents[2]
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = (repo_root / config_path).resolve()

    if not config_path.exists():
        raise FileNotFoundError(f"Config not found: {config_path}")

    config = load_config(config_path)
    json_root = resolve_json_root(repo_root, config)
    validate_json_root(json_root)

    env = dict(os.environ)
    env["RSDW_JSON_ROOT"] = str(json_root)
    env["RSDW_LOOT_SOURCE_DIR"] = str(json_root)
    env["RSDW_NPC_SOURCE_DIR"] = str(json_root)
    env["RSDW_LOCATION_SOURCE_DIR"] = str(json_root)

    run_step(
        ["python", str(repo_root / "website" / "tools" / "LocationData" / "CompileLocationData.py")],
        repo_root,
        env,
    )
    run_step(
        ["python", str(repo_root / "website" / "tools" / "LootData" / "CompileLootData.py")],
        repo_root,
        env,
    )
    run_step(
        ["python", str(repo_root / "website" / "tools" / "NPCData" / "CompileNPCData.py")],
        repo_root,
        env,
    )

    print("[INFO] Compile data pipeline completed successfully.")
    print(f"[INFO] Config: {config_path}")
    print(f"[INFO] JSON root used: {json_root}")


if __name__ == "__main__":
    main()
