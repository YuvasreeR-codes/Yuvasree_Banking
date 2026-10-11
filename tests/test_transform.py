
import hashlib

import numpy as np
import pandas as pd
import pytest

from src.etl import transform as tr


# ============================================================
# FIXTURE: VALID CUSTOMER DATA
# ============================================================

@pytest.fixture
def valid_df():
    """Two synthetic banking records."""

    row = {
        "customer_id": 1,
        "credit_limit": 50000,
        "gender": next(iter(tr.GENDER_MAP)),
        "education": next(iter(tr.EDUCATION_MAP)),
        "marriage": next(iter(tr.MARRIAGE_MAP)),
        "age": 30,
        "default_next_month": 0,
    }

    row.update({
        col: 0 for col in tr.REPAYMENT_COLUMNS
    })

    row.update({
        col: 6000 for col in tr.BILL_COLUMNS
    })

    row.update({
        col: 1000 for col in tr.PAYMENT_COLUMNS
    })

    df = pd.DataFrame([row, row.copy()])
    df.loc[1, "customer_id"] = 2

    return df


# ============================================================
# 1. NUMERIC CONVERSION
# ============================================================

def test_numeric_conversion(valid_df):
    valid_df["credit_limit"] = valid_df["credit_limit"].astype(str)

    result = tr.convert_numeric_columns(valid_df)

    assert pd.api.types.is_numeric_dtype(result["credit_limit"])
    assert result.loc[0, "credit_limit"] == 50000


def test_integer_conversion(valid_df):
    valid_df["customer_id"] = ["1", "2"]

    result = tr.convert_numeric_columns(valid_df)

    assert result["customer_id"].dtype == "int64"


def test_invalid_numeric_value(valid_df):
    valid_df["credit_limit"] = valid_df["credit_limit"].astype(object)
    valid_df.at[0, "credit_limit"] = "invalid"

    with pytest.raises(ValueError):
        tr.convert_numeric_columns(valid_df)


def test_fractional_customer_id(valid_df):
    valid_df["customer_id"] = [1.5, 2]

    with pytest.raises(ValueError, match="Non-integer"):
        tr.convert_numeric_columns(valid_df)


def test_nonfinite_customer_id(valid_df):
    valid_df["customer_id"] = [np.inf, 2]

    with pytest.raises(ValueError, match="Non-finite"):
        tr.convert_numeric_columns(valid_df)


# ============================================================
# 2. DEMOGRAPHIC TRANSFORMATION
# ============================================================

def test_demographic_labels(valid_df):
    result = tr.transform_demographics(valid_df)

    assert result.loc[0, "gender_label"] == tr.GENDER_MAP[
        valid_df.loc[0, "gender"]
    ]

    assert result.loc[0, "education_label"] == tr.EDUCATION_MAP[
        valid_df.loc[0, "education"]
    ]

    assert result.loc[0, "marriage_label"] == tr.MARRIAGE_MAP[
        valid_df.loc[0, "marriage"]
    ]


def test_unknown_demographic_label(valid_df):
    valid_df.loc[0, "gender"] = 999

    result = tr.transform_demographics(valid_df)

    assert result.loc[0, "gender_label"] == "Unknown"


def test_age_group(valid_df):
    result = tr.transform_demographics(valid_df)

    assert "age_group" in result.columns
    assert pd.notna(result.loc[0, "age_group"])
    assert result.loc[0, "age_group"] in tr.AGE_LABELS


# ============================================================
# 3. FINANCIAL INDICATORS
# ============================================================

def test_financial_totals(valid_df):
    result = tr.calculate_financial_indicators(valid_df)

    assert result.loc[0, "total_bill_amount"] == 36000
    assert result.loc[0, "total_payment_amount"] == 6000


def test_financial_averages(valid_df):
    result = tr.calculate_financial_indicators(valid_df)

    assert result.loc[0, "avg_bill_amount"] == 6000
    assert result.loc[0, "avg_payment_amount"] == 1000


def test_credit_utilization(valid_df):
    result = tr.calculate_financial_indicators(valid_df)

    assert result.loc[0, "latest_credit_utilization"] == pytest.approx(
        6000 / 50000
    )


def test_payment_to_bill_ratio(valid_df):
    result = tr.calculate_financial_indicators(valid_df)

    assert result.loc[0, "payment_to_bill_ratio"] == pytest.approx(
        6000 / 36000
    )


def test_zero_credit_limit_ratio(valid_df):
    valid_df.loc[0, "credit_limit"] = 0

    result = tr.calculate_financial_indicators(valid_df)

    assert pd.isna(result.loc[0, "latest_credit_utilization"])


def test_zero_total_bill_ratio(valid_df):
    valid_df.loc[0, tr.BILL_COLUMNS] = 0

    result = tr.calculate_financial_indicators(valid_df)

    assert pd.isna(result.loc[0, "payment_to_bill_ratio"])


