"""
Run the RSDWArchive update pipeline for a new RuneScape: Dragonwilds game build.

Default behavior:
- Detect the installed game version from the UE4SS header dump.
- Use E:\\Github\\Retoc\\RSDragonwilds\\<version> as the shared retoc cache.
- Locate the current .usmap and copy it into that cache.
- Run retoc if the cache is not already populated.
- Run the RSDWArchive CUE4Parse extractor to produce json/, textures/, and usmap/.
- Generate <version>/.gitignore entries for files over 100 MB.
- Update website/data.config.json to the new full ProjectVersion folder.
- Run website/updatewebsite.py to compile website datasets and file-index.json.
- Generate old-vs-new reports against the previous dataset folder when one exists.
- Move the previous dataset folder out of the repo after reports complete.
- Generate a local Git commit batch plan for the finished update.
"""

from __future__ import annotations

import argparse
import filecmp
import json
import os
import re
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Sequence


GAME_NAME = "RSDragonwilds"
DEFAULT_RETOC_BASE = Path(r"E:\Github\Retoc\RSDragonwilds")
DEFAULT_CUE4PARSE_ROOT = Path(r"E:\Github\CUE4Parse")
DEFAULT_CONFIG_RELATIVE = Path("website", "data.config.json")
DEFAULT_PREVIOUS_ARCHIVE_DESTINATION = Path(r"E:\Github")
PROJECT_VERSION_RE = re.compile(r'ProjectVersion\s*=\s*TEXT\("([^"]+)"\)')
DATASET_VERSION_RE = re.compile(r"^\d+(?:\.\d+)+$")
RETOC_MANIFEST_NAME = "retoc-manifest.json"
RETOC_LOCK_NAME = ".retoc.lock"
LARGE_FILE_LIMIT_MB = 100
LARGE_FILE_LIMIT_BYTES = LARGE_FILE_LIMIT_MB * 1024 * 1024
DEFAULT_GIT_BATCH_GB = 1.9
DEFAULT_GIT_FILE_LIMIT_MB = 100.0
DEFAULT_REPORT_TIMEOUT_MINUTES = 30.0


@dataclass(frozen=True)
class RetocCacheStatus:
    state: str
    detail: str
    manifest: dict | None = None


@dataclass(frozen=True)
class CommandStage:
    name: str
    command: str
    cwd: str
    status: str
    started_utc: str | None
    finished_utc: str | None
    duration_seconds: float | None
    exit_code: int | None = None
    log_path: str | None = None
    timed_out: bool = False
    timeout_seconds: float | None = None

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "command": self.command,
            "cwd": self.cwd,
            "status": self.status,
            "started_utc": self.started_utc,
            "finished_utc": self.finished_utc,
            "duration_seconds": self.duration_seconds,
            "exit_code": self.exit_code,
            "log_path": self.log_path,
            "timed_out": self.timed_out,
            "timeout_seconds": self.timeout_seconds,
        }


def repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def utc_stamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%SZ")


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def print_section(title: str) -> None:
    print(f"\n== {title} ==")


def candidate_game_roots() -> list[Path]:
    out: list[Path] = []
    env_root = os.environ.get("RSDW_GAME_ROOT")
    if env_root:
        out.append(Path(env_root))
    out.extend(
        [
            Path(r"F:\SteamLibrary\steamapps\common\RSDragonwilds\RSDragonwilds"),
            Path(r"C:\Program Files (x86)\Steam\steamapps\common\RSDragonwilds\RSDragonwilds"),
            Path(r"C:\Program Files\Steam\steamapps\common\RSDragonwilds\RSDragonwilds"),
        ]
    )
    return out


def first_existing(paths: Iterable[Path]) -> Path | None:
    for path in paths:
        if path.exists():
            return path
    return None


def detect_game_root(explicit: Path | None) -> Path:
    if explicit:
        root = explicit.resolve()
        if not root.is_dir():
            raise SystemExit(f"Game root does not exist: {root}")
        return root

    root = first_existing(candidate_game_roots())
    if root is None:
        candidates = "\n  ".join(str(p) for p in candidate_game_roots())
        raise SystemExit(
            "Could not detect the game root. Pass --game-root or set RSDW_GAME_ROOT.\n"
            f"Tried:\n  {candidates}"
        )
    return root.resolve()


def ue4ss_root(game_root: Path) -> Path:
    return game_root / "Binaries" / "Win64" / "ue4ss"


def detect_game_version(game_root: Path, explicit: str | None) -> str:
    if explicit:
        return explicit

    version_file = (
        ue4ss_root(game_root)
        / "UHTHeaderDump"
        / "EngineSettings"
        / "Private"
        / "GeneralProjectSettings.cpp"
    )
    if not version_file.is_file():
        raise SystemExit(
            "Could not detect game version because the UE4SS header dump was not found.\n"
            f"Expected: {version_file}\n"
            "Pass --version explicitly after generating/updating the dump."
        )

    text = version_file.read_text(encoding="utf-8", errors="replace")
    match = PROJECT_VERSION_RE.search(text)
    if not match:
        raise SystemExit(
            "Could not parse ProjectVersion from UE4SS header dump.\n"
            f"File: {version_file}\n"
            "Pass --version explicitly."
        )
    return match.group(1)


