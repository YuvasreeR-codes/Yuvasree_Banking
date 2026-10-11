
import pandas as pd
import pytest

from src.etl import data_quality as dq


# ============================================================
# FIXTURE: VALID BANKING CUSTOMER RECORDS
# ============================================================

@pytest.fixture
def valid_df():
    """Create two valid records using project configuration."""

    def first_value(values):
        return sorted(values)[0]

    row = {
        "customer_id": 1,
        "credit_limit": max(dq.MIN_CREDIT_LIMIT, 50000),
        "gender": first_value(dq.VALID_GENDER_VALUES),
        "education": first_value(dq.VALID_EDUCATION_VALUES),
        "marriage": first_value(dq.VALID_MARRIAGE_VALUES),
        "age": dq.MIN_AGE,
        "default_next_month": first_value(dq.VALID_DEFAULT_VALUES),
    }

    row.update({
        column: first_value(dq.VALID_REPAYMENT_VALUES)
        for column in dq.REPAYMENT_COLUMNS
    })

    row.update({
        column: 1000
        for column in dq.BILL_COLUMNS
    })

    row.update({
        column: 500
        for column in dq.PAYMENT_COLUMNS
    })

    df = pd.DataFrame([row, row.copy()])
    df.loc[1, "customer_id"] = 2

    return df


# ============================================================
# TEST ISSUE CREATION
# ============================================================

def test_create_issue():
    issue = dq.create_issue(
        customer_id=1,
        check_name="INVALID_AGE_RANGE",
        column_name="age",
        invalid_value=10,
        reason="Invalid age"
    )

    assert issue["customer_id"] == 1
    assert issue["check_name"] == "INVALID_AGE_RANGE"
    assert issue["invalid_value"] == "10"
    assert issue["reason"] == "Invalid age"


def test_create_issue_null_value():
    issue = dq.create_issue(
        1, "MISSING_VALUE", "age", None, "Missing age"
    )

    assert issue["invalid_value"] is None


# ============================================================
# TEST MISSING VALUES
# ============================================================

def test_missing_values_valid(valid_df):
    assert dq.check_missing_values(valid_df) == []


