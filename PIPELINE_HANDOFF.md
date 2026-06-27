# RSDWArchive Pipeline Handoff

This document defines RSDWArchive as a pipeline node for a larger local
orchestration project. It is intentionally more contract-focused than
[Updating.md](Updating.md), which remains the human maintainer guide.

## Contract Summary

| Field | Value |
| --- | --- |
| Project | RSDWArchive |
| Working directory | `E:\Github\RSDWArchive` |
| Primary entrypoint | `python .\tools\UpdateArchiveData.py` |
| Dry run | `python .\tools\UpdateArchiveData.py --dry-run` |
| Full artifact build | `python .\tools\UpdateArchiveData.py` |
| MasterPipeline full build | `python .\tools\UpdateArchiveData.py --reports-mode best-effort --resource-profile max --extract-workers max` |
| Self-owned commit and push | `python .\tools\UpdateArchiveData.py --reports-mode best-effort --resource-profile max --extract-workers max --git-commit-batches --git-push-each` |
| Completion summary schema | `RSDWArchive.UpdatePipeline.v1` in `<version>\PipelineRun.json` |
| Machine contract | `pipeline.contract.json` |
| Shared Retoc cache | `E:\Github\Retoc\RSDragonwilds\<ProjectVersion>` |
| CUE4Parse checkout | `E:\Github\CUE4Parse` |

RSDWArchive owns its own Retoc/CUE4Parse extraction, website compile, report
generation, previous-dataset archival, Git commit batch planning, and optional
Git batch push.

## Inputs And Dependencies

The outer orchestrator must run this project only after these inputs are ready:

- RuneScape: Dragonwilds game install, normally detected from one of the
  configured Steam paths or `RSDW_GAME_ROOT`.
- UE4SS header dump containing `ProjectVersion`, expected at
  `<game-root>\Binaries\Win64\ue4ss\UHTHeaderDump\EngineSettings\Private\GeneralProjectSettings.cpp`
  unless `--version` is passed.
- A current `.usmap`, discovered from UE4SS, `RSDW_USMAP_ROOT`,
  `--usmap-search-root`, or the Retoc cache unless `--usmap` is passed.
- `retoc`, `dotnet`, Python, and Git on `PATH` for the default full pipeline.
- `E:\Github\CUE4Parse`, unless `--cue4parse-root` or `CUE4PARSE_ROOT` points
  to another checkout.
- A writable shared Retoc base at `E:\Github\Retoc\RSDragonwilds`.

## Stage Order

The canonical full pipeline runs these stages in order:

1. Detect game root, version, `.usmap`, Retoc cache, output folder, config, and
   CUE4Parse checkout.
2. Prepare or reuse `E:\Github\Retoc\RSDragonwilds\<version>`.
3. Run Retoc only when the shared cache is not already populated.
4. Run the RSDWArchive CUE4Parse extractor into `<version>`.
5. Generate `<version>\.gitignore` entries for files over 100 MB.
6. Update `website\data.config.json` to the new full `ProjectVersion`.
7. Run `website\updatewebsite.py` to compile website datasets and
   `website\file-index.json`.
8. Generate summary reports from the newest previous dataset to the new
   dataset. Reports default to `--reports-mode best-effort` and are
   nonblocking unless `--reports-mode required` is passed.
9. Move the previous dataset folder to `E:\Github`, unless skipped. This is
   recorded as best-effort housekeeping for normal MasterPipeline releases.
10. Generate a local Git commit batch plan, and optionally create and push those
    batches when Git flags are provided.

Successful full, resumed, partial, and smoke-test runs write the canonical
`<version>\PipelineRun.json`. Partial/skipped/nonblocking stages are recorded as
structured status fields inside that summary.

## Performance And Resume Controls

- `--resource-profile conservative|balanced|max` controls the default worker
  request when `--extract-workers` is omitted.
- `--extract-workers <n|auto|max>` is passed to the CUE4Parse extractor.
  `auto` leaves a little CPU headroom; `max` uses the processor count.
- `--extract-mode full|json-only|textures-only|missing-only` controls extractor
  scope. The default `full` keeps archive parity. `missing-only` is useful for
  resume runs because it will not rewrite existing outputs.
