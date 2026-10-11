
"""
Rule-based credit risk scoring engine.

Uses configurable rules from risk_config.py.

This module does not modify the database.
"""

import logging

import pandas as pd

from src.risk.risk_config import (
    RISK_RULES,
    RISK_BANDS,
    RISK_RULE_VERSION,
    MISSING_VALUE_POLICY,
)


logger = logging.getLogger(__name__)


REQUIRED_COLUMNS = [
    "customer_id",
    "max_repayment_delay",
    "months_with_delay",
    "latest_credit_utilization",
    "payment_to_bill_ratio",
    "total_bill_amount",
]


# ============================================================
# 1. SCORE REPAYMENT DELAY
# ============================================================

def score_repayment_delay(value):
    """
    Higher repayment delay means higher risk.

    <= 0 months: 0 points
    1 month:     10 points
    >= 2 months: 25 points
    """

    rule = RISK_RULES["max_repayment_delay"]

    if value >= rule["high_threshold"]:
        return rule["high_points"]

    if value >= rule["medium_threshold"]:
        return rule["medium_points"]

    return 0


# ============================================================
# 2. SCORE MONTHS WITH DELAY
# ============================================================

def score_months_with_delay(value):
    """
    More delayed months means higher risk.

    0 months:  0 points
    1-2:      10 points
    >= 3:     25 points
    """

    rule = RISK_RULES["months_with_delay"]

    if value >= rule["high_threshold"]:
        return rule["high_points"]

    if value >= rule["medium_threshold"]:
        return rule["medium_points"]

    return 0


# ============================================================
# 3. SCORE CREDIT UTILIZATION
# ============================================================

def score_credit_utilization(value):
    """
    Higher credit utilization means higher risk.

    Below 30%: 0 points
    30%-below 80%: 10 points
    80% or above: 25 points
    """

    rule = RISK_RULES["latest_credit_utilization"]

    if value >= rule["high_threshold"]:
        return rule["high_points"]

    if value >= rule["medium_threshold"]:
        return rule["medium_points"]

    return 0


# ============================================================
# 4. SCORE PAYMENT-TO-BILL RATIO
# ============================================================

def score_payment_ratio(payment_ratio, total_bill_amount):
    """
    Calculate payment-related risk.

    If the net total bill is zero or negative,
    assign zero payment-risk points.

    Otherwise, use the configured payment ratio thresholds.
    """

    if total_bill_amount <= 0:
        return 0

    rule = RISK_RULES["payment_to_bill_ratio"]

    if payment_ratio < rule["medium_threshold"]:
        return rule["high_points"]

    if payment_ratio < rule["high_threshold"]:
        return rule["medium_points"]

    return 0


# ============================================================
# 5. ASSIGN RISK BAND
# ============================================================

def assign_risk_band(score):
    """
    Convert the total risk score into a risk band.
    """

    for band, limits in RISK_BANDS.items():

        if (
            limits["min_score"]
            <= score
            <= limits["max_score"]
        ):
            return band

    raise ValueError(
        f"Risk score outside configured bands: {score}"
    )

def normalize_risk_indicators(indicators):
    """
    Normalize financial indicators before scoring.

    Negative utilization represents a credit balance
    and is treated as zero utilization.
    """

    normalized = indicators.copy()

    utilization = normalized["latest_credit_utilization"]

    if pd.notna(utilization) and utilization < 0:
        normalized["latest_credit_utilization"] = 0.0

    return normalized
# ============================================================
# 6. CALCULATE RISK FOR ONE CUSTOMER
# ============================================================


def calculate_customer_risk(customer):
    """
    Calculate a customer's rule-based credit risk score.

    Source data quality is validated in the ETL pipeline.
    """

    customer_id = customer["customer_id"]

    indicators = {
        column: customer[column]
        for column in REQUIRED_COLUMNS
        if column != "customer_id"
    }

    # Normalize negative credit utilization to zero.
    indicators = normalize_risk_indicators(indicators)

    # Calculate repayment-related scores.
    delay_score = score_repayment_delay(
        indicators["max_repayment_delay"]
    )

    frequency_score = score_months_with_delay(
        indicators["months_with_delay"]
    )

    utilization_score = score_credit_utilization(
        indicators["latest_credit_utilization"]
    )

    # Special handling for zero or negative net bill totals.
    total_bill = indicators["total_bill_amount"]

    if total_bill <= 0:
        payment_score = 0
        payment_reason = (
            "No positive net bill balance; "
            "payment-ratio risk points set to zero"
        )
    else:
        payment_score = score_payment_ratio(
            indicators["payment_to_bill_ratio"],
            total_bill
        )
        payment_reason = None

    # Calculate overall risk score.
    total_score = (
        delay_score
        + frequency_score
        + utilization_score
        + payment_score
    )

    risk_band = assign_risk_band(total_score)

    # Generate explainable reasons.
    reasons = []

    if delay_score > 0:
        reasons.append("History of repayment delays")

    if frequency_score > 0:
        reasons.append("Repeated delayed repayments")

    if utilization_score > 0:
        reasons.append("Elevated credit utilization")

    if payment_score > 0:
        reasons.append("Low payment coverage")

    if payment_reason:
        reasons.append(payment_reason)

    if not reasons:
        reasons.append(
            "No elevated risk indicators under current rules"
        )

    return {
        "customer_id": customer_id,
        "risk_score": int(total_score),
        "risk_band": risk_band,
        "delay_score": int(delay_score),
        "delay_frequency_score": int(frequency_score),
        "utilization_score": int(utilization_score),
        "payment_score": int(payment_score),
        "rule_version": RISK_RULE_VERSION,
        "risk_reason": "; ".join(reasons),
    }


# ============================================================
# 7. CALCULATE RISK FOR MULTIPLE CUSTOMERS
# ============================================================

def calculate_risk_scores(credit_df):
    """
    Apply risk scoring to a DataFrame of credit profiles.

    Returns one risk result per customer.
    """

    missing_columns = [
        column
        for column in REQUIRED_COLUMNS
        if column not in credit_df.columns
    ]

    if missing_columns:
        raise ValueError(
            "Missing required columns: "
            + ", ".join(missing_columns)
        )

    if credit_df["customer_id"].isna().any():
        raise ValueError(
            "Customer ID cannot be null"
        )

    if credit_df["customer_id"].duplicated().any():
        raise ValueError(
            "Duplicate customer IDs in risk input"
        )

    results = [
        calculate_customer_risk(row)
        for _, row in credit_df.iterrows()
    ]

    result_columns = [
        "customer_id",
        "risk_score",
        "risk_band",
        "delay_score",
        "delay_frequency_score",
        "utilization_score",
        "payment_score",
        "rule_version",
        "risk_reason",
    ]

    result_df = pd.DataFrame(
        results,
        columns=result_columns
    )

    logger.info(
        "Risk scoring completed for %d customers",
        len(result_df)
    )

    return result_df
