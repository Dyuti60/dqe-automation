# Selenium Introduction

## Overview

This assignment uses Selenium 4 and Google Chrome to validate and extract data from a local Plotly HTML report. The automation:

- opens `report.html` through a managed Chrome WebDriver;
- extracts the Plotly table into `table.csv`;
- captures the initial doughnut chart state;
- progressively deselects each legend category;
- writes one CSV and screenshot for every chart state; and
- validates rendered data before creating any output.

## Prerequisites

- Python 3.10 or newer
- Google Chrome
- Docker Desktop with the lab Jenkins container running
- Git Bash for the commands shown below

ChromeDriver does not need to be downloaded manually. Selenium Manager resolves a compatible driver when `webdriver.Chrome()` starts.

## Folder Structure

```text
Selenium Introduction/
|-- main.py
|-- requirements.txt
|-- report.html
|-- table.csv
|-- doughnut0.csv
|-- doughnut1.csv
|-- doughnut2.csv
|-- doughnut3.csv
|-- screenshots/
|   |-- screenshot0.png
|   |-- screenshot1.png
|   |-- screenshot2.png
|   `-- screenshot3.png
`-- README.md
```

The CSV files and screenshots are regenerated on each successful run.

## Copy the Jenkins Report

Run the `data_dev` Jenkins pipeline first so that `/generated_report/report.html` exists in the `jenkins` container. From the repository root in Git Bash, copy it with:

```bash
docker cp jenkins:/generated_report/report.html "Selenium Introduction/report.html"
```

Git Bash may convert `/generated_report/...` into a Windows path before Docker receives it. If that happens, disable MSYS path conversion for this command:

```bash
MSYS_NO_PATHCONV=1 docker cp jenkins:/generated_report/report.html "Selenium Introduction/report.html"
```

Confirm that the copied file is the generated Plotly report and not the original placeholder before running the automation.

## Environment Setup

From the repository root in Git Bash:

```bash
python -m venv "Selenium Introduction/.venv"
source "Selenium Introduction/.venv/Scripts/activate"
python -m pip install --upgrade pip
python -m pip install -r "Selenium Introduction/requirements.txt"
```

The only project dependency is Selenium 4.

## Run the Automation

Run the normal headed Chrome workflow from the repository root:

```bash
python "Selenium Introduction/main.py"
```

For a headless execution, invoke the existing `main()` parameter:

```bash
python -c "import importlib.util; from pathlib import Path; p=Path('Selenium Introduction/main.py'); s=importlib.util.spec_from_file_location('selenium_intro', p); m=importlib.util.module_from_spec(s); s.loader.exec_module(m); m.main(headless=True)"
```

The script resolves `report.html` relative to `main.py`, so it is independent of the current working directory.

## Implementation

### WebDriver Lifecycle

`SeleniumWebDriverContextManager` configures Chrome for headed or headless use, returns the initialized driver from `__enter__()`, and always calls `quit()` from `__exit__()`. Exceptions are logged and are not suppressed.

### Plotly Table Extraction

The automation waits for the Plotly document and table to render, then locates the table, columns, headers, and cells using multiple Selenium locator strategies. Plotly stores table values by column, so the extracted columns are ordered by their SVG positions and transposed into rows. Header names, column counts, row counts, duplicate header extraction, and the underlying Plotly model length are validated before `table.csv` is written.

### Doughnut Chart Interaction

The initial legend order is retained. The script exports the unfiltered chart as state 0, then reacquires the legend before every click and cumulatively deselects each category. Every transition is checked against Plotly's hidden-label state and the visual legend opacity. Active categories and values are read from the report rather than hardcoded.

Each state creates matching outputs:

| State | Hidden categories | CSV | Screenshot |
|---|---|---|---|
| 0 | None | `doughnut0.csv` | `screenshot0.png` |
| 1 | Hospital | `doughnut1.csv` | `screenshot1.png` |
| 2 | Hospital, Clinic | `doughnut2.csv` | `screenshot2.png` |
| 3 | Hospital, Clinic, Specialty Center | `doughnut3.csv` | `screenshot3.png` |

The final CSV contains only its header because no category remains active.

## Outputs

- `table.csv`: table headers plus all rendered report rows.
- `doughnut0.csv` through `doughnut3.csv`: active chart data after each state transition.
- `screenshots/screenshot0.png` through `screenshot3.png`: the complete Plotly figure, including the chart and legend.

## Error Handling and Edge Cases

The script reports missing reports, browser startup failures, timeouts, missing or stale Plotly elements, intercepted clicks, malformed tables, inconsistent column lengths, incomplete virtualized content, mismatched chart state, invalid values, and output failures. It also supports Plotly charts that omit some slice labels visually by reconciling active categories with the read-only Plotly trace model. The all-categories-deselected state is exported safely as a header-only CSV.

## Verified Execution

The completed headless run produced:

- 19 table data rows with headers `Facility Type`, `Visit Date`, and `Average Time Spent`;
- legend categories `Hospital`, `Clinic`, and `Specialty Center`;
- doughnut CSV data-row counts of 3, 2, 1, and 0; and
- four valid, nonempty PNG screenshots showing the progressive filter states.

Python syntax validation and `git diff --check` also passed.

## Known Limitations

- Selectors depend on Plotly's current generated DOM classes and should be reviewed after a major Plotly upgrade.
- Selenium Manager may require internet access the first time it resolves ChromeDriver.
- Plotly may display its built-in legend interaction hint briefly in filtered screenshots; this does not change the chart data or filter state.
