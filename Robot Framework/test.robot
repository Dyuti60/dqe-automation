*** Settings ***
Library           SeleniumLibrary
Library           ${CURDIR}${/}helper.py
Test Teardown     Close All Browsers


*** Variables ***
${REPORT_FILE}       ${CURDIR}${/}..${/}Selenium Introduction${/}report.html
${PARQUET_FOLDER}    D:/parquet_data/facility_type_avg_time_spent_per_visit_date
${FILTER_DATE}       ${EMPTY}


*** Test Cases ***
Plotly Report Table Matches Parquet Data
    ${report_uri}=    Evaluate
    ...    pathlib.Path($REPORT_FILE).resolve().as_uri()
    ...    modules=pathlib
    Open Browser    ${report_uri}    Chrome
    Wait Until Page Contains Element    css:.table    timeout=20s
    Wait Until Page Contains Element
    ...    css:.table .y-column #header .cell-text
    ...    timeout=20s
    Wait Until Page Contains Element
    ...    css:.table .y-column .column-block[id^="cells"] .column-cell .cell-text
    ...    timeout=20s

    ${table_element}=    Get WebElement    css:.table
    ${html_df}=    Read Html Table    ${table_element}
    ${parquet_df}=    Read Parquet Data    ${PARQUET_FOLDER}    ${FILTER_DATE}

    ${has_filter}=    Evaluate    bool(str($FILTER_DATE).strip())
    IF    ${has_filter}
        ${html_df}=    Evaluate
        ...    $html_df.loc[$html_df["Visit Date"] == str($FILTER_DATE).strip()].reset_index(drop=True)
    END

    ${is_match}    ${differences}=    Compare Dataframes
    ...    ${html_df}
    ...    ${parquet_df}
    Should Be True    ${is_match}    ${differences}