- `--reports-mode required|best-effort|skip` controls report gating. The default
  is `best-effort`.
- `--report-timeout-minutes <n>` bounds report generation. A timeout is
  recorded in `PipelineRun.json`; it is nonblocking in `best-effort` mode.
- `--report-detail summary|full` controls report depth. `summary` avoids the
  historical full rename-detecting diff and changelog pass; `full` keeps it.

## Shared Cache Rules

- Treat `E:\Github\Retoc\RSDragonwilds\<ProjectVersion>` as shared state across
  projects.
- Respect `.retoc.lock`; if it exists, stop and assume another pipeline may be
  using the cache.
- Accept an existing `retoc-manifest.json` only when its `game` and `version`
  match the current run.
- Skip Retoc by default when the cache already contains `Engine\` and
  `RSDragonwilds\` package data.
- Do not write Retoc output inside `E:\Github\RSDWArchive`.
- Use `--force-retoc` only for an intentional cache rebuild after manual review.

## Outputs For Downstream Projects

After a successful full run, downstream projects may consume:

- `E:\Github\RSDWArchive\<version>\json`
- `E:\Github\RSDWArchive\<version>\textures`
- `E:\Github\RSDWArchive\<version>\usmap`
- `E:\Github\RSDWArchive\<version>\ArchiveExtractManifest.json`
- `E:\Github\RSDWArchive\<version>\PipelineRun.json`
- `E:\Github\RSDWArchive\pipeline.contract.json`
- `E:\Github\RSDWArchive\website\data.config.json`
- `E:\Github\RSDWArchive\website\file-index.json`
- `E:\Github\RSDWArchive\website\tools\*.json`
- `E:\Github\RSDWArchive\reports\reports\<old>_to_<new>`

`<version>\GitCommitPlan.json` is produced when the Git planning stage runs.
If `--git-commit-batches --git-push-each` is used, RSDWArchive handles its own
batch commits and pushes.

## Success Criteria

The outer orchestrator should treat the RSDWArchive node as successful when all
of these are true:

- The command exits with code `0`.
- `<version>\PipelineRun.json` exists and has
  `schema: "RSDWArchive.UpdatePipeline.v1"`.
- `<version>\ArchiveExtractManifest.json` exists and has
  `FailedPackageCount: 0`.
- `website\data.config.json` has `datasetVersion` equal to `<version>`.
- `website\file-index.json` exists.
- `reports.status` in `PipelineRun.json` is `completed`, `skipped`, `timeout`,
  or `failed`, and `reports.acceptable` is `true`.
- `previous_dataset_archival.acceptable` is `true`.
- If Git flags were used, the Git batch stage completed successfully and pushed
  each generated batch.

## Failure Behavior

Any nonzero exit code means the outer orchestrator should stop before starting
downstream consumers. Common failures include:

- Game root cannot be detected and `--game-root` was not supplied.
- UE4SS header dump is missing or `ProjectVersion` cannot be parsed.
- No `.usmap` can be found.
- `retoc`, `dotnet`, Python, or Git is missing from `PATH`.
- `E:\Github\CUE4Parse` is missing and no alternate CUE4Parse root is supplied.
- Retoc cache is locked, conflicting, or incomplete.
- Previous dataset archive destination already exists at `E:\Github\<old>`.
- A child command fails; inspect `<version>\PipelineLogs\<timestamp>\*.log`.
- Report timeout/failure is nonblocking in `best-effort` mode, but fails the
  node in `required` mode.

## Orchestrator Defaults

Recommended orchestration flow:

1. Run `python .\tools\UpdateArchiveData.py --dry-run`.
2. If dry run succeeds and the resolved version is the intended version, run
   `python .\tools\UpdateArchiveData.py --reports-mode best-effort --resource-profile max --extract-workers max --git-commit-batches --git-push-each`.
3. Validate the success criteria above.
4. Start downstream projects that consume `E:\Github\RSDWArchive\<version>` or
   `website\tools\*.json`.

Use `python .\tools\UpdateArchiveData.py` instead of the Git command only when
the larger orchestrator intentionally wants to review, commit, or push this repo
manually.
