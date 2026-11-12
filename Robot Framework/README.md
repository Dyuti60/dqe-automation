# Robot Framework Data Comparison

This project uses Robot Framework and SeleniumLibrary to extract a Plotly SVG table, then uses Pandas and PyArrow to compare it exactly with its partitioned Parquet source data.

## Prerequisites

- Python 3.10 or newer
- Google Chrome
- The generated Plotly `report.html`
- The partitioned Parquet dataset

Selenium Manager resolves a compatible ChromeDriver when the test runs.

## Dependencies

Dependencies are declared in `requirements.txt`: Robot Framework, SeleniumLibrary, Selenium, Pandas, PyArrow, and pytest.

## Inputs

- Report: `../Selenium Introduction/report.html`
- Parquet dataset: `D:\parquet_data\facility_type_avg_time_spent_per_visit_date`
- Report table type: Plotly-generated SVG, not an HTML `<table>`

The Robot variables and defaults are:

| Variable | Default |
|---|---|
| `REPORT_FILE` | `../Selenium Introduction/report.html` |
| `PARQUET_FOLDER` | `D:/parquet_data/facility_type_avg_time_spent_per_visit_date` |
| `FILTER_DATE` | Empty; compare the report's default seven-day window |

Override variables from the command line when required:

```bash
robot --outputdir ./results \
  --variable "REPORT_FILE:/path/to/report.html" \
  --variable "PARQUET_FOLDER:D:/path/to/parquet" \
  --variable "FILTER_DATE:2026-10-11" \
  test.robot
```

Local Parquet copies and generated test outputs are intentionally ignored by Git.

## Setup

From the `Robot Framework/` directory:

```bash
python -m venv .venv
source .venv/Scripts/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

## Run Tests

Run unit tests:

```bash
python -m pytest test_helper.py -q
```

Run the browser comparison:

```bash
robot --outputdir ./results test.robot
```

Robot Framework reports and logs will be written to `results/`.

## Expected Results

With the supplied default inputs, the test passes with exactly 19 rows and three columns for `2026-10-05` through `2026-10-11`. With `FILTER_DATE=2026-10-11`, both sources produce two matching rows. The default run creates:

- `results/output.xml`
- `results/log.html`
- `results/report.html`

`robot-framework-results.zip` is a local submission artifact containing these three files beneath a top-level `results/` directory; it is not committed.
