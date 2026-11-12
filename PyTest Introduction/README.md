# Pytest CSV Validation Assignment

This directory contains Pytest tests for `src/data/data.csv`, session-scoped fixtures, a collection hook that marks tests without explicit marks as `unmarked`, registered custom markers, and HTML report configuration.

## Setup

Open Git Bash, navigate to project directory and run these commands:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install -r requirements.txt
```

The dependencies include `pytest-reportportal`, but ReportPortal remains disabled unless the `--reportportal` option is supplied.

## Required test commands

Run all tests. The default setting in `pytest.ini` writes the report to `reports/all-tests/report.html`.

```bash
python -m pytest
```

Run only tests dynamically marked as `unmarked` and write a separate report.

```bash
python -m pytest -m unmarked \
  -o "addopts=--html=reports/unmarked/report.html"
```

Run tests marked `validate_csv`, excluding the expected-failure test, and write a separate report.

```bash
python -m pytest -m "validate_csv and not xfail" \
  -o "addopts=--html=reports/validate-csv-not-xfail/report.html"
```

The `-o addopts=...` option gives each filtered run its own report path instead of overwriting the default all-tests report.

## Optional ReportPortal execution

`pytest.ini` contains the ReportPortal endpoint, launch name, log level, and a project placeholder. Replace `REPLACE_WITH_ACTUAL_PROJECT` with the assigned ReportPortal project before attempting an upload. Do not store authentication credentials in this repository.

In PowerShell, capture the API key without displaying it and expose it only to the current process environment:

```powershell
$secureKey = Read-Host "ReportPortal API key" -AsSecureString
$env:RP_API_KEY = [System.Net.NetworkCredential]::new("", $secureKey).Password
```

After the project value is configured, start an explicitly enabled ReportPortal run:

```powershell
python -m pytest --reportportal
```

Normal local execution remains independent of ReportPortal:

```powershell
python -m pytest
```

Remove the process-scoped credential after use:

```powershell
Remove-Item Env:RP_API_KEY
Remove-Variable secureKey
```

When finished, leave the virtual environment with:

```bash
deactivate
```

## Verified results

The current CSV intentionally exposes data-quality findings, so some commands return a nonzero exit code.

| Run | Result |
| --- | --- |
| All tests | 3 passed, 3 failed, 1 skipped, 1 xfailed |
| `unmarked` | 1 passed, 1 failed, 6 deselected |
| `validate_csv and not xfail` | 1 passed, 1 failed, 1 skipped, 5 deselected |

The failures accurately identify the current file contents:

- CSV row 7 contains the invalid email `invalid_email.com`.
- The row with `id=2` contains `is_active=False`, while the assignment expects `True`.
- The duplicate row for `id=4` is reported as an expected failure through `xfail`.

The age test is skipped intentionally, as required by the assignment. The source CSV was not changed to force the tests to pass.
