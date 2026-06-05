# Vendored GitCommitTools

This is the vendored copy of `E:\Github\GitCommitTools` used by RSDWArchive.
Prefer the project wrapper unless you are changing the generic planner itself:

```powershell
python .\tools\PlanGitCommits.py
```

The underlying tool is `git_commit_tools.py`. It inspects a target repository's
working tree, flags files over GitHub's 100 MiB file limit, and splits the
remaining changed paths into conservative commit batches under a configurable
size cap.

The default batch cap is `1.9 GiB`. This is intentionally below GitHub's rough
2 GiB push limit because Git pack size is not exactly the same as working tree
file size.

## Commands

Analyze a repo:

```powershell
python .\tools\PlanGitCommits.py analyze
```

Print a commit plan:

```powershell
python .\tools\PlanGitCommits.py
```

Write a JSON plan:

```powershell
python .\tools\PlanGitCommits.py --out .\0.11.2.2\GitCommitPlan.json
```

Use a smaller file limit for testing:

```powershell
python .\tools\PlanGitCommits.py --file-limit-mb 1
```

Dry-run commit batches:

```powershell
python .\tools\PlanGitCommits.py commit-batches
```

Actually create commits:

```powershell
python .\tools\PlanGitCommits.py commit-batches --execute --message-prefix "Update RSDWArchive 0.11.2.2"
```

Create and push each batch one at a time:

```powershell
python .\tools\PlanGitCommits.py commit-batches --execute --push-each --message-prefix "Update RSDWArchive 0.11.2.2"
```

## Safety

- `commit-batches` is a dry run unless `--execute` is provided.
- `--push-each` requires `--execute`.
- The tool refuses to commit while changed files over 100 MiB are present.
- The tool refuses to run commits if the Git index already has staged changes.
- Paths are staged with `git add -A --pathspec-from-file ...` so large batches
  do not hit Windows command-line length limits.

## What It Measures

The batch size is based on working tree file size. GitHub push size is based on
Git pack data, so this is an estimate. The default `1.9 GiB` cap leaves some
headroom.
