import hashlib
import json
import logging

import numpy as np
import pandas as pd

from src.config import (
    GENDER_MAP,
    EDUCATION_MAP,
    MARRIAGE_MAP,
    AGE_BINS,
    AGE_LABELS,
    REPAYMENT_COLUMNS,
    BILL_COLUMNS,
    PAYMENT_COLUMNS,
    BILL_MONTH_MAP,
    PAYMENT_MONTH_MAP,
)

logger = logging.getLogger(__name__)


# ============================================================
# 1. NUMERIC TYPE CONVERSION
# ============================================================

def convert_numeric_columns(df):
    """
    Convert numeric source fields to numeric types.

    This function is called only after data-quality
    validation has completed successfully.
    """

    df = df.copy()

    numeric_columns = [
        "customer_id",
        "credit_limit",
        "gender",
        "education",
        "marriage",
        "age",
        "default_next_month",
        *REPAYMENT_COLUMNS,
        *BILL_COLUMNS,
        *PAYMENT_COLUMNS,
    ]

    for column in numeric_columns:

        df[column] = pd.to_numeric(
            df[column],
            errors="raise"
        )

    integer_columns = [
        "customer_id",
        "gender",
        "education",
        "marriage",
        "age",
        "default_next_month",
        *REPAYMENT_COLUMNS,
    ]

    for column in integer_columns:

        if not np.isfinite(df[column]).all():
            raise ValueError(
                f"Non-finite values in {column}"
            )

        if not (df[column] % 1 == 0).all():
            raise ValueError(
                f"Non-integer values in {column}"
            )

        df[column] = df[column].astype("int64")

    logger.info("Numeric conversion completed")

    return df


# ============================================================
# 2. DEMOGRAPHIC TRANSFORMATION
# ============================================================

def transform_demographics(df):
    """
    Create readable demographic labels and age groups.
    """

    df = df.copy()

    df["gender_label"] = (
        df["gender"]
        .map(GENDER_MAP)
        .fillna("Unknown")
    )

    df["education_label"] = (
        df["education"]
        .map(EDUCATION_MAP)
        .fillna("Unknown")
    )

    df["marriage_label"] = (
        df["marriage"]
        .map(MARRIAGE_MAP)
        .fillna("Unknown")
    )

    df["age_group"] = pd.cut(
        df["age"],
        bins=AGE_BINS,
        labels=AGE_LABELS,
        include_lowest=True
    ).astype("object")

    logger.info("Demographic transformation completed")

    return df


# ============================================================
# 3. FINANCIAL INDICATORS
# ============================================================

def calculate_financial_indicators(df):
    """
    Calculate bill, payment and credit indicators.
    """

    df = df.copy()

    df["total_bill_amount"] = (
        df[BILL_COLUMNS].sum(axis=1)
    )

    df["total_payment_amount"] = (
        df[PAYMENT_COLUMNS].sum(axis=1)
    )

    df["avg_bill_amount"] = (
        df[BILL_COLUMNS].mean(axis=1)
    )

    df["avg_payment_amount"] = (
        df[PAYMENT_COLUMNS].mean(axis=1)
    )

    # Latest observed bill relative to credit limit.
    # This is an analytical proxy, not an official
    # bank-calculated utilization measure.

    df["latest_credit_utilization"] = np.where(
        df["credit_limit"] > 0,
        df["bill_amt_sep"] / df["credit_limit"],
        np.nan
    )

    # Six-month aggregate payment-to-bill indicator.
    # It is not a contractual repayment rate.

    df["payment_to_bill_ratio"] = np.where(
        df["total_bill_amount"] > 0,
        df["total_payment_amount"] /
        df["total_bill_amount"],
        np.nan
    )

    logger.info("Financial indicators calculated")

    return df


# ============================================================
# 4. REPAYMENT INDICATORS
# ============================================================

def calculate_repayment_indicators(df):
    """
    Calculate repayment-delay indicators.

    Positive repayment-status codes indicate delays.

    -2, -1 and 0 are preserved and not counted as delays.
    """

    df = df.copy()

    df["months_with_delay"] = (
        df[REPAYMENT_COLUMNS] > 0
    ).sum(axis=1)

    df["max_repayment_delay"] = (
        df[REPAYMENT_COLUMNS]
        .clip(lower=0)
        .max(axis=1)
    )

    logger.info("Repayment indicators calculated")

    return df


# ============================================================
# 5. GENERATE SOURCE RECORD HASH
# ============================================================

HASH_COLUMNS = [
    "customer_id",
    "credit_limit",
    "gender",
    "education",
    "marriage",
    "age",
    *REPAYMENT_COLUMNS,
    *BILL_COLUMNS,
    *PAYMENT_COLUMNS,
    "default_next_month",
]