def find_usmap(args: argparse.Namespace, game_root: Path, retoc_version_root: Path) -> Path:
    if args.usmap:
        path = args.usmap.resolve()
        if not path.is_file():
            raise SystemExit(f"--usmap does not exist: {path}")
        return path

    search_roots: list[tuple[str, Path]] = [("ue4ss", ue4ss_root(game_root))]
    search_roots.extend(("user", p) for p in (args.usmap_search_root or []))
    env_root = os.environ.get("RSDW_USMAP_ROOT")
    if env_root:
        search_roots.append(("env", Path(env_root)))
    search_roots.append(("retoc cache", retoc_version_root))

    candidates: list[tuple[float, int, str, Path]] = []
    seen: set[Path] = set()
    for priority, (label, root) in enumerate(search_roots):
        if not root.exists():
            continue
        for path in root.rglob("*.usmap"):
            resolved = path.resolve()
            if resolved not in seen and resolved.is_file():
                seen.add(resolved)
                candidates.append((resolved.stat().st_mtime, priority, label, resolved))

    if not candidates:
        roots = "\n  ".join(f"{label}: {path}" for label, path in search_roots)
        raise SystemExit(
            "Could not find a .usmap file. Generate one with UE4SS, then pass --usmap if needed.\n"
            f"Searched:\n  {roots}"
        )

    candidates.sort(key=lambda item: (-item[0], item[1], str(item[3]).lower()))
    _, _, label, chosen = candidates[0]
    if len(candidates) > 1:
        print(f"Found {len(candidates)} .usmap files; using newest/preferred {label} source: {chosen}")
    return chosen


def copy_usmap_to_retoc(usmap: Path, retoc_version_root: Path, dry_run: bool) -> Path:
    dest = retoc_version_root / usmap.name
    if usmap.resolve() == dest.resolve():
        return dest

    if dest.is_file() and filecmp.cmp(usmap, dest, shallow=False):
        print(f"usmap already current in retoc cache: {dest}")
        return dest

    print(f"Copy usmap: {usmap} -> {dest}")
    if not dry_run:
        retoc_version_root.mkdir(parents=True, exist_ok=True)
        shutil.copy2(usmap, dest)
    return dest


def load_json_file(path: Path) -> dict | None:
    if not path.is_file():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    return data if isinstance(data, dict) else None


def retoc_manifest_path(retoc_version_root: Path) -> Path:
    return retoc_version_root / RETOC_MANIFEST_NAME


def retoc_cache_has_package_data(retoc_version_root: Path) -> bool:
    rsdw = retoc_version_root / GAME_NAME
    engine = retoc_version_root / "Engine"
    if not (rsdw.is_dir() and engine.is_dir()):
        return False
    try:
        next(rsdw.rglob("*.uasset"))
        return True
    except StopIteration:
        return False


def retoc_cache_status(retoc_version_root: Path, version: str) -> RetocCacheStatus:
    if not retoc_version_root.exists():
        return RetocCacheStatus("missing", "cache folder does not exist")
    if not retoc_version_root.is_dir():
        return RetocCacheStatus("conflict", f"cache path exists but is not a directory: {retoc_version_root}")

    lock_path = retoc_version_root / RETOC_LOCK_NAME
    if lock_path.exists():
        return RetocCacheStatus("locked", f"retoc lock exists: {lock_path}")

    manifest = load_json_file(retoc_manifest_path(retoc_version_root))
    if manifest:
        manifest_game = manifest.get("game")
        manifest_version = manifest.get("version")
        if manifest_game and manifest_game != GAME_NAME:
            return RetocCacheStatus(
                "conflict",
                f"manifest game is {manifest_game!r}, expected {GAME_NAME!r}",
                manifest,
            )
        if manifest_version and manifest_version != version:
            return RetocCacheStatus(
                "conflict",
                f"manifest version is {manifest_version!r}, expected {version!r}",
                manifest,
            )

    if retoc_cache_has_package_data(retoc_version_root):
        return RetocCacheStatus("ready", "Engine/ and RSDragonwilds/ package data found", manifest)

    children = list(retoc_version_root.iterdir())
    allowed_partial = {RETOC_MANIFEST_NAME, "scriptobjects.bin"}
    unexpected = [
        child
        for child in children
        if child.name not in allowed_partial and child.suffix.lower() != ".usmap"
    ]
    if not unexpected:
        return RetocCacheStatus("missing", "cache folder exists but only contains metadata/usmap files", manifest)

    preview = ", ".join(child.name for child in unexpected[:5])
    if len(unexpected) > 5:
        preview += ", ..."
    return RetocCacheStatus(
        "incomplete",
        f"cache folder is not ready and contains non-metadata files: {preview}",
        manifest,
    )


def write_retoc_manifest(
    *,
    retoc_version_root: Path,
    version: str,
    game_root: Path,
    paks_root: Path,
    usmap: Path,
    retoc_command: Sequence[str],
) -> None:
    manifest = {
        "schema": "RSDWArchive.RetocCache.v1",
        "game": GAME_NAME,
        "version": version,
        "source_paks": str(paks_root),
        "game_root": str(game_root),
        "retoc_root": str(retoc_version_root),
        "usmap": str(usmap),
        "generated_at_utc": now_iso(),
        "generated_by": "RSDWArchive/tools/UpdateArchiveData.py",
        "retoc_command": command_text(retoc_command),
    }
    retoc_manifest_path(retoc_version_root).write_text(json.dumps(manifest, indent=2), encoding="utf-8")


def acquire_retoc_lock(retoc_version_root: Path) -> Path:
    retoc_version_root.mkdir(parents=True, exist_ok=True)
    lock_path = retoc_version_root / RETOC_LOCK_NAME
    try:
        fd = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
    except FileExistsError:
        raise SystemExit(
            f"Retoc cache is locked: {lock_path}\n"
            "Another pipeline may be running. If this is stale, delete the lock after verifying no retoc job is active."
        )
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        payload = {
            "created_at_utc": now_iso(),
            "pid": os.getpid(),
            "script": str(Path(__file__).resolve()),
        }
        json.dump(payload, f, indent=2)
    return lock_path


