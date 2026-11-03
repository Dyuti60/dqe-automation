"""Open the generated Plotly report in a managed Chrome session."""

from __future__ import annotations

import csv
from decimal import Decimal, InvalidOperation
import logging
from pathlib import Path
import re
from types import TracebackType

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait


LOGGER = logging.getLogger(__name__)
REPORT_LOAD_TIMEOUT_SECONDS = 20
EXPECTED_TABLE_HEADERS = (
    "Facility Type",
    "Visit Date",
    "Average Time Spent",
)
DOUGHNUT_CSV_HEADERS = ("Facility Type", "Min Average Time Spent")
TRANSLATE_Y_PATTERN = re.compile(
    r"translate\(\s*[-+]?\d*\.?\d+(?:[eE][-+]?\d+)?"
    r"(?:\s*,\s*|\s+)"
    r"([-+]?\d*\.?\d+(?:[eE][-+]?\d+)?)\s*\)"
)


class TableExtractionError(RuntimeError):
    """Raised when the rendered Plotly table cannot be extracted safely."""


class ChartAutomationError(RuntimeError):
    """Raised when doughnut-chart extraction or interaction is unreliable."""


class SeleniumWebDriverContextManager:
    """Create and reliably close a Selenium Chrome WebDriver."""

    def __init__(self, headless: bool = False) -> None:
        self.headless = headless
        self.driver: WebDriver | None = None

    def __enter__(self) -> WebDriver:
        options = webdriver.ChromeOptions()
        options.add_argument("--window-size=1440,1000")
        if self.headless:
            options.add_argument("--headless=new")
        else:
            options.add_argument("--start-maximized")

        try:
            LOGGER.info("Starting Google Chrome (headless=%s).", self.headless)
            self.driver = webdriver.Chrome(options=options)
        except WebDriverException:
            LOGGER.exception("Failed to initialize Google Chrome WebDriver.")
            raise

        return self.driver

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc_value: BaseException | None,
        traceback: TracebackType | None,
    ) -> bool:
        if exc_type is not None:
            LOGGER.error(
                "Chrome session is closing after an exception.",
                exc_info=(exc_type, exc_value, traceback),
            )

        if self.driver is not None:
            try:
                LOGGER.info("Closing Google Chrome WebDriver.")
                self.driver.quit()
            except WebDriverException:
                LOGGER.exception("Failed to close Google Chrome WebDriver cleanly.")
                raise
            finally:
                self.driver = None

        return False


def resolve_report_path() -> Path:
    """Return report.html beside this module, failing before Chrome is launched."""

    report_path = Path(__file__).resolve().with_name("report.html")
    if not report_path.is_file():
        raise FileNotFoundError(f"HTML report was not found: {report_path}")
    return report_path


def resolve_csv_path() -> Path:
    """Return the table.csv output path beside this module."""

    return Path(__file__).resolve().with_name("table.csv")


def _translate_y(element) -> float:
    """Return the y component of an SVG element's translate transform."""

    transform = element.get_attribute("transform") or ""
    if not transform:
        return 0.0

    match = TRANSLATE_Y_PATTERN.search(transform)
    if match is None:
        raise TableExtractionError(
            f"Unsupported Plotly SVG transform encountered: {transform!r}"
        )
    return float(match.group(1))


