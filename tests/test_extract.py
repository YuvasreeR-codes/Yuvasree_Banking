
from pathlib import Path

import pandas as pd
import pytest

from src.etl import extract


# ============================================================
# TEST FIXTURES
# ============================================================

@pytest.fixture
def sample_raw_df():
    """Create a DataFrame with all required raw columns."""
    return pd.DataFrame({
        column: [1, 2]
        for column in extract.REQUIRED_RAW_COLUMNS
    })


@pytest.fixture
def valid_excel_file(tmp_path):
    """Create a temporary Excel file for validation tests."""
    file_path = tmp_path / "banking_data.xlsx"
    file_path.touch()
    return file_path


# ============================================================
# TEST VALIDATE INPUT FILE
# ============================================================

def test_validate_input_file_success(valid_excel_file):
    result = extract.validate_input_file(valid_excel_file)

    assert result == valid_excel_file
    assert isinstance(result, Path)


def test_validate_input_file_missing(tmp_path):
    file_path = tmp_path / "missing.xlsx"

    with pytest.raises(FileNotFoundError):
        extract.validate_input_file(file_path)


def test_validate_input_file_unsupported(tmp_path):
    file_path = tmp_path / "banking_data.txt"
    file_path.touch()

    with pytest.raises(ValueError, match="Unsupported file type"):
        extract.validate_input_file(file_path)


def test_validate_input_file_directory(tmp_path):
    with pytest.raises(ValueError, match="not a file"):
        extract.validate_input_file(tmp_path)


# ============================================================
# TEST READ EXCEL FILE
# ============================================================

def test_read_excel_file_success(monkeypatch, valid_excel_file):
    expected_df = pd.DataFrame({
        "ID": [1, 2],
        "LIMIT_BAL": [20000, 50000]
    })

    def mock_read_excel(file_path, sheet_name, header, engine):
        assert Path(file_path) == valid_excel_file
        assert sheet_name == extract.EXCEL_SHEET_NAME
        assert header == extract.EXCEL_HEADER_ROW
        assert engine == "openpyxl"
        return expected_df

    monkeypatch.setattr(
        extract.pd,
        "read_excel",
        mock_read_excel
    )

    result = extract.read_excel_file(valid_excel_file)

    pd.testing.assert_frame_equal(result, expected_df)


def test_read_excel_file_missing_sheet(monkeypatch, valid_excel_file):
    def mock_read_excel(*args, **kwargs):
        raise ValueError("Worksheet not found")

    monkeypatch.setattr(
        extract.pd,
        "read_excel",
        mock_read_excel
    )

    with pytest.raises(ValueError, match="Could not read sheet"):
        extract.read_excel_file(valid_excel_file)


def test_read_excel_file_failure(monkeypatch, valid_excel_file):
    def mock_read_excel(*args, **kwargs):
        raise OSError("Unable to read workbook")

    monkeypatch.setattr(
        extract.pd,
        "read_excel",
        mock_read_excel
    )

    with pytest.raises(RuntimeError, match="Failed to read Excel file"):
        extract.read_excel_file(valid_excel_file)


# ============================================================
# TEST SOURCE SCHEMA VALIDATION
# ============================================================

def test_validate_source_schema_success(sample_raw_df):
    result = extract.validate_source_schema(sample_raw_df)

    assert result is None


def test_validate_source_schema_missing_columns(sample_raw_df):
    missing_column = extract.REQUIRED_RAW_COLUMNS[0]

    df = sample_raw_df.drop(columns=[missing_column])

    with pytest.raises(ValueError, match="Missing required columns"):
        extract.validate_source_schema(df)


def test_validate_source_schema_extra_columns(sample_raw_df):
    sample_raw_df["EXTRA_COLUMN"] = [10, 20]

    extract.validate_source_schema(sample_raw_df)


# ============================================================
# TEST STANDARDIZE COLUMNS
# ============================================================

def test_standardize_columns():
    df = pd.DataFrame({
        " ID ": [1],
        "LIMIT_BAL": [20000],
        "default.payment.next.month": [0]
    })

    result = extract.standardize_columns(df)

    assert "customer_id" in result.columns
    assert "credit_limit" in result.columns
    assert "default_next_month" in result.columns

def test_standardize_columns_does_not_modify_original():
    df = pd.DataFrame({
        "LIMIT_BAL": [20000]
    })

    original_df = df.copy(deep=True)

    extract.standardize_columns(df)

    pd.testing.assert_frame_equal(df, original_df)


# ============================================================
# TEST COMPLETE EXTRACTION WORKFLOW
# ============================================================

def test_extract_data_success(
    monkeypatch,
    valid_excel_file,
    sample_raw_df
):
    def mock_read_excel_file(file_path):
        return sample_raw_df.copy()

    monkeypatch.setattr(
        extract,
        "read_excel_file",
        mock_read_excel_file
    )

    result = extract.extract_data(valid_excel_file)

    assert isinstance(result, pd.DataFrame)
    assert len(result) == len(sample_raw_df)
    assert "customer_id" in result.columns
    assert "credit_limit" in result.columns


def test_extract_data_invalid_file(tmp_path):
    missing_file = tmp_path / "missing.xlsx"

    with pytest.raises(FileNotFoundError):
        extract.extract_data(missing_file)
