# Reports

Reports are now part of the root archive update pipeline. The normal command is:

```powershell
python .\tools\UpdateArchiveData.py
```

During a full update, the pipeline compares the newest previous dataset folder
against the new full-version dataset and writes reports to:

```text
reports\reports\<old>_to_<new>
```

For example, `0.11.2` to `0.11.2.2` writes:

```text
reports\reports\0.11.2_to_0.11.2.2
```

The report generator writes a `.gitignore` inside the report output folder for
files over 100 MB. The full JSON diff can be very large.

The first Retoc/CUE4Parse migration report can be noisy because the old dataset
may have been produced by the earlier exporter. Future CUE4Parse-to-CUE4Parse
reports should be more focused.

To regenerate reports from already-existing datasets without running Retoc,
CUE4Parse extraction, or the website compile:

```powershell
python .\tools\UpdateArchiveData.py --run-reports --skip-retoc --skip-extract --skip-config-update --skip-website --previous-version 0.11.2 --version 0.11.2.2 --skip-archive-previous
```

The legacy `1_generate_report_data.bat` flow is still available for ad hoc
manual reports, but it uses hard-coded paths and is not used by the main
pipeline.