def generate_record_hash(row):
    """
    Generate a SHA-256 hash from canonical source values.

    The hash detects whether an incoming customer's
    historical source record differs from the stored one.

    Derived columns are deliberately excluded.
    """

    values = {}

    for column in HASH_COLUMNS:

        value = row[column]

        if pd.isna(value):
            values[column] = None

        elif column in [
            "customer_id",
            "gender",
            "education",
            "marriage",
            "age",
            "default_next_month",
            *REPAYMENT_COLUMNS,
        ]:
            values[column] = int(value)

        else:
            # Normalize numeric representation so that
            # 50000 and 50000.0 generate the same hash.
            values[column] = format(
                float(value),
                ".10g"
            )

    serialized = json.dumps(
        values,
        sort_keys=True,
        separators=(",", ":")
    )

    return hashlib.sha256(
        serialized.encode("utf-8")
    ).hexdigest()


def add_record_hash(df):
    """
    Add record_hash for incremental comparison.
    """

    df = df.copy()

    df["record_hash"] = df.apply(
        generate_record_hash,
        axis=1
    )

    logger.info("Record hashes generated")

    return df


# ============================================================
# 6. CREATE CUSTOMERS TABLE
# ============================================================

def create_customers_table(df):

    columns = [
        "customer_id",
        "gender",
        "gender_label",
        "education",
        "education_label",
        "marriage",
        "marriage_label",
        "age",
        "age_group",
        "record_hash",
    ]

    return df[columns].copy()


# ============================================================
# 7. CREATE CREDIT PROFILES TABLE
# ============================================================

def create_credit_profiles_table(df):

    columns = [
        "customer_id",
        "credit_limit",
        *REPAYMENT_COLUMNS,
        "months_with_delay",
        "max_repayment_delay",
        "total_bill_amount",
        "total_payment_amount",
        "avg_bill_amount",
        "avg_payment_amount",
        "latest_credit_utilization",
        "payment_to_bill_ratio",
        "default_next_month",
    ]

    result = df[columns].copy()

    # Replace non-finite calculated ratios with NULL-ready
    # values for MySQL insertion.

    result = result.replace(
        [np.inf, -np.inf],
        np.nan
    )

    return result


# ============================================================
# 8. CREATE BILLS TABLE
# ============================================================

def create_bills_table(df):
    """
    Convert six monthly bill columns into long format.

    Each customer produces six bill records.
    """

    frames = []

    for column, month in BILL_MONTH_MAP.items():

        temp = df[
            ["customer_id", column]
        ].copy()

        temp.rename(
            columns={column: "bill_amount"},
            inplace=True
        )

        temp["month"] = month

        frames.append(temp)

    return pd.concat(
        frames,
        ignore_index=True
    )[["customer_id", "month", "bill_amount"]]


# ============================================================
# 9. CREATE PAYMENTS TABLE
# ============================================================

def create_payments_table(df):
    """
    Convert six monthly payment columns into long format.

    Each customer produces six payment records.
    """

    frames = []

    for column, month in PAYMENT_MONTH_MAP.items():

        temp = df[
            ["customer_id", column]
        ].copy()

        temp.rename(
            columns={column: "payment_amount"},
            inplace=True
        )

        temp["month"] = month

        frames.append(temp)

    return pd.concat(
        frames,
        ignore_index=True
    )[["customer_id", "month", "payment_amount"]]


# ============================================================
# 10. MAIN TRANSFORMATION FUNCTION
# ============================================================

def transform_data(valid_df):
    """
    Transform validated customer data.

    Returns
    -------
    dict:
        customers
        credit_profiles
        bills
        payments
    """

    logger.info(
        "Starting transformation. Records=%d",
        len(valid_df)
    )

    df = convert_numeric_columns(valid_df)

    df = transform_demographics(df)

    df = calculate_financial_indicators(df)

    df = calculate_repayment_indicators(df)

    df = add_record_hash(df)

    tables = {
        "customers": create_customers_table(df),
        "credit_profiles": create_credit_profiles_table(df),
        "bills": create_bills_table(df),
        "payments": create_payments_table(df),
    }

    # --------------------------------------------------------
    # Verify expected output counts
    # --------------------------------------------------------

    customer_count = len(tables["customers"])

    if len(tables["credit_profiles"]) != customer_count:
        raise ValueError(
            "Credit profile count mismatch"
        )

    if len(tables["bills"]) != customer_count * 6:
        raise ValueError(
            "Bill record count mismatch"
        )

    if len(tables["payments"]) != customer_count * 6:
        raise ValueError(
            "Payment record count mismatch"
        )

    logger.info(
        "Transformation completed. "
        "Customers=%d, Bills=%d, Payments=%d",
        customer_count,
        len(tables["bills"]),
        len(tables["payments"])
    )

    return tables