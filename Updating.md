# Updating Archive Data

New archive folders are generated locally with:

```powershell
python .\tools\UpdateArchiveData.py
```

The pipeline detects the installed game root, reads the full UE4SS
`ProjectVersion`, uses the shared `E:\Github\Retoc\RSDragonwilds\<version>`
cache, runs the RSDWArchive CUE4Parse extractor against `E:\Github\CUE4Parse`,
writes `<version>\json`, `<version>\textures`, and `<version>\usmap`, updates
`website\data.config.json`, runs the website compile/index stage, generates
reports comparing the previous dataset to the new full version, moves the
previous dataset folder to `E:\Github`, writes a local Git commit batch plan,
and writes `<version>\PipelineRun.json`.

Use the full detected game version as the dataset folder, for example
`0.11.2.2`.

## Full Pipeline

Run the update without automatic Git commits:

```powershell
python .\tools\UpdateArchiveData.py
```

Run the update, create Git-safe commit batches, and push each batch:

```powershell
python .\tools\UpdateArchiveData.py --git-commit-batches --git-push-each
```

## Useful Checks

Preview what the pipeline will do:

```powershell
python .\tools\UpdateArchiveData.py --dry-run
```

Run a small extractor smoke test without compiling the website:

```powershell
python .\tools\UpdateArchiveData.py --skip-retoc --extract-limit 50 --skip-website --skip-config-update
```

## Reports And Archival

Run only the report stage for two explicit versions:

```powershell
python .\tools\UpdateArchiveData.py --run-reports --skip-retoc --skip-extract --skip-config-update --skip-website --previous-version 0.11.2 --version 0.11.2.2 --skip-archive-previous
```

Keep the previous dataset inside the repo instead of moving it to `E:\Github`:

```powershell
python .\tools\UpdateArchiveData.py --skip-archive-previous
```

## Git Commit Planning

Plan safe commit batches:

```powershell
python .\tools\PlanGitCommits.py
```

Create commit batches after reviewing the plan:

```powershell
python .\tools\PlanGitCommits.py commit-batches --execute
```

Create and push each batch:

```powershell
python .\tools\PlanGitCommits.py commit-batches --execute --push-each
```

The commit-batch command is a dry run unless `--execute` is added. The pipeline
also writes `<version>\GitCommitPlan.json` at the end of full runs.