def _extract_column_values(column, column_index: int) -> list[str]:
    """Extract a Plotly table column in visual row order, excluding its header."""

    positioned_values: list[tuple[float, str]] = []
    cell_blocks = column.find_elements(
        By.CSS_SELECTOR,
        ".column-block[id^='cells']",
    )
    if not cell_blocks:
        raise TableExtractionError(
            f"No data-cell blocks were found for table column {column_index + 1}."
        )

    for block in cell_blocks:
        block_y = _translate_y(block)
        cells = block.find_elements(By.CSS_SELECTOR, ".column-cell")
        if not cells:
            raise TableExtractionError(
                f"No cells were found in a block for table column {column_index + 1}."
            )

        for cell in cells:
            try:
                cell_text = cell.find_element(By.CSS_SELECTOR, ".cell-text").text.strip()
            except NoSuchElementException as error:
                raise TableExtractionError(
                    f"A text element is missing from table column {column_index + 1}."
                ) from error

            if not cell_text:
                raise TableExtractionError(
                    f"An empty cell was found in table column {column_index + 1}."
                )
            positioned_values.append((block_y + _translate_y(cell), cell_text))

    positions = [position for position, _ in positioned_values]
    if len(positions) != len(set(positions)):
        raise TableExtractionError(
            f"Duplicate visual row positions were found in table column {column_index + 1}."
        )

    positioned_values.sort(key=lambda item: item[0])
    return [value for _, value in positioned_values]


def extract_plotly_table(
    driver: WebDriver,
    wait: WebDriverWait,
) -> tuple[list[str], list[list[str]]]:
    """Extract and validate the rendered Plotly table from the current page."""

    try:
        table = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "table"))
        )
    except TimeoutException as error:
        raise TableExtractionError("The Plotly table did not render before timeout.") from error

    columns = table.find_elements(By.CLASS_NAME, "y-column")
    if len(columns) != len(EXPECTED_TABLE_HEADERS):
        raise TableExtractionError(
            "Expected exactly three Plotly table columns, "
            f"but found {len(columns)}."
        )

    headers: list[str] = []
    column_values: list[list[str]] = []
    for column_index, column in enumerate(columns):
        try:
            header_block = column.find_element(By.ID, "header")
            header = header_block.find_element(By.CSS_SELECTOR, ".cell-text").text.strip()
        except NoSuchElementException as error:
            raise TableExtractionError(
                f"The header is missing from table column {column_index + 1}."
            ) from error

        if not header:
            raise TableExtractionError(
                f"The header is empty for table column {column_index + 1}."
            )
        headers.append(header)
        column_values.append(_extract_column_values(column, column_index))

    if tuple(headers) != EXPECTED_TABLE_HEADERS:
        raise TableExtractionError(
            f"Unexpected table headers: {headers}. "
            f"Expected: {list(EXPECTED_TABLE_HEADERS)}."
        )

    column_lengths = [len(values) for values in column_values]
    if len(set(column_lengths)) != 1:
        raise TableExtractionError(
            f"Plotly table columns contain inconsistent row counts: {column_lengths}."
        )
    if not column_lengths or column_lengths[0] == 0:
        raise TableExtractionError("The Plotly table contains no data rows.")

    # The current Plotly table is scrollable but keeps all rows in two SVG cell
    # blocks. Compare the DOM count with Plotly's trace model to detect future
    # virtualization or clipping that would otherwise omit rows silently.
    try:
        plotly_root = table.find_element(
            By.XPATH,
            "ancestor::*[contains(concat(' ', normalize-space(@class), ' '), "
            "' js-plotly-plot ')][1]",
        )
    except NoSuchElementException as error:
        raise TableExtractionError("The Plotly graph root could not be located.") from error

    model_lengths = driver.execute_script(
        """
        const tableTrace = arguments[0].data.find(trace => trace.type === 'table');
        return tableTrace ? tableTrace.cells.values.map(values => values.length) : null;
        """,
        plotly_root,
    )
    if model_lengths is None:
        raise TableExtractionError("The Plotly table trace model is unavailable.")
    if list(model_lengths) != column_lengths:
        raise TableExtractionError(
            "Rendered table rows do not match the Plotly model; scrolling or "
            f"virtualization may have omitted cells. DOM={column_lengths}, "
            f"model={model_lengths}."
        )

    if table.find_elements(By.CLASS_NAME, "scrollbar-kit"):
        LOGGER.info(
            "Plotly table is scrollable; all %d model rows are present in the DOM.",
            column_lengths[0],
        )

    rows = [list(row) for row in zip(*column_values)]
    if any(tuple(row) == EXPECTED_TABLE_HEADERS for row in rows):
        raise TableExtractionError("A table header was incorrectly extracted as a data row.")

    return headers, rows