def test_missing_values_detected(valid_df):
    valid_df.loc[0, "age"] = None

    issues = dq.check_missing_values(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "MISSING_VALUE"
    assert issues[0]["column_name"] == "age"


# ============================================================
# TEST DUPLICATE CUSTOMER IDS
# ============================================================

def test_duplicate_ids_valid(valid_df):
    assert dq.check_duplicate_customer_ids(valid_df) == []


def test_duplicate_ids_detected(valid_df):
    valid_df.loc[1, "customer_id"] = 1

    issues = dq.check_duplicate_customer_ids(valid_df)

    # Both occurrences are flagged because keep=False.
    assert len(issues) == 2
    assert all(
        issue["check_name"] == "DUPLICATE_CUSTOMER_ID"
        for issue in issues
    )


# ============================================================
# TEST CUSTOMER ID VALIDATION
# ============================================================

@pytest.mark.parametrize("invalid_id", [0, -1, 1.5, "abc"])
def test_invalid_customer_id(valid_df, invalid_id):
    valid_df["customer_id"] = valid_df["customer_id"].astype(object)
    valid_df.at[0, "customer_id"] = invalid_id

    issues = dq.check_customer_id(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_CUSTOMER_ID"


def test_valid_customer_id(valid_df):
    assert dq.check_customer_id(valid_df) == []


# ============================================================
# TEST AGE VALIDATION
# ============================================================

@pytest.mark.parametrize(
    "invalid_age",
    [dq.MIN_AGE - 1, dq.MAX_AGE + 1]
)
def test_invalid_age_range(valid_df, invalid_age):
    valid_df.loc[0, "age"] = invalid_age

    issues = dq.check_age_range(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_AGE_RANGE"


def test_invalid_age_type(valid_df):
    valid_df["age"] = valid_df["age"].astype(object)
    valid_df.at[0, "age"] = "invalid"

    issues = dq.check_age_range(valid_df)

    assert issues[0]["check_name"] == "INVALID_AGE_TYPE"


def test_valid_age_boundaries(valid_df):
    valid_df.loc[0, "age"] = dq.MIN_AGE
    valid_df.loc[1, "age"] = dq.MAX_AGE

    assert dq.check_age_range(valid_df) == []


# ============================================================
# TEST CREDIT LIMIT
# ============================================================

def test_invalid_credit_limit(valid_df):
    valid_df.loc[0, "credit_limit"] = dq.MIN_CREDIT_LIMIT - 1

    issues = dq.check_credit_limit(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_CREDIT_LIMIT"


def test_invalid_credit_limit_type(valid_df):
    valid_df["credit_limit"] = valid_df["credit_limit"].astype(object)
    valid_df.at[0, "credit_limit"] = "invalid"

    issues = dq.check_credit_limit(valid_df)

    assert issues[0]["check_name"] == "INVALID_CREDIT_LIMIT_TYPE"


# ============================================================
# TEST DEMOGRAPHIC VALUES
# ============================================================

@pytest.mark.parametrize(
    "column,check_name",
    [
        ("gender", "INVALID_GENDER"),
        ("education", "INVALID_EDUCATION"),
        ("marriage", "INVALID_MARRIAGE"),
    ]
)
def test_invalid_demographic(valid_df, column, check_name):
    valid_df.loc[0, column] = 999

    issues = dq.check_demographic_values(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == check_name


def test_valid_demographics(valid_df):
    assert dq.check_demographic_values(valid_df) == []


# ============================================================
# TEST REPAYMENT STATUS
# ============================================================

def test_invalid_repayment_status(valid_df):
    column = dq.REPAYMENT_COLUMNS[0]
    valid_df.loc[0, column] = 999

    issues = dq.check_repayment_status(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_REPAYMENT_STATUS"


def test_valid_repayment_status(valid_df):
    assert dq.check_repayment_status(valid_df) == []


# ============================================================
# TEST PAYMENT AMOUNTS
# ============================================================

def test_negative_payment(valid_df):
    column = dq.PAYMENT_COLUMNS[0]
    valid_df.loc[0, column] = -100

    issues = dq.check_payment_amounts(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "NEGATIVE_PAYMENT_AMOUNT"


def test_invalid_payment_type(valid_df):
    column = dq.PAYMENT_COLUMNS[0]
    valid_df[column] = valid_df[column].astype(object)
    valid_df.at[0, column] = "invalid"

    issues = dq.check_payment_amounts(valid_df)

    assert issues[0]["check_name"] == "INVALID_PAYMENT_TYPE"


def test_valid_payments(valid_df):
    assert dq.check_payment_amounts(valid_df) == []


# ============================================================
# TEST BILL AMOUNTS
# ============================================================

def test_negative_bill_allowed(valid_df):
    column = dq.BILL_COLUMNS[0]
    valid_df.loc[0, column] = -500

    assert dq.check_bill_amounts(valid_df) == []


def test_invalid_bill_type(valid_df):
    column = dq.BILL_COLUMNS[0]
    valid_df[column] = valid_df[column].astype(object)
    valid_df.at[0, column] = "invalid"

    issues = dq.check_bill_amounts(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_BILL_AMOUNT"


# ============================================================
# TEST DEFAULT INDICATOR
# ============================================================

def test_invalid_default_indicator(valid_df):
    valid_df.loc[0, "default_next_month"] = 5

    issues = dq.check_default_indicator(valid_df)

    assert len(issues) == 1
    assert issues[0]["check_name"] == "INVALID_DEFAULT_INDICATOR"


def test_valid_default_indicator(valid_df):
    assert dq.check_default_indicator(valid_df) == []


# ============================================================
# TEST COMPLETE DATA QUALITY WORKFLOW
# ============================================================

def test_all_valid_records(valid_df):
    valid, rejected, issues = dq.run_data_quality_checks(valid_df)

    assert len(valid) == 2
    assert rejected.empty
    assert issues.empty
    assert "rejection_reason" in rejected.columns


def test_one_rejected_record(valid_df):
    valid_df.loc[0, "age"] = dq.MIN_AGE - 1

    valid, rejected, issues = dq.run_data_quality_checks(valid_df)

    assert len(valid) == 1
    assert len(rejected) == 1
    assert len(issues) == 1
    assert rejected.iloc[0]["customer_id"] == 1
    assert "Age must be between" in rejected.iloc[0]["rejection_reason"]


def test_multiple_issues_same_customer(valid_df):
    valid_df.loc[0, "age"] = dq.MIN_AGE - 1
    valid_df.loc[0, "credit_limit"] = dq.MIN_CREDIT_LIMIT - 1

    valid, rejected, issues = dq.run_data_quality_checks(valid_df)

    assert len(valid) == 1
    assert len(rejected) == 1
    assert len(issues) == 2
    assert " | " in rejected.iloc[0]["rejection_reason"]


def test_missing_customer_id_rejected(valid_df):
    valid_df["customer_id"] = valid_df["customer_id"].astype(float)
    valid_df.loc[0, "customer_id"] = float("nan")

    valid, rejected, issues = dq.run_data_quality_checks(valid_df)

    assert len(valid) == 1
    assert len(rejected) == 1
    assert rejected.iloc[0]["rejection_reason"] == "Missing customer_id"
    assert "MISSING_VALUE" in issues["check_name"].values


def test_duplicate_customers_rejected(valid_df):
    valid_df.loc[1, "customer_id"] = 1

    valid, rejected, issues = dq.run_data_quality_checks(valid_df)

    assert valid.empty
    assert len(rejected) == 2
    assert len(issues) == 2


def test_input_dataframe_not_modified(valid_df):
    original = valid_df.copy(deep=True)

    dq.run_data_quality_checks(valid_df)

    pd.testing.assert_frame_equal(valid_df, original)
