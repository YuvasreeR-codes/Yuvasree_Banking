import logging

import pandas as pd

from src.config import (
    MIN_AGE,
    MAX_AGE,
    MIN_CREDIT_LIMIT,
    VALID_GENDER_VALUES,
    VALID_EDUCATION_VALUES,
    VALID_MARRIAGE_VALUES,
    VALID_DEFAULT_VALUES,
    VALID_REPAYMENT_VALUES,
    REPAYMENT_COLUMNS,
    BILL_COLUMNS,
    PAYMENT_COLUMNS,
)


logger = logging.getLogger(__name__)


# ============================================================
# REQUIRED FIELDS
# ============================================================

REQUIRED_VALUE_COLUMNS = [
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


# ============================================================
# HELPER: CREATE ISSUE RECORD
# ============================================================

def create_issue(
    customer_id,
    check_name,
    column_name,
    invalid_value,
    reason
):
    """
    Create a standardized data-quality issue dictionary.

    These dictionaries can later be inserted into the
    data_quality_issues MySQL table.
    """

    return {
        "customer_id": customer_id,
        "check_name": check_name,
        "column_name": column_name,
        "invalid_value": (
            None
            if pd.isna(invalid_value)
            else str(invalid_value)
        ),
        "reason": reason,
    }


# ============================================================
# CHECK 1: MISSING VALUES
# ============================================================

def check_missing_values(df):
    """
    Check required columns for missing/null values.
    """

    issues = []

    for index, row in df.iterrows():

        customer_id = row.get("customer_id")

        for column in REQUIRED_VALUE_COLUMNS:

            if pd.isna(row[column]):

                issues.append(
                    create_issue(
                        customer_id=customer_id,
                        check_name="MISSING_VALUE",
                        column_name=column,
                        invalid_value=None,
                        reason=f"{column} contains a missing value"
                    )
                )

    return issues


# ============================================================
# CHECK 2: DUPLICATE CUSTOMER IDs
# ============================================================

def check_duplicate_customer_ids(df):
    """
    Detect duplicate customer IDs inside the current
    incoming batch.

    This does NOT check MySQL.

    Existing IDs in MySQL are handled later by
    incremental.py.
    """

    issues = []

    duplicate_mask = df.duplicated(
        subset=["customer_id"],
        keep=False
    )

    duplicate_rows = df[duplicate_mask]

    for _, row in duplicate_rows.iterrows():

        issues.append(
            create_issue(
                customer_id=row["customer_id"],
                check_name="DUPLICATE_CUSTOMER_ID",
                column_name="customer_id",
                invalid_value=row["customer_id"],
                reason=(
                    "Duplicate customer_id found "
                    "within the incoming batch"
                )
            )
        )

    return issues


# ============================================================
# CHECK 3: CUSTOMER ID
# ============================================================

def check_customer_id(df):
    """
    Validate customer ID.

    Customer IDs must be positive numeric values.
    """

    issues = []

    for _, row in df.iterrows():

        value = row["customer_id"]

        if pd.isna(value):
            continue

        try:
            numeric_value = float(value)

            if numeric_value <= 0:

                issues.append(
                    create_issue(
                        customer_id=value,
                        check_name="INVALID_CUSTOMER_ID",
                        column_name="customer_id",
                        invalid_value=value,
                        reason=(
                            "customer_id must be greater than 0"
                        )
                    )
                )

            elif not numeric_value.is_integer():

                issues.append(
                    create_issue(
                        customer_id=value,
                        check_name="INVALID_CUSTOMER_ID",
                        column_name="customer_id",
                        invalid_value=value,
                        reason=(
                            "customer_id must be a whole number"
                        )
                    )
                )

        except (TypeError, ValueError):

            issues.append(
                create_issue(
                    customer_id=value,
                    check_name="INVALID_CUSTOMER_ID",
                    column_name="customer_id",
                    invalid_value=value,
                    reason="customer_id must be numeric"
                )
            )

    return issues


# ============================================================
# CHECK 4: AGE RANGE
# ============================================================

def check_age_range(df):
    """
    Validate customer age.

    Valid project range:
        MIN_AGE <= age <= MAX_AGE
    """

    issues = []

    for _, row in df.iterrows():

        age = row["age"]

        if pd.isna(age):
            continue

        try:
            age_value = float(age)

            if age_value < MIN_AGE or age_value > MAX_AGE:

                issues.append(
                    create_issue(
                        customer_id=row["customer_id"],
                        check_name="INVALID_AGE_RANGE",
                        column_name="age",
                        invalid_value=age,
                        reason=(
                            f"Age must be between "
                            f"{MIN_AGE} and {MAX_AGE}"
                        )
                    )
                )

        except (TypeError, ValueError):

            issues.append(
                create_issue(
                    customer_id=row["customer_id"],
                    check_name="INVALID_AGE_TYPE",
                    column_name="age",
                    invalid_value=age,
                    reason="Age must be numeric"
                )
            )

    return issues


# ============================================================
# CHECK 5: CREDIT LIMIT
# ============================================================

def check_credit_limit(df):
    """
    Credit limit must be a positive numeric value.
    """

    issues = []

    for _, row in df.iterrows():

        value = row["credit_limit"]

        if pd.isna(value):
            continue

        try:
            credit_limit = float(value)

            if credit_limit < MIN_CREDIT_LIMIT:

                issues.append(
                    create_issue(
                        customer_id=row["customer_id"],
                        check_name="INVALID_CREDIT_LIMIT",
                        column_name="credit_limit",
                        invalid_value=value,
                        reason=(
                            "Credit limit must be greater "
                            "than or equal to "
                            f"{MIN_CREDIT_LIMIT}"
                        )
                    )
                )

        except (TypeError, ValueError):

            issues.append(
                create_issue(
                    customer_id=row["customer_id"],
                    check_name="INVALID_CREDIT_LIMIT_TYPE",
                    column_name="credit_limit",
                    invalid_value=value,
                    reason="Credit limit must be numeric"
                )
            )

    return issues


# ============================================================
# GENERIC CATEGORY CHECK
# ============================================================

def check_allowed_values(
    df,
    column,
    allowed_values,
    check_name
):
    """
    Generic reusable validator for categorical fields.

    Used for:
        gender
        education
        marriage
        default indicator
    """

    issues = []

    for _, row in df.iterrows():

        value = row[column]

        if pd.isna(value):
            continue

        if value not in allowed_values:

            issues.append(
                create_issue(
                    customer_id=row["customer_id"],
                    check_name=check_name,
                    column_name=column,
                    invalid_value=value,
                    reason=(
                        f"{column} must be one of "
                        f"{allowed_values}"
                    )
                )
            )

    return issues


# ============================================================
# CHECK 6: DEMOGRAPHIC VALUES
# ============================================================

def check_demographic_values(df):
    """
    Validate gender, education and marriage codes.
    """

    issues = []

    issues.extend(
        check_allowed_values(
            df,
            "gender",
            VALID_GENDER_VALUES,
            "INVALID_GENDER"
        )
    )

    issues.extend(
        check_allowed_values(
            df,
            "education",
            VALID_EDUCATION_VALUES,
            "INVALID_EDUCATION"
        )
    )

    issues.extend(
        check_allowed_values(
            df,
            "marriage",
            VALID_MARRIAGE_VALUES,
            "INVALID_MARRIAGE"
        )
    )

    return issues


# ============================================================
# CHECK 7: REPAYMENT STATUS
# ============================================================

def check_repayment_status(df):
    """
    Validate repayment-status codes.

    Original values are preserved.

    Values <= 0 are not treated as invalid merely because
    they represent non-positive repayment states.
    """

    issues = []

    for column in REPAYMENT_COLUMNS:

        for _, row in df.iterrows():

            value = row[column]

            if pd.isna(value):
                continue

            if value not in VALID_REPAYMENT_VALUES:

                issues.append(
                    create_issue(
                        customer_id=row["customer_id"],
                        check_name="INVALID_REPAYMENT_STATUS",
                        column_name=column,
                        invalid_value=value,
                        reason=(
                            "Repayment status is outside "
                            "the accepted source values "
                            f"{VALID_REPAYMENT_VALUES}"
                        )
                    )
                )

    return issues


# ============================================================
# CHECK 8: PAYMENT AMOUNTS
# ============================================================

def check_payment_amounts(df):
    """
    Previous payment amounts must not be negative.
    """

    issues = []

    for column in PAYMENT_COLUMNS:

        for _, row in df.iterrows():

            value = row[column]

            if pd.isna(value):
                continue

            try:
                payment = float(value)

                if payment < 0:

                    issues.append(
                        create_issue(
                            customer_id=row["customer_id"],
                            check_name="NEGATIVE_PAYMENT_AMOUNT",
                            column_name=column,
                            invalid_value=value,
                            reason=(
                                "Previous payment amount "
                                "cannot be negative"
                            )
                        )
                    )

            except (TypeError, ValueError):

                issues.append(
                    create_issue(
                        customer_id=row["customer_id"],
                        check_name="INVALID_PAYMENT_TYPE",
                        column_name=column,
                        invalid_value=value,
                        reason="Payment amount must be numeric"
                    )
                )

    return issues


# ============================================================
# CHECK 9: BILL AMOUNTS
# ============================================================

def check_bill_amounts(df):
    """
    Validate that bill amounts are numeric.

    Negative bill amounts are NOT rejected because the
    source dataset may contain negative balances/credits.
    """

    issues = []

    for column in BILL_COLUMNS:

        for _, row in df.iterrows():

            value = row[column]

            if pd.isna(value):
                continue

            try:
                float(value)

            except (TypeError, ValueError):

                issues.append(
                    create_issue(
                        customer_id=row["customer_id"],
                        check_name="INVALID_BILL_AMOUNT",
                        column_name=column,
                        invalid_value=value,
                        reason="Bill amount must be numeric"
                    )
                )

    return issues


# ============================================================
# CHECK 10: DEFAULT INDICATOR
# ============================================================

def check_default_indicator(df):
    """
    Default-next-month indicator must be 0 or 1.
    """

    return check_allowed_values(
        df,
        "default_next_month",
        VALID_DEFAULT_VALUES,
        "INVALID_DEFAULT_INDICATOR"
    )


# ============================================================
# RUN ALL DATA QUALITY CHECKS
# ============================================================

def run_data_quality_checks(df):
    """
    Execute all reusable data-quality checks.

    Returns
    -------
    valid_df : pandas.DataFrame

    rejected_df : pandas.DataFrame
        Original rejected records plus rejection_reason.

    issues_df : pandas.DataFrame
        One row per data-quality issue.
    """

    logger.info(
        "Starting data-quality checks. Records=%d",
        len(df)
    )

    all_issues = []

    # --------------------------------------------------------
    # Execute reusable checks
    # --------------------------------------------------------

    all_issues.extend(
        check_missing_values(df)
    )

    all_issues.extend(
        check_duplicate_customer_ids(df)
    )

    all_issues.extend(
        check_customer_id(df)
    )

    all_issues.extend(
        check_age_range(df)
    )

    all_issues.extend(
        check_credit_limit(df)
    )

    all_issues.extend(
        check_demographic_values(df)
    )

    all_issues.extend(
        check_repayment_status(df)
    )

    all_issues.extend(
        check_bill_amounts(df)
    )

    all_issues.extend(
        check_payment_amounts(df)
    )

    all_issues.extend(
        check_default_indicator(df)
    )

    # --------------------------------------------------------
    # Convert issues into DataFrame
    # --------------------------------------------------------

    issues_df = pd.DataFrame(
        all_issues,
        columns=[
            "customer_id",
            "check_name",
            "column_name",
            "invalid_value",
            "reason"
        ]
    )

    # --------------------------------------------------------
    # No issues found
    # --------------------------------------------------------

    if issues_df.empty:

        valid_df = df.copy()

        rejected_df = df.iloc[0:0].copy()

        rejected_df["rejection_reason"] = pd.Series(
            dtype="object"
        )

        logger.info(
            "Data-quality checks completed. "
            "Valid=%d, Rejected=0, Issues=0",
            len(valid_df)
        )

        return valid_df, rejected_df, issues_df

    # --------------------------------------------------------
    # Identify rejected customer IDs
    # --------------------------------------------------------

    rejected_customer_ids = (
        issues_df["customer_id"]
        .dropna()
        .unique()
        .tolist()
    )

    # --------------------------------------------------------
    # Handle rows where customer_id itself is missing
    # --------------------------------------------------------

    missing_id_mask = df["customer_id"].isna()

    rejected_mask = (
        df["customer_id"].isin(rejected_customer_ids)
        | missing_id_mask
    )

    rejected_df = df[
        rejected_mask
    ].copy()

    valid_df = df[
        ~rejected_mask
    ].copy()

    # --------------------------------------------------------
    # Build readable rejection reasons
    # --------------------------------------------------------

    reason_map = (
        issues_df[
            issues_df["customer_id"].notna()
        ]
        .groupby("customer_id")["reason"]
        .apply(
            lambda values:
            " | ".join(dict.fromkeys(values))
        )
        .to_dict()
    )

    # rejected_df["rejection_reason"] = (
    #     rejected_df["customer_id"]
    #     .map(reason_map)
    # )
    rejected_df["rejection_reason"] = (
    rejected_df["customer_id"]
    .map(reason_map)
    .astype("object")
)

    rejected_df.loc[
        rejected_df["customer_id"].isna(),
        "rejection_reason"
    ] = "Missing customer_id"

    # --------------------------------------------------------
    # Logging
    # --------------------------------------------------------

    logger.info(
        "Data-quality checks completed. "
        "Valid=%d, Rejected=%d, Issues=%d",
        len(valid_df),
        len(rejected_df),
        len(issues_df)
    )

    return (
        valid_df.reset_index(drop=True),
        rejected_df.reset_index(drop=True),
        issues_df.reset_index(drop=True)
    )