def release_retoc_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def command_text(cmd: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(c) for c in cmd])


def run_command(
    title: str,
    cmd: Sequence[str],
    *,
    cwd: Path,
    log_path: Path | None,
    dry_run: bool,
    timeout_seconds: float | None = None,
) -> CommandStage:
    print_section(title)
    cmd_text = command_text(cmd)
    print(cmd_text)
    if dry_run:
        return CommandStage(
            name=title,
            command=cmd_text,
            cwd=str(cwd),
            status="planned",
            started_utc=None,
            finished_utc=None,
            duration_seconds=None,
            log_path=str(log_path) if log_path else None,
            timeout_seconds=timeout_seconds,
        )

    assert log_path is not None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_utc = now_iso()
    started = time.monotonic()
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"# {title}\n")
        log.write(f"# cwd: {cwd}\n")
        log.write(f"# started_utc: {started_utc}\n")
        log.write(f"# timeout_seconds: {timeout_seconds}\n")
        log.write(f"$ {cmd_text}\n\n")
        log.flush()

        proc = subprocess.Popen(
            [str(c) for c in cmd],
            cwd=str(cwd),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            print(line, end="")
            log.write(line)
        try:
            rc = proc.wait(timeout=timeout_seconds)
            timed_out = False
        except subprocess.TimeoutExpired:
            proc.kill()
            rc = proc.wait()
            timed_out = True
        finished_utc = now_iso()
        duration_seconds = round(time.monotonic() - started, 3)
        log.write(f"\n# finished_utc: {finished_utc}\n")
        log.write(f"# duration_seconds: {duration_seconds}\n")
        log.write(f"# exit_code: {rc}\n")
        log.write(f"# timed_out: {timed_out}\n")
        stage = CommandStage(
            name=title,
            command=cmd_text,
            cwd=str(cwd),
            status="timeout" if timed_out else ("completed" if rc == 0 else "failed"),
            started_utc=started_utc,
            finished_utc=finished_utc,
            duration_seconds=duration_seconds,
            exit_code=rc,
            log_path=str(log_path),
            timed_out=timed_out,
            timeout_seconds=timeout_seconds,
        )
        if timed_out:
            raise SystemExit(f"{title} timed out after {timeout_seconds} seconds. Log: {log_path}")
        if rc != 0:
            raise SystemExit(f"{title} failed with exit code {rc}. Log: {log_path}")
        return stage


def run_command_to_log(
    title: str,
    cmd: Sequence[str],
    *,
    cwd: Path,
    log_path: Path | None,
    dry_run: bool,
    timeout_seconds: float | None,
) -> CommandStage:
    print_section(title)
    cmd_text = command_text(cmd)
    print(cmd_text)
    if timeout_seconds:
        print(f"Timeout: {timeout_seconds:g} seconds")
    if dry_run:
        return CommandStage(
            name=title,
            command=cmd_text,
            cwd=str(cwd),
            status="planned",
            started_utc=None,
            finished_utc=None,
            duration_seconds=None,
            log_path=str(log_path) if log_path else None,
            timeout_seconds=timeout_seconds,
        )

    assert log_path is not None
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started_utc = now_iso()
    started = time.monotonic()
    timed_out = False
    rc: int | None = None
    with log_path.open("w", encoding="utf-8", errors="replace") as log:
        log.write(f"# {title}\n")
        log.write(f"# cwd: {cwd}\n")
        log.write(f"# started_utc: {started_utc}\n")
        log.write(f"# timeout_seconds: {timeout_seconds}\n")
        log.write(f"$ {cmd_text}\n\n")
        log.flush()
        try:
            completed = subprocess.run(
                [str(c) for c in cmd],
                cwd=str(cwd),
                stdout=log,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_seconds,
                check=False,
            )
            rc = completed.returncode
        except subprocess.TimeoutExpired:
            timed_out = True

        finished_utc = now_iso()
        duration_seconds = round(time.monotonic() - started, 3)
        log.write(f"\n# finished_utc: {finished_utc}\n")
        log.write(f"# duration_seconds: {duration_seconds}\n")
        log.write(f"# exit_code: {rc}\n")
        log.write(f"# timed_out: {timed_out}\n")

    status = "timeout" if timed_out else ("completed" if rc == 0 else "failed")
    print(f"{title} {status} in {duration_seconds:g}s")
    return CommandStage(
        name=title,
        command=cmd_text,
        cwd=str(cwd),
        status=status,
        started_utc=started_utc,
        finished_utc=finished_utc,
        duration_seconds=duration_seconds,
        exit_code=rc,
        log_path=str(log_path),
        timed_out=timed_out,
        timeout_seconds=timeout_seconds,
    )


def require_tool(name: str) -> str:
    found = shutil.which(name)
    if found is None:
        raise SystemExit(f"Required tool not found on PATH: {name}")
    return found


def extension_counts(root: Path) -> dict[str, int]:
    counts: dict[str, int] = {}
    if not root.is_dir():
        return counts
    for path in root.rglob("*"):
        if path.is_file():
            suffix = path.suffix.lower() or "<none>"
            counts[suffix] = counts.get(suffix, 0) + 1
    return dict(sorted(counts.items(), key=lambda item: (-item[1], item[0])))


def version_key(version: str) -> tuple[int, ...]:
    return tuple(int(part) for part in version.split("."))


def is_dataset_folder(path: Path) -> bool:
    return path.is_dir() and DATASET_VERSION_RE.match(path.name) is not None and (path / "json").is_dir()


def detect_previous_dataset(repo: Path, version: str, output_root: Path) -> Path | None:
    candidates = [
        path.resolve()
        for path in repo.iterdir()
        if is_dataset_folder(path) and path.resolve() != output_root.resolve() and path.name != version
    ]
    if not candidates:
        return None

    current_key = version_key(version)
    older = [path for path in candidates if version_key(path.name) < current_key]
    pool = older or candidates
    return max(pool, key=lambda path: version_key(path.name))


def resolve_previous_dataset(args: argparse.Namespace, repo: Path, version: str, output_root: Path) -> Path | None:
    if not args.previous_version:
        return detect_previous_dataset(repo, version, output_root)

    previous = Path(args.previous_version)
    if not previous.is_absolute():
        previous = repo / previous
    previous = previous.resolve()
    if not is_dataset_folder(previous):
        raise SystemExit(f"Previous dataset root is missing or has no json/: {previous}")
    if previous == output_root.resolve():
        raise SystemExit(f"Previous dataset cannot be the same as output root: {previous}")
    return previous


def should_run_completion_stages(args: argparse.Namespace) -> bool:
    return (
        not args.skip_extract
        and not args.skip_website
        and args.extract_limit is None
        and not args.asset
        and not args.name
        and not args.prefix
    )


def resolve_reports_mode(args: argparse.Namespace) -> str:
    if args.skip_reports:
        return "skip"
    return args.reports_mode


def report_timeout_seconds(args: argparse.Namespace) -> float | None:
    if args.report_timeout_minutes is None or args.report_timeout_minutes <= 0:
        return None
    return args.report_timeout_minutes * 60.0


def report_required(mode: str) -> bool:
    return mode == "required"


def resolve_extract_workers(args: argparse.Namespace) -> str:
    if args.extract_workers:
        return args.extract_workers
    if args.resource_profile == "conservative":
        return "1"
    if args.resource_profile == "max":
        return "max"
    return "auto"


def reports_state(
    *,
    mode: str,
    status: str,
    reason: str,
    previous_dataset: Path | None = None,
    output_dir: Path | None = None,
    stage: CommandStage | None = None,
    report_run_json: Path | None = None,
    error: str | None = None,
) -> dict:
    required = report_required(mode)
    return {
        "mode": mode,
        "status": status,
        "skipped": status == "skipped",
        "required": required,
        "acceptable": status == "completed" or not required,
        "reason": reason,
        "previous_dataset": str(previous_dataset) if previous_dataset else None,
        "output_dir": str(output_dir) if output_dir else None,
        "report_run_json": str(report_run_json) if report_run_json else None,
        "stage": stage.to_dict() if stage else None,
        "error": error,
    }


def previous_archive_state(
    *,
    status: str,
    reason: str,
    source: Path | None = None,
    destination: Path | None = None,
    required: bool = False,
    error: str | None = None,
) -> dict:
    return {
        "status": status,
        "skipped": status == "skipped",
        "required": required,
        "acceptable": status == "completed" or not required,
        "reason": reason,
        "source": str(source) if source else None,
        "destination": str(destination) if destination else None,
        "error": error,
    }


def default_report_output_dir(repo: Path, old_version: str, new_version: str) -> Path:
    return repo / "reports" / "reports" / f"{old_version}_to_{new_version}"


def resolve_report_output_dir(args: argparse.Namespace, repo: Path, old_version: str, new_version: str) -> Path:
    path = args.report_output_dir or default_report_output_dir(repo, old_version, new_version)
    if not path.is_absolute():
        path = repo / path
    return path.resolve()


def archive_previous_dataset(previous_root: Path, destination_base: Path, dry_run: bool) -> Path:
    destination_base = destination_base.resolve()
    destination = destination_base / previous_root.name
    print_section("Archive previous dataset")
    print(f"Move {previous_root} -> {destination}")
    if destination.exists():
        raise SystemExit(
            f"Previous dataset archive destination already exists: {destination}\n"
            "Move or remove that folder before archiving the previous dataset."
        )
    if dry_run:
        return destination
    destination_base.mkdir(parents=True, exist_ok=True)
    shutil.move(str(previous_root), str(destination))
    print(f"Moved previous dataset to: {destination}")
    return destination


def load_archive_extract_summary(path: Path) -> dict:
    data = load_json_file(path)
    if not data:
        return {}
    return {
        "selected_packages": data.get("SelectedPackageCount"),
        "json_written": data.get("JsonWrittenCount"),
        "json_skipped": data.get("JsonSkippedCount"),
        "textures_written": data.get("TextureWrittenCount"),
        "textures_skipped": data.get("TextureSkippedCount"),
        "failed_packages": data.get("FailedPackageCount"),
        "requested_workers": data.get("RequestedWorkers"),
        "effective_workers": data.get("EffectiveWorkers"),
        "duration_seconds": data.get("DurationSeconds"),
        "packages_per_second": data.get("PackagesPerSecond"),
        "json_bytes_written": data.get("JsonBytesWritten"),
        "texture_bytes_written": data.get("TextureBytesWritten"),
    }


def load_git_plan_summary(path: Path) -> dict:
    data = load_json_file(path)
    if not data:
        return {}
    batches = data.get("batches") if isinstance(data.get("batches"), list) else []
    return {
        "changed_path_count": data.get("changed_path_count"),
        "allowed_path_count": data.get("allowed_path_count"),
        "blocked_path_count": data.get("blocked_path_count"),
        "batch_count": len(batches),
        "max_batch_bytes": data.get("max_batch_bytes"),
        "file_limit_bytes": data.get("file_limit_bytes"),
    }


def write_large_file_gitignore(dataset_root: Path, dry_run: bool) -> None:
    large_files: list[str] = []
    if dataset_root.is_dir():
        for path in sorted(dataset_root.rglob("*")):
            if not path.is_file() or path.name == ".gitignore":
                continue
            try:
                size = path.stat().st_size
            except OSError:
                continue
            if size > LARGE_FILE_LIMIT_BYTES:
                large_files.append(path.relative_to(dataset_root).as_posix())

    print_section("Large file ignore audit")
    print(f"Files over {LARGE_FILE_LIMIT_MB} MB: {len(large_files)}")
    if dry_run:
        return
    if not large_files:
        return

    gitignore_path = dataset_root / ".gitignore"
    existing = gitignore_path.read_text(encoding="utf-8").splitlines() if gitignore_path.exists() else []
    header = f"# Files over {LARGE_FILE_LIMIT_MB} MB"
    if header in existing:
        existing = existing[: existing.index(header)]
    while existing and not existing[-1].strip():
        existing.pop()

    lines = existing[:]
    if lines:
        lines.append("")
    lines.append(header)
    lines.extend(large_files)
    gitignore_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Wrote {gitignore_path}")


def update_website_config(config_path: Path, version: str, dry_run: bool) -> None:
    print_section("Website config")
    print(f"Set datasetVersion -> {version}")
    if dry_run:
        return
    payload = load_json_file(config_path) or {}
    payload["datasetVersion"] = version
    payload.setdefault("repoBranch", "main")
    payload.pop("datasetJsonRoot", None)
    payload.pop("datasetTexturesRoot", None)
    config_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def write_pipeline_summary(
    *,
    path: Path,
    args: argparse.Namespace,
    version: str,
    game_root: Path,
    retoc_version_root: Path,
    usmap: Path,
    output_root: Path,
    log_dir: Path | None,
    dry_run: bool,
    stages: list[CommandStage],
    resource_settings: dict,
    reports: dict | None = None,
    previous_dataset_archival: dict | None = None,
    git_commit_plan: dict | None = None,
) -> None:
    previous_archive = previous_dataset_archival or {"skipped": True}
    summary = {
        "schema": "RSDWArchive.UpdatePipeline.v1",
        "updated_utc": now_iso(),
        "dry_run": dry_run,
        "version": version,
        "game_root": str(game_root),
        "retoc_root": str(retoc_version_root),
        "usmap": str(usmap),
        "output_root": str(output_root),
        "log_dir": str(log_dir) if log_dir else None,
        "resource_settings": resource_settings,
        "stages": [stage.to_dict() for stage in stages],
        "website": {
            "skipped": args.skip_website,
            "config_update_skipped": args.skip_config_update,
        },
        "counts_by_extension": extension_counts(output_root),
        "archive_extract": load_archive_extract_summary(output_root / "ArchiveExtractManifest.json"),
        "reports": reports or {"skipped": True},
        "previous_dataset_archival": previous_archive,
        "previous_archive": previous_archive or {"skipped": True},
        "git_commit_plan": git_commit_plan or {"skipped": True},
    }
    path.write_text(json.dumps(summary, indent=2), encoding="utf-8")


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the retoc -> CUE4Parse -> RSDWArchive website update pipeline.",
    )
    parser.add_argument("--game-root", type=Path, default=None, help="RSDragonwilds game root.")
    parser.add_argument("--version", default=None, help="Game version folder name. Defaults to detected ProjectVersion.")
    parser.add_argument("--retoc-base", type=Path, default=DEFAULT_RETOC_BASE)
    parser.add_argument("--output-root", type=Path, default=None, help="Output data root. Defaults to <repo>/<version>.")
    parser.add_argument("--usmap", type=Path, default=None, help="Explicit .usmap path.")
    parser.add_argument(
        "--usmap-search-root",
        type=Path,
        action="append",
        default=[],
        help="Additional folder to search recursively for .usmap files. Repeatable.",
    )
    parser.add_argument("--cue4parse-root", type=Path, default=None)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG_RELATIVE)
    parser.add_argument("--dry-run", action="store_true", help="Print planned work without running commands.")
    parser.add_argument(
        "--resource-profile",
        choices=["conservative", "balanced", "max"],
        default="balanced",
        help="Default local resource posture. Controls auto extraction workers when --extract-workers is omitted.",
    )

    parser.add_argument("--skip-retoc", action="store_true")
    parser.add_argument("--force-retoc", action="store_true", help="Run retoc even if the cache looks populated.")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--force-extract", action="store_true", help="Re-export existing JSON/textures.")

    parser.add_argument("--extract-limit", type=int, default=None, help="Limit CUE extraction for smoke tests.")
    parser.add_argument(
        "--extract-workers",
        default=None,
        help="CUE extractor workers: integer, auto, or max. Defaults from --resource-profile.",
    )
    parser.add_argument(
        "--extract-mode",
        choices=["full", "json-only", "textures-only", "missing-only"],
        default="full",
        help="CUE extraction scope. Default full preserves archive parity.",
    )
    parser.add_argument("--asset", action="append", default=[], help="Exact package path for CUE extraction. Repeatable.")
    parser.add_argument("--name", action="append", default=[], help="Exact asset name for CUE extraction. Repeatable.")
    parser.add_argument("--prefix", default=None, help="Comma-separated CUE extraction filename prefixes.")

    parser.add_argument("--skip-config-update", action="store_true", help="Do not update website/data.config.json.")
    parser.add_argument("--skip-website", action="store_true", help="Skip website/updatewebsite.py.")
    parser.add_argument("--skip-compile-data", action="store_true", help="Pass through to website/updatewebsite.py.")
    parser.add_argument("--skip-file-index", action="store_true", help="Pass through to website/updatewebsite.py.")

    parser.add_argument(
        "--previous-version",
        default=None,
        help="Previous dataset version or path for reports/archive. Defaults to newest older dataset folder.",
    )
    parser.add_argument("--run-reports", action="store_true", help="Run reports even for a partial/skipped pipeline run.")
    parser.add_argument("--skip-reports", action="store_true", help="Skip old-vs-new report generation.")
    parser.add_argument(
        "--reports-mode",
        choices=["required", "best-effort", "skip"],
        default="best-effort",
        help="Report behavior. best-effort is nonblocking and records timeout/failure in PipelineRun.json.",
    )
    parser.add_argument(
        "--report-timeout-minutes",
        type=float,
        default=DEFAULT_REPORT_TIMEOUT_MINUTES,
        help="Timeout for report generation. Use 0 for no timeout.",
    )
    parser.add_argument(
        "--report-detail",
        choices=["summary", "full"],
        default="summary",
        help="summary avoids full rename-detecting diffs; full keeps the historical deep diff/changelog outputs.",
    )
    parser.add_argument("--report-output-dir", type=Path, default=None, help="Report output folder.")
    parser.add_argument(
        "--skip-archive-previous",
        action="store_true",
        help="Do not move the previous dataset out of the repo after reports complete.",
    )
    parser.add_argument(
        "--archive-previous-destination",
        type=Path,
        default=DEFAULT_PREVIOUS_ARCHIVE_DESTINATION,
        help="Destination folder for the previous dataset archive move.",
    )

    parser.add_argument("--skip-git-plan", action="store_true", help="Skip final Git commit batch planning.")
    parser.add_argument("--run-git-plan", action="store_true", help="Run Git commit planning even for a partial run.")
    parser.add_argument("--git-plan-output", type=Path, default=None, help="Git commit plan JSON output path.")
    parser.add_argument("--git-max-batch-gb", type=float, default=DEFAULT_GIT_BATCH_GB)
    parser.add_argument("--git-file-limit-mb", type=float, default=DEFAULT_GIT_FILE_LIMIT_MB)
    parser.add_argument(
        "--git-commit-batches",
        action="store_true",
        help="Create Git commits from the final batch plan. This stages and commits files.",
    )
    parser.add_argument(
        "--git-push-each",
        action="store_true",
        help="Push after each Git commit batch. Requires --git-commit-batches.",
    )

    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    root = repo_root().resolve()
    game_root = detect_game_root(args.game_root)
    version = detect_game_version(game_root, args.version)
    retoc_version_root = (args.retoc_base / version).resolve()
    output_root = (args.output_root or (root / version)).resolve()
    cue4parse_root = (
        args.cue4parse_root
        or (Path(os.environ["CUE4PARSE_ROOT"]) if os.environ.get("CUE4PARSE_ROOT") else None)
        or DEFAULT_CUE4PARSE_ROOT
    ).resolve()

    paks_root = game_root / "Content" / "Paks"
    if not paks_root.is_dir():
        raise SystemExit(f"Game Paks folder not found: {paks_root}")

    config_path = args.config
    if not config_path.is_absolute():
        config_path = (root / config_path).resolve()

    usmap_source = find_usmap(args, game_root, retoc_version_root)
    usmap = copy_usmap_to_retoc(usmap_source, retoc_version_root, args.dry_run)
    log_dir = None if args.dry_run else output_root / "PipelineLogs" / utc_stamp()
    completion_stages = should_run_completion_stages(args)
    report_stages = completion_stages or args.run_reports
    reports_mode = resolve_reports_mode(args)
    extract_workers = resolve_extract_workers(args)
    report_timeout = report_timeout_seconds(args)
    git_plan_stage = (completion_stages or args.run_git_plan or args.git_commit_batches) and not args.skip_git_plan
    stages: list[CommandStage] = []
    resource_settings = {
        "profile": args.resource_profile,
        "extract_workers_requested": args.extract_workers,
        "extract_workers_effective_request": extract_workers,
        "extract_mode": args.extract_mode,
        "reports_mode": reports_mode,
        "report_timeout_minutes": args.report_timeout_minutes,
        "report_detail": args.report_detail,
    }
    if args.git_push_each and not args.git_commit_batches:
        raise SystemExit("--git-push-each requires --git-commit-batches.")
    previous_dataset = resolve_previous_dataset(args, root, version, output_root) if (report_stages or args.previous_version) else None
    report_output_dir = (
        resolve_report_output_dir(args, root, previous_dataset.name, version) if previous_dataset is not None else None
    )
    git_plan_output = args.git_plan_output or (output_root / "GitCommitPlan.json")
    if not git_plan_output.is_absolute():
        git_plan_output = (root / git_plan_output).resolve()

    print_section("Resolved Pipeline")
    print(f"repo:       {root}")
    print(f"game:       {game_root}")
    print(f"ue4ss:      {ue4ss_root(game_root)}")
    print(f"version:    {version}")
    print(f"retoc:      {retoc_version_root}")
    print(f"usmap:      {usmap}")
    print(f"output:     {output_root}")
    print(f"cue4parse:  {cue4parse_root}")
    print(f"config:     {config_path}")
    print(f"resources:  {args.resource_profile}")
    print(f"workers:    {extract_workers}")
    if report_stages:
        print(f"previous:   {previous_dataset if previous_dataset else '<none detected>'}")
        print(f"reports:    {report_output_dir if report_output_dir else '<skipped>'} ({reports_mode})")
        if reports_mode != "skip":
            print(f"report timeout: {report_timeout if report_timeout else '<none>'}")
        print(f"archive old: {args.archive_previous_destination.resolve()}")
    print(f"git plan:   {git_plan_output if git_plan_stage else '<skipped>'}")
    if log_dir:
        print(f"logs:       {log_dir}")

    if not args.skip_retoc:
        require_tool("retoc")
    if not args.skip_extract:
        require_tool("dotnet")
        if not cue4parse_root.is_dir():
            raise SystemExit(
                f"CUE4Parse source checkout not found: {cue4parse_root}\n"
                "Clone FabianFG/CUE4Parse there or pass --cue4parse-root."
            )
    if report_stages and reports_mode != "skip" and previous_dataset is not None:
        require_tool("git")
    if git_plan_stage:
        require_tool("git")

    if not args.dry_run:
        output_root.mkdir(parents=True, exist_ok=True)

    if args.skip_retoc:
        print_section("retoc")
        print("Skipped by --skip-retoc")
        if not args.dry_run and not retoc_cache_has_package_data(retoc_version_root):
            raise SystemExit(f"--skip-retoc was set but cache is not ready: {retoc_version_root}")
    else:
        status = retoc_cache_status(retoc_version_root, version)
        print_section("retoc")
        print(f"Cache status: {status.state} ({status.detail})")
        if status.state == "ready" and not args.force_retoc:
            print(f"Skipping retoc; cache already populated: {retoc_version_root}")
        elif status.state in {"conflict", "locked"}:
            raise SystemExit(f"Refusing to run retoc: {status.detail}")
        elif status.state == "incomplete" and not args.force_retoc:
            raise SystemExit(
                "Refusing to run retoc into an incomplete non-empty cache.\n"
                f"{status.detail}\n"
                f"Inspect or clean this folder first: {retoc_version_root}\n"
                "Use --force-retoc only if you intentionally want retoc to write into it."
            )
        else:
            retoc_cmd = ["retoc", "to-legacy", str(paks_root), str(retoc_version_root)]
            lock_path: Path | None = None
            try:
                if not args.dry_run:
                    lock_path = acquire_retoc_lock(retoc_version_root)
                stages.append(
                    run_command(
                        "retoc to-legacy",
                        retoc_cmd,
                        cwd=root,
                        log_path=log_dir / "01_retoc.log" if log_dir else None,
                        dry_run=args.dry_run,
                    )
                )
                if not args.dry_run:
                    write_retoc_manifest(
                        retoc_version_root=retoc_version_root,
                        version=version,
                        game_root=game_root,
                        paks_root=paks_root,
                        usmap=usmap,
                        retoc_command=retoc_cmd,
                    )
            finally:
                if lock_path is not None:
                    release_retoc_lock(lock_path)

    if args.skip_extract:
        print_section("CUE4Parse archive extract")
        print("Skipped by --skip-extract")
    else:
        cue_project = root / "tools" / "CueExtract" / "RsdwArchiveExtract" / "RsdwArchiveExtract.csproj"
        cmd: list[str] = [
            "dotnet",
            "run",
            "--project",
            str(cue_project),
            f"/p:Cue4ParseRoot={cue4parse_root}",
            "--",
            "--retoc-root",
            str(retoc_version_root),
            "--usmap",
            str(usmap),
            "--out",
            str(output_root),
            "--manifest",
            str(output_root / "ArchiveExtractManifest.json"),
            "--workers",
            extract_workers,
            "--extract-mode",
            args.extract_mode,
        ]
        for asset in args.asset:
            cmd.extend(["--asset", asset])
        for name in args.name:
            cmd.extend(["--name", name])
        if args.prefix:
            cmd.extend(["--prefix", args.prefix])
        if args.extract_limit is not None:
            cmd.extend(["--limit", str(args.extract_limit)])
        elif not args.asset and not args.name:
            cmd.append("--all")
        if args.force_extract:
            cmd.append("--force")

        stages.append(
            run_command(
                "CUE4Parse archive extract",
                cmd,
                cwd=root,
                log_path=log_dir / "02_archive_extract.log" if log_dir else None,
                dry_run=args.dry_run,
            )
        )

    write_large_file_gitignore(output_root, args.dry_run)

    if args.skip_config_update:
        print_section("Website config")
        print("Skipped by --skip-config-update")
    else:
        update_website_config(config_path, version, args.dry_run)

    if args.skip_website:
        print_section("Website update")
        print("Skipped by --skip-website")
    else:
        website_cmd: list[str] = [
            sys.executable,
            str(root / "website" / "updatewebsite.py"),
            "--config",
            str(config_path),
        ]
        if args.skip_compile_data:
            website_cmd.append("--skip-compile-data")
        if args.skip_file_index:
            website_cmd.append("--skip-file-index")
        stages.append(
            run_command(
                "Website update",
                website_cmd,
                cwd=root,
                log_path=log_dir / "03_website_update.log" if log_dir else None,
                dry_run=args.dry_run,
            )
        )

    reports_summary: dict | None = None
    previous_archive_summary: dict | None = None
    if report_stages:
        if previous_dataset is None:
            print_section("Archive reports")
            print("Skipped; no previous dataset folder was detected.")
            reports_summary = reports_state(
                mode=reports_mode,
                status="skipped",
                reason="no previous dataset detected",
            )
            previous_archive_summary = previous_archive_state(
                status="skipped",
                reason="no previous dataset detected",
            )
        elif reports_mode == "skip":
            print_section("Archive reports")
            print("Skipped by report mode.")
            reports_summary = reports_state(
                mode=reports_mode,
                status="skipped",
                reason="reports mode is skip",
                previous_dataset=previous_dataset,
            )
            print_section("Archive previous dataset")
            print("Deferred because report generation was skipped.")
            previous_archive_summary = previous_archive_state(
                status="deferred",
                reason="reports skipped",
                source=previous_dataset,
            )
        else:
            assert report_output_dir is not None
            reports_cmd = [
                sys.executable,
                str(root / "reports" / "generate_reports.py"),
                "--old-root",
                str(previous_dataset),
                "--new-root",
                str(output_root),
                "--old-version",
                previous_dataset.name,
                "--new-version",
                version,
                "--out-dir",
                str(report_output_dir),
                "--detail",
                args.report_detail,
            ]
            report_stage = run_command_to_log(
                "Archive reports",
                reports_cmd,
                cwd=root,
                log_path=log_dir / "04_archive_reports.log" if log_dir else None,
                dry_run=args.dry_run,
                timeout_seconds=report_timeout,
            )
            stages.append(report_stage)
            report_run_json = report_output_dir / "ReportRun.json"
            if report_stage.status in {"completed", "planned"}:
                reports_summary = reports_state(
                    mode=reports_mode,
                    status=report_stage.status,
                    reason=report_stage.status,
                    previous_dataset=previous_dataset,
                    output_dir=report_output_dir,
                    stage=report_stage,
                    report_run_json=report_run_json,
                )
            else:
                reason = "report generation timed out" if report_stage.status == "timeout" else "report generation failed"
                reports_summary = reports_state(
                    mode=reports_mode,
                    status=report_stage.status,
                    reason=reason,
                    previous_dataset=previous_dataset,
                    output_dir=report_output_dir,
                    stage=report_stage,
                    report_run_json=report_run_json if report_run_json.exists() else None,
                    error=f"Archive reports {report_stage.status}",
                )
                if report_required(reports_mode):
                    raise SystemExit(f"Archive reports {report_stage.status}. Log: {report_stage.log_path}")

            if reports_summary["status"] in {"completed", "planned"}:
                if reports_summary["status"] == "planned":
                    print_section("Archive previous dataset")
                    print("Planned after reports complete.")
                    previous_archive_summary = previous_archive_state(
                        status="planned",
                        reason="dry run",
                        source=previous_dataset,
                        destination=args.archive_previous_destination.resolve() / previous_dataset.name,
                    )
                elif args.skip_archive_previous:
                    print_section("Archive previous dataset")
                    print("Skipped by --skip-archive-previous")
                    previous_archive_summary = previous_archive_state(
                        status="skipped",
                        reason="--skip-archive-previous",
                        source=previous_dataset,
                    )
                else:
                    try:
                        moved_to = archive_previous_dataset(
                            previous_dataset,
                            args.archive_previous_destination,
                            args.dry_run,
                        )
                        previous_archive_summary = previous_archive_state(
                            status="completed" if not args.dry_run else "planned",
                            reason="completed" if not args.dry_run else "dry run",
                            source=previous_dataset,
                            destination=moved_to,
                        )
                    except SystemExit as exc:
                        if report_required(reports_mode):
                            raise
                        print(f"Previous dataset archival failed but is nonblocking in {reports_mode} mode: {exc}")
                        previous_archive_summary = previous_archive_state(
                            status="failed",
                            reason="nonblocking archival failure",
                            source=previous_dataset,
                            required=False,
                            error=str(exc),
                        )
            else:
                print_section("Archive previous dataset")
                print("Deferred because reports did not complete.")
                previous_archive_summary = previous_archive_state(
                    status="deferred",
                    reason="reports did not complete",
                    source=previous_dataset,
                )
    else:
        print_section("Archive reports")
        print("Skipped for partial/smoke pipeline run.")
        reports_summary = reports_state(
            mode=reports_mode,
            status="skipped",
            reason="partial pipeline run",
        )
        previous_archive_summary = previous_archive_state(
            status="skipped",
            reason="partial pipeline run",
        )

    git_commit_plan_summary: dict | None = None
    if git_plan_stage:
        git_mode = "commit-batches" if args.git_commit_batches else "plan"
        git_cmd = [
            sys.executable,
            str(root / "tools" / "PlanGitCommits.py"),
            git_mode,
            "--repo",
            str(root),
            "--out",
            str(git_plan_output),
            "--max-batch-gb",
            str(args.git_max_batch_gb),
            "--file-limit-mb",
            str(args.git_file_limit_mb),
            "--message-prefix",
            f"Update RSDWArchive {version}",
        ]
        if args.git_commit_batches:
            git_cmd.append("--execute")
        if args.git_push_each:
            git_cmd.append("--push-each")

        stages.append(
            run_command(
                "Git commit plan" if not args.git_commit_batches else "Git commit batches",
                git_cmd,
                cwd=root,
                log_path=log_dir / "05_git_commit_plan.log" if log_dir else None,
                dry_run=args.dry_run,
            )
        )
        git_commit_plan_summary = {
            "skipped": False,
            "mode": git_mode,
            "plan": str(git_plan_output),
            "commit_batches": args.git_commit_batches,
            "push_each": args.git_push_each,
            **({} if args.dry_run else load_git_plan_summary(git_plan_output)),
        }
    else:
        print_section("Git commit plan")
        print("Skipped by --skip-git-plan or partial/smoke pipeline run.")
        git_commit_plan_summary = {
            "skipped": True,
            "reason": "--skip-git-plan" if args.skip_git_plan else "partial pipeline run",
        }

    if args.dry_run:
        print_section("Dry Run Complete")
        print("No files were written and no commands were executed.")
    else:
        summary_path = output_root / "PipelineRun.json"
        write_pipeline_summary(
            path=summary_path,
            args=args,
            version=version,
            game_root=game_root,
            retoc_version_root=retoc_version_root,
            usmap=usmap,
            output_root=output_root,
            log_dir=log_dir,
            dry_run=False,
            stages=stages,
            resource_settings=resource_settings,
            reports=reports_summary,
            previous_dataset_archival=previous_archive_summary,
            git_commit_plan=git_commit_plan_summary,
        )
        print_section("Summary")
        print(f"Wrote {summary_path}")
        counts = extension_counts(output_root)
        print("File counts:")
        for ext, count in counts.items():
            print(f"  {ext}: {count}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
