
"""
Database operations for customer credit risk scores.

Responsibilities:
1. Fetch customer credit profiles.
2. Calculate risk scores.
3. Save scores using batch upsert.
4. Return processing statistics.
"""

import logging

import pandas as pd
from sqlalchemy import text

from config import BATCH_SIZE
from src.db.connection import get_engine
from src.risk.risk_engine import calculate_risk_scores


logger = logging.getLogger(__name__)


# ============================================================
# 1. FETCH CREDIT PROFILES
# ============================================================


def fetch_credit_profiles():
    """
    Fetch financial indicators required for risk scoring.

    Includes total_bill_amount to handle customers
    with zero or negative net bill balances.
    """

    query = text("""
        SELECT
            customer_id,
            max_repayment_delay,
            months_with_delay,
            latest_credit_utilization,
            payment_to_bill_ratio,
            total_bill_amount
        FROM credit_profiles
        ORDER BY customer_id
    """)

    with get_engine().connect() as connection:
        df = pd.read_sql_query(
            query,
            connection
        )

    logger.info(
        "Fetched %d credit profiles",
        len(df)
    )

    return df


# ============================================================
# 2. SPLIT DATA INTO BATCHES
# ============================================================

def split_dataframe(df, batch_size=BATCH_SIZE):
    """
    Yield DataFrame batches.
    """

    if batch_size <= 0:
        raise ValueError(
            "Batch size must be greater than zero"
        )

    for start in range(0, len(df), batch_size):

        yield df.iloc[
            start:start + batch_size
        ].copy()


# ============================================================
# 3. CONVERT DATAFRAME TO SQL RECORDS
# ============================================================

def dataframe_to_records(df):
    """
    Convert pandas values into SQL-compatible values.

    Missing values become NULL.
    """

    records = []

    for row in df.to_dict(orient="records"):

        clean_record = {}

        for column, value in row.items():

            if pd.isna(value):
                clean_record[column] = None

            elif hasattr(value, "item"):
                clean_record[column] = value.item()

            else:
                clean_record[column] = value

        records.append(clean_record)

    return records


# ============================================================
# 4. UPSERT RISK SCORES
# ============================================================

UPSERT_RISK_QUERY = text("""
    INSERT INTO customer_risk_scores (
        customer_id,
        risk_score,
        risk_band,
        delay_score,
        delay_frequency_score,
        utilization_score,
        payment_score,
        rule_version,
        risk_reason
    )
    VALUES (
        :customer_id,
        :risk_score,
        :risk_band,
        :delay_score,
        :delay_frequency_score,
        :utilization_score,
        :payment_score,
        :rule_version,
        :risk_reason
    )
    ON DUPLICATE KEY UPDATE
        risk_score = VALUES(risk_score),
        risk_band = VALUES(risk_band),
        delay_score = VALUES(delay_score),
        delay_frequency_score = VALUES(delay_frequency_score),
        utilization_score = VALUES(utilization_score),
        payment_score = VALUES(payment_score),
        rule_version = VALUES(rule_version),
        risk_reason = VALUES(risk_reason),
        updated_at = CURRENT_TIMESTAMP
""")


def save_risk_scores(
    risk_df,
    batch_size=BATCH_SIZE
):
    """
    Insert or update customer risk scores in batches.

    Each batch is committed as one transaction.

    If a batch fails, its changes are rolled back
    and the exception is propagated.
    """

    if batch_size <= 0:
        raise ValueError(
            "Batch size must be greater than zero"
        )

    if risk_df.empty:
        logger.info(
            "No risk scores to save"
        )
        return 0

    if risk_df["customer_id"].duplicated().any():
        raise ValueError(
            "Duplicate customer IDs in risk results"
        )

    engine = get_engine()

    processed_count = 0

    for batch_number, batch in enumerate(
        split_dataframe(risk_df, batch_size),
        start=1
    ):

        records = dataframe_to_records(batch)

        try:

            with engine.begin() as connection:

                connection.execute(
                    UPSERT_RISK_QUERY,
                    records
                )

            processed_count += len(records)

            logger.info(
                "Risk batch %d committed: %d records",
                batch_number,
                len(records)
            )

        except Exception:

            logger.exception(
                "Risk batch %d failed",
                batch_number
            )

            raise

    return processed_count


# ============================================================
# 5. MAIN RISK SCORING PIPELINE
# ============================================================

def run_risk_scoring(
    batch_size=BATCH_SIZE
):
    """
    Fetch, calculate, and persist risk scores.

    Returns a summary dictionary.
    """

    logger.info(
        "Starting credit risk scoring"
    )

    # Step 1: Fetch financial indicators.
    credit_df = fetch_credit_profiles()

    # Step 2: Calculate risk scores.
    risk_df = calculate_risk_scores(
        credit_df
    )

    # Step 3: Save results in MySQL.
    processed_count = save_risk_scores(
        risk_df,
        batch_size=batch_size
    )

    # Step 4: Build summary.
    band_counts = (
        risk_df["risk_band"]
        .value_counts()
        .to_dict()
    )

    summary = {
        "total_customers": len(credit_df),
        "processed_count": processed_count,
        "low_risk": band_counts.get("LOW", 0),
        "medium_risk": band_counts.get("MEDIUM", 0),
        "high_risk": band_counts.get("HIGH", 0),
        "unclassified": band_counts.get(
            "UNCLASSIFIED", 0
        ),
    }

    logger.info(
        "Risk scoring completed: %s",
        summary
    )

    return summary


# ============================================================
# 6. DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":

    result = run_risk_scoring(
        batch_size=BATCH_SIZE
    )

    print("\nCredit Risk Scoring Summary")

    for key, value in result.items():
        print(f"{key}: {value}")