def write_table_csv(headers: list[str], rows: list[list[str]], csv_path: Path) -> None:
    """Write validated table data to a UTF-8 CSV file."""

    with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
        writer = csv.writer(csv_file)
        writer.writerow(headers)
        writer.writerows(rows)


def _get_plotly_root(driver: WebDriver, wait: WebDriverWait):
    """Return the rendered Plotly graph container."""

    try:
        return wait.until(
            EC.visibility_of_element_located((By.CSS_SELECTOR, ".js-plotly-plot"))
        )
    except TimeoutException as error:
        raise ChartAutomationError("The Plotly graph did not render before timeout.") from error


def _get_legend_items(driver: WebDriver, wait: WebDriverWait):
    """Reacquire the chart legend and its current items."""

    try:
        scrollbox = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "scrollbox"))
        )
        items = scrollbox.find_elements(By.CLASS_NAME, "traces")
    except (NoSuchElementException, StaleElementReferenceException) as error:
        raise ChartAutomationError("The doughnut-chart legend is unavailable.") from error

    if not items:
        raise ChartAutomationError("The doughnut-chart legend contains no categories.")
    return scrollbox, items


def _legend_item_name(item) -> str:
    """Return a non-empty category name from a Plotly legend item."""

    try:
        name = item.find_element(By.CLASS_NAME, "legendtext").text.strip()
    except (NoSuchElementException, StaleElementReferenceException) as error:
        raise ChartAutomationError("A chart legend item has no readable label.") from error
    if not name:
        raise ChartAutomationError("A chart legend item has an empty category name.")
    return name


def _get_legend_categories(driver: WebDriver, wait: WebDriverWait) -> list[str]:
    """Capture the initial legend category names in displayed order."""

    _, items = _get_legend_items(driver, wait)
    categories = [_legend_item_name(item) for item in items]
    if len(categories) != len(set(categories)):
        raise ChartAutomationError(
            f"Duplicate category names were found in the legend: {categories}."
        )
    return categories


def _read_doughnut_model(driver: WebDriver, plotly_root) -> dict[str, object]:
    """Read the existing Plotly pie trace and active hidden-label state."""

    model = driver.execute_script(
        """
        const plot = arguments[0];
        const trace = plot._fullData.find(item => item.type === 'pie');
        if (!trace) {
            return null;
        }
        return {
            labels: Array.from(trace.labels, label => String(label)),
            values: Array.from(trace.values, value => Number(value)),
            hidden: Array.from(plot._fullLayout.hiddenlabels || [], label => String(label))
        };
        """,
        plotly_root,
    )
    if model is None:
        raise ChartAutomationError("The Plotly doughnut trace model is unavailable.")

    labels = model.get("labels", [])
    values = model.get("values", [])
    if len(labels) != len(values):
        raise ChartAutomationError(
            f"Doughnut trace labels and values differ in length: {len(labels)} vs "
            f"{len(values)}."
        )
    return model


def _format_chart_value(value: object) -> str:
    """Format Plotly's numeric value without adding presentation-only zeros."""

    return format(float(value), ".15g")


def _rendered_slice_values(driver: WebDriver, wait: WebDriverWait) -> dict[str, str]:
    """Read currently rendered slice labels through Selenium DOM locators."""

    try:
        pie_layer = wait.until(
            EC.presence_of_element_located((By.CLASS_NAME, "pielayer"))
        )
        slice_labels = pie_layer.find_elements(
            By.CSS_SELECTOR,
            "text.slicetext[data-notex='1']",
        )
    except (NoSuchElementException, StaleElementReferenceException) as error:
        raise ChartAutomationError("The doughnut-chart layer is unavailable.") from error

    rendered: dict[str, str] = {}
    for slice_label in slice_labels:
        try:
            parts = [
                part.text.strip()
                for part in slice_label.find_elements(By.TAG_NAME, "tspan")
                if part.text.strip()
            ]
        except StaleElementReferenceException as error:
            raise ChartAutomationError(
                "A doughnut slice changed while its label was being read."
            ) from error

        if len(parts) < 2:
            raise ChartAutomationError(
                f"A rendered slice label does not contain category and value: {parts}."
            )
        category = parts[0]
        value = "".join(parts[1:])
        if category in rendered:
            raise ChartAutomationError(
                f"The rendered chart contains a duplicate slice label: {category}."
            )
        rendered[category] = value
    return rendered