# ============================================================
# 4. REPAYMENT INDICATORS
# ============================================================

def test_repayment_delay_indicators(valid_df):
    valid_df.loc[0, tr.REPAYMENT_COLUMNS[0]] = 2
    valid_df.loc[0, tr.REPAYMENT_COLUMNS[1]] = 3

    result = tr.calculate_repayment_indicators(valid_df)

    assert result.loc[0, "months_with_delay"] == 2
    assert result.loc[0, "max_repayment_delay"] == 3


def test_nonpositive_repayment_status(valid_df):
    valid_df.loc[0, tr.REPAYMENT_COLUMNS[0]] = -2
    valid_df.loc[0, tr.REPAYMENT_COLUMNS[1]] = -1

    result = tr.calculate_repayment_indicators(valid_df)

    assert result.loc[0, "months_with_delay"] == 0
    assert result.loc[0, "max_repayment_delay"] == 0


# ============================================================
# 5. RECORD HASH
# ============================================================

def test_record_hash_format(valid_df):
    record_hash = tr.generate_record_hash(valid_df.iloc[0])

    assert len(record_hash) == 64
    assert all(c in "0123456789abcdef" for c in record_hash)


def test_record_hash_consistency(valid_df):
    first = tr.generate_record_hash(valid_df.iloc[0])
    second = tr.generate_record_hash(valid_df.iloc[0])

    assert first == second


def test_record_hash_detects_change(valid_df):
    original_hash = tr.generate_record_hash(valid_df.iloc[0])

    modified = valid_df.copy()
    modified.loc[0, "credit_limit"] = 90000

    modified_hash = tr.generate_record_hash(modified.iloc[0])

    assert original_hash != modified_hash


def test_record_hash_numeric_normalization(valid_df):
    first = tr.generate_record_hash(valid_df.iloc[0])

    modified = valid_df.copy()
    modified["credit_limit"] = modified["credit_limit"].astype(float)

    second = tr.generate_record_hash(modified.iloc[0])

    assert first == second


def test_add_record_hash(valid_df):
    result = tr.add_record_hash(valid_df)

    assert "record_hash" in result.columns
    assert len(result) == len(valid_df)
    assert result["record_hash"].str.len().eq(64).all()


# ============================================================
# 6. COMPLETE TRANSFORMATION
# ============================================================

def test_transform_data_tables(valid_df):
    tables = tr.transform_data(valid_df)

    assert set(tables.keys()) == {
        "customers",
        "credit_profiles",
        "bills",
        "payments",
    }


def test_transform_data_record_counts(valid_df):
    tables = tr.transform_data(valid_df)

    assert len(tables["customers"]) == 2
    assert len(tables["credit_profiles"]) == 2
    assert len(tables["bills"]) == 12
    assert len(tables["payments"]) == 12


def test_customer_table_columns(valid_df):
    tables = tr.transform_data(valid_df)

    customers = tables["customers"]

    assert "customer_id" in customers.columns
    assert "gender_label" in customers.columns
    assert "age_group" in customers.columns
    assert "record_hash" in customers.columns


def test_credit_profile_columns(valid_df):
    tables = tr.transform_data(valid_df)

    profiles = tables["credit_profiles"]

    assert "credit_limit" in profiles.columns
    assert "months_with_delay" in profiles.columns
    assert "latest_credit_utilization" in profiles.columns
    assert "payment_to_bill_ratio" in profiles.columns


def test_bill_table_structure(valid_df):
    tables = tr.transform_data(valid_df)

    bills = tables["bills"]

    assert list(bills.columns) == [
        "customer_id",
        "month",
        "bill_amount",
    ]

    assert bills.groupby("customer_id").size().eq(6).all()
    assert set(bills["month"]) == set(tr.BILL_MONTH_MAP.values())


def test_payment_table_structure(valid_df):
    tables = tr.transform_data(valid_df)

    payments = tables["payments"]

    assert list(payments.columns) == [
        "customer_id",
        "month",
        "payment_amount",
    ]

    assert payments.groupby("customer_id").size().eq(6).all()
    assert set(payments["month"]) == set(
        tr.PAYMENT_MONTH_MAP.values()
    )


def test_bill_amounts_preserved(valid_df):
    tables = tr.transform_data(valid_df)

    bills = tables["bills"]

    assert bills["bill_amount"].eq(6000).all()


def test_payment_amounts_preserved(valid_df):
    tables = tr.transform_data(valid_df)

    payments = tables["payments"]

    assert payments["payment_amount"].eq(1000).all()


def test_transform_does_not_modify_input(valid_df):
    original = valid_df.copy(deep=True)

    tr.transform_data(valid_df)

    pd.testing.assert_frame_equal(valid_df, original)
