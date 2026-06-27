from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Sequence


SCRIPT_DIR = Path(__file__).resolve().parent
REPO_ROOT = SCRIPT_DIR.parent
DEFAULT_OUTPUT_ROOT = SCRIPT_DIR / "reports"
RAW_REPORTS = [
    "json_name_status_report.txt",
    "json_numstat_report.txt",
    "json_full_diff_report.txt",
    "textures_name_status_report.txt",
]
DERIVED_REPORTS = [
    "clean_diff_report.txt",
    "ReportRun.json",
]
LARGE_FILE_LIMIT_MB = 100
LARGE_FILE_LIMIT_BYTES = LARGE_FILE_LIMIT_MB * 1024 * 1024


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def command_text(cmd: Sequence[str]) -> str:
    return subprocess.list2cmdline([str(c) for c in cmd])


def version_safe_name(text: str) -> str:
    return "".join(ch if ch.isalnum() or ch in ".-_" else "_" for ch in text).strip("._") or "unknown"


def default_output_dir(old_version: str, new_version: str) -> Path:
    return DEFAULT_OUTPUT_ROOT / f"{version_safe_name(old_version)}_to_{version_safe_name(new_version)}"


def clean_output_dir(output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    for name in RAW_REPORTS + DERIVED_REPORTS:
        path = output_dir / name
        if path.exists():
            path.unlink()
    changelog = output_dir / "changelog"
    if changelog.exists():
        shutil.rmtree(changelog)


def write_large_file_gitignore(output_dir: Path) -> list[str]:
    large_files: list[str] = []
    for path in sorted(output_dir.rglob("*")):
        if not path.is_file() or path.name == ".gitignore":
            continue
        try:
            size = path.stat().st_size
        except OSError:
            continue
        if size > LARGE_FILE_LIMIT_BYTES:
            large_files.append(path.relative_to(output_dir).as_posix())

    gitignore_path = output_dir / ".gitignore"
    if not large_files:
        if gitignore_path.exists():
            gitignore_path.unlink()
        return []

    lines = [f"# Files over {LARGE_FILE_LIMIT_MB} MB", *large_files]
    gitignore_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {gitignore_path}")
    return large_files


def require_dataset_root(path: Path, label: str) -> None:
    if not path.is_dir():
        raise SystemExit(f"{label} dataset root does not exist: {path}")
    for child in ("json", "textures"):
        child_path = path / child
        if not child_path.is_dir():
            raise SystemExit(f"{label} dataset is missing {child}/: {child_path}")


def run_git_diff(cmd: Sequence[str], output_path: Path) -> int:
    print(f"[RUN] {command_text(cmd)} > {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8", errors="replace") as out:
        proc = subprocess.run(
            [str(c) for c in cmd],
            cwd=str(REPO_ROOT),
            stdout=out,
            stderr=subprocess.PIPE,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    if proc.stderr:
        print(proc.stderr, end="", file=sys.stderr)
    if proc.returncode not in (0, 1):
        raise SystemExit(f"git diff failed with exit code {proc.returncode}: {command_text(cmd)}")
    return proc.returncode


def run_python(cmd: Sequence[str]) -> None:
    print(f"[RUN] {command_text(cmd)}")
    proc = subprocess.run([str(c) for c in cmd], cwd=str(REPO_ROOT))
    if proc.returncode != 0:
        raise SystemExit(f"report processor failed with exit code {proc.returncode}: {command_text(cmd)}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate RSDWArchive old-vs-new dataset reports.")
    parser.add_argument("--old-root", type=Path, required=True, help="Previous dataset root.")
    parser.add_argument("--new-root", type=Path, required=True, help="Current dataset root.")
    parser.add_argument("--old-version", required=True)
    parser.add_argument("--new-version", required=True)
    parser.add_argument("--out-dir", type=Path, default=None)
    parser.add_argument(
        "--detail",
        choices=["summary", "full"],
        default="summary",
        help="summary skips full JSON diff/changelog; full keeps the historical deep report output.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    old_root = args.old_root.resolve()
    new_root = args.new_root.resolve()
    out_dir = (args.out_dir or default_output_dir(args.old_version, args.new_version)).resolve()

    require_dataset_root(old_root, "Old")
    require_dataset_root(new_root, "New")
    if old_root == new_root:
        raise SystemExit(f"Old and new dataset roots are the same: {old_root}")

    print("== Archive reports ==")
    print(f"old:    {old_root}")
    print(f"new:    {new_root}")
    print(f"output: {out_dir}")
    print(f"detail: {args.detail}")

    clean_output_dir(out_dir)

    outputs = {
        "json_name_status": out_dir / "json_name_status_report.txt",
        "json_numstat": out_dir / "json_numstat_report.txt",
        "textures_name_status": out_dir / "textures_name_status_report.txt",
    }
    if args.detail == "full":
        outputs["json_full_diff"] = out_dir / "json_full_diff_report.txt"

    rename_args = ["-M"] if args.detail == "full" else ["--no-renames"]

    exit_codes = {
        "json_name_status": run_git_diff(
            ["git", "diff", "--no-index", *rename_args, "--name-status", old_root / "json", new_root / "json"],
            outputs["json_name_status"],
        ),
        "json_numstat": run_git_diff(
            ["git", "diff", "--no-index", *rename_args, "--numstat", old_root / "json", new_root / "json"],
            outputs["json_numstat"],
        ),
        "textures_name_status": run_git_diff(
            ["git", "diff", "--no-index", *rename_args, "--name-status", old_root / "textures", new_root / "textures"],
            outputs["textures_name_status"],
        ),
    }
    if args.detail == "full":
        exit_codes["json_full_diff"] = run_git_diff(
            ["git", "diff", "--no-index", *rename_args, old_root / "json", new_root / "json"],
            outputs["json_full_diff"],
        )

    run_python(
        [
            sys.executable,
            SCRIPT_DIR / "2_create_reports.py",
            "--base-dir",
            out_dir,
            "--old-version",
            args.old_version,
            "--new-version",
            args.new_version,
        ]
    )
    changelog_index: str | None = None
    if args.detail == "full":
        run_python([sys.executable, SCRIPT_DIR / "3_create_changelog.py", "--base-dir", out_dir, "--clean"])
        changelog_index = str(out_dir / "changelog" / "index.txt")

    large_ignored_files = write_large_file_gitignore(out_dir)

    report_run = {
        "schema": "RSDWArchive.Reports.v1",
        "generated_at_utc": now_iso(),
        "old_version": args.old_version,
        "new_version": args.new_version,
        "old_root": str(old_root),
        "new_root": str(new_root),
        "output_dir": str(out_dir),
        "detail": args.detail,
        "git_diff_exit_codes": exit_codes,
        "files": {key: str(path) for key, path in outputs.items()},
        "clean_report": str(out_dir / "clean_diff_report.txt"),
        "changelog_index": changelog_index,
        "large_ignored_files": large_ignored_files,
    }
    (out_dir / "ReportRun.json").write_text(json.dumps(report_run, indent=2) + "\n", encoding="utf-8")
    print(f"[INFO] Wrote {out_dir / 'ReportRun.json'}")
    print("[INFO] Archive reports completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
