---
name: generate-parquet-dq-tests
description: >-
  Creates one standardized PyTest source-to-target DQ module from an authoritative
  Parquet dataset mapping. Invoke it for dataset test generation only; refuse
  framework, Jenkins, connector, conftest, or transformation implementation work.
---

# Generate Parquet DQ tests

Generate a mapping-driven PyTest module for the existing PyTest DQ Framework.
Before acting, read:

- `PyTest DQ Framework/docs/test-automation-strategy.md`, especially sections 5 and 6
- `PyTest DQ Framework/docs/dq-framework-design.md`
- `docs/parquet-aggregated-data-mapping.md`

The detailed data mapping is authoritative if it conflicts with a strategy summary,
sample, existing test, or observed Parquet output.

## When this skill applies

Use this skill only when asked to generate or review a dataset-level Parquet DQ test
module from a documented mapping. The Step 1 framework must already provide the
`db_connection`, `parquet_reader`, and `data_quality_library` fixtures and register
the required markers.

The only generated artifact is:

`PyTest DQ Framework/tests/dq checks/parquet_files/test_<dataset_name>.py`

Generate one dataset per module. Do not edit framework libraries, connectors,
`conftest.py`, `pytest.ini`, requirements, Jenkinsfiles, mappings, `data_dev`, or
transformation code unless the user separately and explicitly authorizes that work.
If a required marker is not registered, report it as a blocker rather than silently
editing framework configuration.

Refuse or stop the generation when:

- the requested work is framework, CI, connector, fixture, or ETL implementation work;
- the expected source is not PostgreSQL or the actual target is not Parquet;
- the request requires copying or reconciling expected SQL with `data_dev`, loader
  code, production transformation SQL, or observed target data;
- the authoritative mapping is absent or lacks information needed to determine the
  output columns, business-key grain, measures, joins, transformations, or filters.

When mapping information is incomplete, identify the exact ambiguity and request a
mapping clarification. Never invent a join, filter, expression, or transformation.

## Inputs you must have

Collect or confirm all of the following before writing a module:

1. Dataset name, matching the folder under `/parquet_data/`.
2. The authoritative mapping from `docs/parquet-aggregated-data-mapping.md`, including:
   - mapped output columns and their aliases;
   - PostgreSQL source tables and source columns;
   - join path and join keys;
   - business-key grain/dimensions;
   - measure expressions and required precision or rounding;
   - mapping-defined transformations and optional filters;
   - partition information and whether partition fields are business or technical.
3. Author name for the module header.
4. Requirement or ticket reference for the module header.

Do not use `data_dev/`, loader implementations, production transformation SQL,
existing Parquet values, or an existing generated test as a substitute for missing
mapping information.

## Hard rules

1. Source/expected is the PostgreSQL query result from `db_connection`.
2. Target/actual is the Parquet DataFrame from `parquet_reader`.
3. Derive expected SQL independently and only from the authoritative mapping.
4. Never copy SQL or behavioral details from `data_dev`, a loader, or production ETL.
5. Do not add a `UNION`, `WHERE`, `CASE`, sign change, cast, join, or other behavior
   unless the mapping requires it.
6. Alias every selected source expression to its mapped Parquet output column. The
   expected result must contain the mapped business columns and no implementation-only
   columns.
7. Use `/parquet_data/<dataset_name>` and
   `parquet_reader.process(target_path, include_subfolders=True)`.
8. Do not drop partition columns in the generated module. The reader/framework may
   identify technical partition columns for comparison, but every mapped business
   column—including a mapped partition column—must remain present and be compared.
9. Call existing `DataQualityLibrary` methods. Do not implement pandas comparisons,
   counts, null checks, or duplicate logic in the test module.
10. Generate all five mandatory tests: smoke/non-empty, full completeness, count,
    business-key uniqueness, and not-null.
11. Pass the complete mapping-defined business-key grain explicitly to
    `check_duplicates`; do not default to full-row uniqueness.
12. Pass every required mapped output column to `check_not_null_values`.
13. Mark every test with `parquet_data` and the dataset-specific marker. Add `smoke`
    only to the non-empty test.
14. Never compare the target to itself, use empty assertions, catch assertion failures,
    weaken expected SQL, add tolerances, or otherwise make a check trivially pass.
15. Do not embed concrete expected SQL for any named production dataset in this skill.

## Workflow

1. Read the requested dataset entry in the detailed mapping. Record its output
   columns, source fields, grain, measures, joins, filters, and partitions.
2. Check that the dataset name, author, requirement reference, join path, and every
   SQL-defining mapping detail are available. Stop and report any ambiguity.
3. Derive the expected PostgreSQL query from the mapping using the generic SQL rules
   below. Do not inspect the ETL or target data to shape the query.