def extract_active_doughnut_data(
    driver: WebDriver,
    wait: WebDriverWait,
    plotly_root,
    legend_categories: list[str],
) -> tuple[list[list[str]], set[str]]:
    """Return active category/value rows after reconciling DOM and trace state."""

    rendered = _rendered_slice_values(driver, wait)
    model = _read_doughnut_model(driver, plotly_root)
    labels = list(model["labels"])
    values = list(model["values"])
    hidden = set(model["hidden"])

    if set(labels) != set(legend_categories):
        raise ChartAutomationError(
            "Legend categories do not match the Plotly trace labels. "
            f"legend={legend_categories}, trace={labels}."
        )
    if not hidden.issubset(set(legend_categories)):
        raise ChartAutomationError(
            f"Plotly reports unknown hidden categories: {sorted(hidden)}."
        )

    value_by_category = {
        category: _format_chart_value(value)
        for category, value in zip(labels, values)
    }
    active_categories = [
        category for category in legend_categories if category not in hidden
    ]
    rendered_categories = set(rendered)
    if not rendered_categories.issubset(set(active_categories)):
        raise ChartAutomationError(
            "Rendered labels include a deselected category: "
            f"{sorted(rendered_categories - set(active_categories))}."
        )

    for category, rendered_value in rendered.items():
        try:
            rendered_number = Decimal(rendered_value.replace(",", ""))
            model_number = Decimal(value_by_category[category])
        except (InvalidOperation, KeyError) as error:
            raise ChartAutomationError(
                f"Could not reconcile rendered value for {category}: {rendered_value!r}."
            ) from error
        if rendered_number != model_number:
            raise ChartAutomationError(
                f"Rendered value for {category} is {rendered_value}, but the Plotly "
                f"trace contains {value_by_category[category]}."
            )

    if len(rendered) < len(active_categories):
        LOGGER.info(
            "Only %d of %d active slice labels are rendered; using the read-only "
            "Plotly trace for hidden label values.",
            len(rendered),
            len(active_categories),
        )
    if not active_categories:
        if rendered:
            raise ChartAutomationError(
                "Slice labels remain rendered although every category is deselected."
            )
        LOGGER.info("All doughnut categories are deselected; chart data is empty.")

    rows = [
        [category, value_by_category[category]]
        for category in active_categories
    ]
    return rows, hidden


def write_doughnut_csv(rows: list[list[str]], csv_path: Path) -> None:
    """Write active doughnut data to a UTF-8 CSV file."""

    try:
        with csv_path.open("w", encoding="utf-8", newline="") as csv_file:
            writer = csv.writer(csv_file)
            writer.writerow(DOUGHNUT_CSV_HEADERS)
            writer.writerows(rows)
    except OSError as error:
        raise ChartAutomationError(
            f"Failed to write doughnut CSV file: {csv_path}."
        ) from error


def _capture_plotly_screenshot(plotly_root, screenshot_path: Path) -> None:
    """Capture the complete Plotly figure so the chart and legend remain visible."""

    try:
        saved = plotly_root.screenshot(str(screenshot_path))
    except WebDriverException as error:
        raise ChartAutomationError(
            f"Failed to capture screenshot: {screenshot_path}."
        ) from error
    if not saved:
        raise ChartAutomationError(
            f"Selenium did not save screenshot: {screenshot_path}."
        )


