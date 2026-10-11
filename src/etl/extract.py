import logging
from pathlib import Path

import pandas as pd

from src.config import (
    SUPPORTED_FILE_EXTENSIONS,
    EXCEL_SHEET_NAME,
    EXCEL_HEADER_ROW,
    REQUIRED_RAW_COLUMNS,
    COLUMN_RENAME_MAP,
)


logger = logging.getLogger(__name__)


# ============================================================
# VALIDATE INPUT FILE
# ============================================================

def validate_input_file(file_path):
    """
    Validate that the input file exists and has a supported
    Excel file extension.

    Parameters
    ----------
    file_path : str or Path
        Path to the incoming Excel file.

    Returns
    -------
    Path
        Validated Path object.

    Raises
    ------
    FileNotFoundError
        If the file does not exist.

    ValueError
        If the file extension is unsupported.
    """

    file_path = Path(file_path)

    if not file_path.exists():
        raise FileNotFoundError(
            f"Input file does not exist: {file_path}"
        )

    if not file_path.is_file():
        raise ValueError(
            f"Input path is not a file: {file_path}"
        )

    if file_path.suffix.lower() not in SUPPORTED_FILE_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {file_path.suffix}. "
            f"Supported types: {SUPPORTED_FILE_EXTENSIONS}"
        )

    logger.info(
        "Input file validated successfully: %s",
        file_path.name
    )

    return file_path


# ============================================================
# READ EXCEL FILE
# ============================================================

def read_excel_file(file_path):
    """
    Read the banking dataset from XLS/XLSX.

    The UCI source workbook contains the actual column
    headings on the second row, therefore EXCEL_HEADER_ROW
    is configured as 1.

    Returns
    -------
    pandas.DataFrame
    """

    file_path = Path(file_path)

    logger.info(
        "Reading source file: %s",
        file_path.name
    )

    try:

        # .xls uses xlrd
        if file_path.suffix.lower() == ".xls":
            engine = "xlrd"

        # .xlsx uses openpyxl
        else:
            engine = "openpyxl"

        df = pd.read_excel(
            file_path,
            sheet_name=EXCEL_SHEET_NAME,
            header=EXCEL_HEADER_ROW,
            engine=engine
        )

        logger.info(
            "Source file read successfully. Rows=%d, Columns=%d",
            len(df),
            len(df.columns)
        )

        return df

    except ValueError as exc:

        # Common example:
        # sheet "Data" does not exist.

        logger.exception(
            "Unable to read expected sheet '%s' from %s",
            EXCEL_SHEET_NAME,
            file_path.name
        )

        raise ValueError(
            f"Could not read sheet '{EXCEL_SHEET_NAME}' "
            f"from {file_path.name}: {exc}"
        ) from exc

    except Exception as exc:

        logger.exception(
            "Failed to read Excel file: %s",
            file_path.name
        )

        raise RuntimeError(
            f"Failed to read Excel file "
            f"'{file_path.name}': {exc}"
        ) from exc


# ============================================================
# VALIDATE SOURCE SCHEMA
# ============================================================

def validate_source_schema(df):
    """
    Check whether all required raw dataset columns exist.

    Extra columns are allowed, but required columns must
    always be present.

    Parameters
    ----------
    df : pandas.DataFrame

    Raises
    ------
    ValueError
        If one or more required columns are missing.
    """

    actual_columns = set(df.columns)

    missing_columns = [
        column
        for column in REQUIRED_RAW_COLUMNS
        if column not in actual_columns
    ]

    if missing_columns:

        logger.error(
            "Source schema validation failed. "
            "Missing columns: %s",
            missing_columns
        )

        raise ValueError(
            "Source schema validation failed. "
            f"Missing required columns: {missing_columns}"
        )

    logger.info(
        "Source schema validation passed."
    )


# ============================================================
# STANDARDIZE COLUMN NAMES
# ============================================================

def standardize_columns(df):
    """
    Standardize raw Excel column names and apply the
    configured banking column mappings.

    Returns
    -------
    pandas.DataFrame
    """

    df = df.copy()

    # Example:
    #
    # LIMIT_BAL
    #      ↓
    # limit_bal
    #
    # default.payment.next.month
    #      ↓
    # default_payment_next_month

    df.columns = (
        df.columns
        .astype(str)
        .str.strip()
        .str.lower()
        .str.replace(".", "_", regex=False)
        .str.replace(" ", "_", regex=False)
    )

    # Apply our business-friendly names.
    #
    # id        -> customer_id
    # limit_bal -> credit_limit
    # pay_0     -> repayment_status_sep

    df.rename(
        columns=COLUMN_RENAME_MAP,
        inplace=True
    )

    logger.info(
        "Column names standardized successfully."
    )

    return df


# ============================================================
# EXTRACT DATA
# ============================================================

def extract_data(file_path):
    """
    Main extraction function.

    Processing:
        1. Validate input file
        2. Read Excel
        3. Validate source schema
        4. Standardize column names

    Returns
    -------
    pandas.DataFrame
        Extracted DataFrame ready for data-quality validation.
    """

    logger.info(
        "Starting extraction for: %s",
        file_path
    )

    file_path = validate_input_file(file_path)

    df = read_excel_file(file_path)

    # Validate BEFORE renaming because REQUIRED_RAW_COLUMNS
    # contains the original UCI column names.
    validate_source_schema(df)

    df = standardize_columns(df)

    logger.info(
        "Extraction completed successfully. "
        "File=%s, Records=%d",
        file_path.name,
        len(df)
    )

    return df