4. Confirm that selected expressions are aliased to the mapped output names and that
   the `GROUP BY` grain is exactly the mapping-defined business key.
5. Create one module at the required path using the template below. Replace every
   placeholder, including the business-key and not-null column lists.
6. Verify fixture direction: completeness and count must call the library with
   `source_data` first and `target_data` second.
7. Verify marker registration without changing `pytest.ini`. Report a missing marker.
8. Run the post-generation review. Execute PyTest only when the user asks for it.

## Template

```python
"""
Description: Data Quality checks for <dataset_name> dataset.
Requirement(s): <requirement_reference>
Author(s): <author_name>
"""

import pytest


@pytest.fixture(scope='module')
def source_data(db_connection):
    source_query = """
    -- expected query derived only from the authoritative mapping
    """
    return db_connection.get_data_sql(source_query)


@pytest.fixture(scope='module')
def target_data(parquet_reader):
    target_path = '/parquet_data/<dataset_name>'
    return parquet_reader.process(target_path, include_subfolders=True)


@pytest.mark.parquet_data
@pytest.mark.smoke
@pytest.mark.<dataset_name>
def test_check_dataset_is_not_empty(target_data, data_quality_library):
    data_quality_library.check_dataset_is_not_empty(target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_data_completeness(source_data, target_data, data_quality_library):
    data_quality_library.check_data_completeness(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_count(source_data, target_data, data_quality_library):
    data_quality_library.check_count(source_data, target_data)


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_uniqueness(target_data, data_quality_library):
    data_quality_library.check_duplicates(
        target_data,
        ['<business_key_1>', '<business_key_2>'],
    )


@pytest.mark.parquet_data
@pytest.mark.<dataset_name>
def test_check_not_null_values(target_data, data_quality_library):
    data_quality_library.check_not_null_values(
        target_data,
        ['<mapped_output_1>', '<mapped_output_2>', '<mapped_output_3>'],
    )
```

Adjust the number of business-key and mapped-output placeholders to the mapping. Do
not add local comparison logic to the template.

## SQL derivation (generic)

Build the query from business intent in this order:

1. Map every target output to its PostgreSQL source expression.
2. Add only the source tables and join relationships explicitly defined by the
   mapping. Use the mapped keys and join type; do not infer missing relationships.
3. Express each dimension exactly as mapped. Apply a date extraction, concatenation,
   formatting rule, or other transformation only when the mapping defines it.
4. Express each measure using the mapped aggregate and precision rule. A rounding
   instruction belongs in expected SQL; arbitrary rounding or tolerance does not.
5. Apply only mapping-defined filters.
6. Group by the complete mapped business-key grain when aggregates are present.
7. Alias every output expression to the exact mapped target column name and return
   only those mapped output columns.
8. Review the query against the detailed mapping, not the strategy summary, ETL SQL,
   an existing test, or a preview of Parquet data.

If any required expression, join, filter, or precision rule is ambiguous, stop and
report the ambiguity instead of choosing a plausible implementation.

## After generation

Review the generated module before considering it complete:

- Confirm the file and dataset names match and only one dataset is covered.
- Confirm header author and requirement values are populated.
- Confirm expected SQL is traceable line-by-line to the detailed mapping.
- Confirm PostgreSQL is expected/source and Parquet is actual/target.
- Confirm recursive Parquet reading and the canonical `/parquet_data/` path.
- Confirm all five tests use the existing library methods.
- Confirm uniqueness receives the full business-key grain explicitly.
- Confirm not-null receives every required mapped output column.
- Confirm all markers are present and registered, with `smoke` only on non-empty.
- Confirm no business column is dropped as a technical partition field.
- Confirm there are no empty assertions, target-to-target comparisons, swallowed
  failures, or implementation-derived expectations.

If test execution is requested, run the focused module with the documented database
configuration and HTML reporting as appropriate. Treat mismatches as mapping-versus-
Parquet evidence. Do not rewrite expected SQL merely to make a failing run green.

---

## Skill review (self-check before Step 3)

- [x] No unfinished scaffold marker remains in this skill.
- [x] No concrete expected SQL for a named production dataset is embedded.
- [x] No instruction permits expected SQL to come from `data_dev` or loader code.
- [x] Smoke, completeness, count, business-key uniqueness, and not-null are mandatory.
- [x] PostgreSQL is source/expected and Parquet is target/actual.
- [x] The template uses real `DataQualityLibrary` assertions and forbids trivial passes.
- [x] The module skeleton, fixtures, paths, and markers match the test strategy.
- [x] Missing mapping details cause an ambiguity report, not an invented transformation.
- [x] Technical partition handling preserves mapped business columns.
- [x] The instructions are dataset-independent and reusable for additional mappings.