def _click_legend_category(
    driver: WebDriver,
    wait: WebDriverWait,
    plotly_root,
    category: str,
    expected_hidden: set[str],
) -> None:
    """Deselect one legend category and verify the cumulative Plotly state."""

    driver.execute_script(
        """
        const plot = arguments[0];
        plot.__seleniumAfterPlot = false;
        plot.once('plotly_afterplot', () => { plot.__seleniumAfterPlot = true; });
        """,
        plotly_root,
    )

    click_error: Exception | None = None
    for _ in range(3):
        try:
            _, items = _get_legend_items(driver, wait)
            item = next(
                (item for item in items if _legend_item_name(item) == category),
                None,
            )
            if item is None:
                raise ChartAutomationError(
                    f"Legend category disappeared before interaction: {category}."
                )
            driver.execute_script(
                "arguments[0].scrollIntoView({block: 'center'});",
                item,
            )
            item.click()
            click_error = None
            break
        except StaleElementReferenceException as error:
            click_error = error
            continue
        except ElementClickInterceptedException as error:
            click_error = error
            try:
                driver.execute_script(
                    "arguments[0].dispatchEvent(new MouseEvent('click', "
                    "{view: window, bubbles: true, cancelable: true}));",
                    item,
                )
                click_error = None
                break
            except (StaleElementReferenceException, WebDriverException) as retry_error:
                click_error = retry_error

    if click_error is not None:
        raise ChartAutomationError(
            f"Failed to click legend category after retries: {category}."
        ) from click_error

    try:
        wait.until(
            lambda active_driver: set(
                _read_doughnut_model(active_driver, plotly_root)["hidden"]
            )
            == expected_hidden
        )
        wait.until(
            lambda active_driver: bool(
                active_driver.execute_script(
                    "return arguments[0].__seleniumAfterPlot === true;",
                    plotly_root,
                )
            )
        )
    except TimeoutException as error:
        current_hidden = set(_read_doughnut_model(driver, plotly_root)["hidden"])
        raise ChartAutomationError(
            f"Legend filter transition failed for {category}. "
            f"Expected hidden={sorted(expected_hidden)}, "
            f"actual hidden={sorted(current_hidden)}."
        ) from error

    _, refreshed_items = _get_legend_items(driver, wait)
    refreshed_item = next(
        (item for item in refreshed_items if _legend_item_name(item) == category),
        None,
    )
    if refreshed_item is None:
        raise ChartAutomationError(
            f"Legend category is missing after interaction: {category}."
        )
    if float(refreshed_item.value_of_css_property("opacity")) >= 1.0:
        raise ChartAutomationError(
            f"Legend category did not become visibly deselected: {category}."
        )


def _clear_prior_doughnut_outputs(base_path: Path, screenshots_path: Path) -> None:
    """Remove only sequential output files owned by this automation."""

    for csv_path in base_path.glob("doughnut*.csv"):
        if re.fullmatch(r"doughnut\d+\.csv", csv_path.name):
            csv_path.unlink()
    if screenshots_path.exists():
        for screenshot_path in screenshots_path.glob("screenshot*.png"):
            if re.fullmatch(r"screenshot\d+\.png", screenshot_path.name):
                screenshot_path.unlink()


def automate_doughnut_chart(
    driver: WebDriver,
    wait: WebDriverWait,
) -> tuple[list[str], list[Path], list[Path], list[int]]:
    """Export initial and cumulatively filtered doughnut-chart states."""

    plotly_root = _get_plotly_root(driver, wait)
    try:
        wait.until(EC.presence_of_element_located((By.CLASS_NAME, "pielayer")))
    except TimeoutException as error:
        raise ChartAutomationError(
            "The doughnut chart did not render before timeout."
        ) from error

    legend_categories = _get_legend_categories(driver, wait)
    base_path = Path(__file__).resolve().parent
    screenshots_path = base_path / "screenshots"
    screenshots_path.mkdir(parents=True, exist_ok=True)
    _clear_prior_doughnut_outputs(base_path, screenshots_path)

    csv_paths: list[Path] = []
    screenshot_paths: list[Path] = []
    active_counts: list[int] = []

    for state_index in range(len(legend_categories) + 1):
        if state_index > 0:
            category = legend_categories[state_index - 1]
            expected_hidden = set(legend_categories[:state_index])
            _click_legend_category(
                driver,
                wait,
                plotly_root,
                category,
                expected_hidden,
            )

        rows, hidden = extract_active_doughnut_data(
            driver,
            wait,
            plotly_root,
            legend_categories,
        )
        expected_hidden = set(legend_categories[:state_index])
        if hidden != expected_hidden:
            raise ChartAutomationError(
                f"Unexpected filter state {state_index}: hidden={sorted(hidden)}, "
                f"expected={sorted(expected_hidden)}."
            )

        csv_path = base_path / f"doughnut{state_index}.csv"
        screenshot_path = screenshots_path / f"screenshot{state_index}.png"
        write_doughnut_csv(rows, csv_path)
        _capture_plotly_screenshot(plotly_root, screenshot_path)
        csv_paths.append(csv_path)
        screenshot_paths.append(screenshot_path)
        active_counts.append(len(rows))
        LOGGER.info(
            "Saved doughnut state %d: active=%d, hidden=%s, csv=%s, screenshot=%s",
            state_index,
            len(rows),
            sorted(hidden),
            csv_path,
            screenshot_path,
        )

    if len(csv_paths) != len(screenshot_paths):
        raise ChartAutomationError(
            "Doughnut CSV and screenshot output counts do not match."
        )
    return legend_categories, csv_paths, screenshot_paths, active_counts


def main(headless: bool = False) -> None:
    """Extract the Plotly table and automate all doughnut filter states."""

    try:
        report_path = resolve_report_path()
        LOGGER.info("Opening local HTML report: %s", report_path)

        with SeleniumWebDriverContextManager(headless=headless) as driver:
            driver.get(report_path.as_uri())
            wait = WebDriverWait(driver, REPORT_LOAD_TIMEOUT_SECONDS)
            wait.until(
                lambda active_driver: active_driver.execute_script(
                    "return document.readyState"
                )
                == "complete"
            )

            print(f"Page title: {driver.title}")
            wait.until(
                EC.visibility_of_element_located(
                    (By.CSS_SELECTOR, ".js-plotly-plot")
                )
            )
            LOGGER.info("Plotly report rendered successfully.")

            headers, rows = extract_plotly_table(driver, wait)
            csv_path = resolve_csv_path()
            write_table_csv(headers, rows, csv_path)

            print(f"Extracted headers: {headers}")
            print(f"Extracted row count: {len(rows)}")
            print("First five data rows:")
            for row in rows[:5]:
                print(row)
            LOGGER.info("Extracted %d table rows to %s", len(rows), csv_path)

            (
                legend_categories,
                doughnut_csv_paths,
                screenshot_paths,
                active_counts,
            ) = automate_doughnut_chart(driver, wait)
            print(f"Legend categories: {legend_categories}")
            print(f"Doughnut active row counts: {active_counts}")
            print(f"Doughnut CSV files: {[path.name for path in doughnut_csv_paths]}")
            print(
                "Doughnut screenshots: "
                f"{[path.name for path in screenshot_paths]}"
            )
            print(
                "Execution summary: "
                f"table_rows={len(rows)}, legend_categories={len(legend_categories)}, "
                f"chart_states={len(doughnut_csv_paths)}"
            )
    except FileNotFoundError:
        LOGGER.exception("Cannot run Selenium because report.html is missing.")
        raise
    except TimeoutException:
        LOGGER.exception("Timed out waiting for the Plotly report to render.")
        raise
    except TableExtractionError:
        LOGGER.exception("Plotly table extraction failed validation.")
        raise
    except ChartAutomationError:
        LOGGER.exception("Doughnut-chart automation failed validation.")
        raise
    except (StaleElementReferenceException, ElementClickInterceptedException):
        LOGGER.exception("A Plotly element became unavailable during interaction.")
        raise
    except WebDriverException:
        LOGGER.exception("Selenium browser execution failed.")
        raise


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    main()
