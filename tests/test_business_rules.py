
import pandas as pd
import pytest

from src.risk import risk_engine as engine
from src.risk.risk_config import (
    RISK_RULES,
    RISK_BANDS,
    RISK_RULE_VERSION,
)


# ---------------------------------------------------------
# Test Data
# ---------------------------------------------------------

def make_customer(**overrides):

    customer = {
        "customer_id": 1,
        "max_repayment_delay": 0,
        "months_with_delay": 0,
        "latest_credit_utilization": 0.10,
        "payment_to_bill_ratio": 1.0,
        "total_bill_amount": 10000,
    }

    customer.update(overrides)
    return customer


# ---------------------------------------------------------
# 1. Configuration Tests
# ---------------------------------------------------------

def test_risk_configuration():

    required_rules = [
        "max_repayment_delay",
        "months_with_delay",
        "latest_credit_utilization",
        "payment_to_bill_ratio",
    ]

    for rule_name in required_rules:

        assert rule_name in RISK_RULES

        rule = RISK_RULES[rule_name]

        assert rule["medium_threshold"] < rule["high_threshold"]
        assert rule["medium_points"] <= rule["high_points"]
        assert rule["high_points"] <= rule["weight"]


def test_risk_band_configuration():

    assert RISK_BANDS["LOW"]["min_score"] == 0
    assert RISK_BANDS["LOW"]["max_score"] == 29

    assert RISK_BANDS["MEDIUM"]["min_score"] == 30
    assert RISK_BANDS["MEDIUM"]["max_score"] == 59

    assert RISK_BANDS["HIGH"]["min_score"] == 60
    assert RISK_BANDS["HIGH"]["max_score"] == 100


# ---------------------------------------------------------
# 2. Repayment Delay Tests
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "delay,expected",
    [
        (-1, 0),
        (0, 0),
        (1, 10),
        (2, 25),
        (5, 25),
    ]
)
def test_repayment_delay(delay, expected):

    assert engine.score_repayment_delay(delay) == expected


# ---------------------------------------------------------
# 3. Months With Delay Tests
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "months,expected",
    [
        (0, 0),
        (1, 10),
        (2, 10),
        (3, 25),
        (6, 25),
    ]
)
def test_months_with_delay(months, expected):

    assert engine.score_months_with_delay(months) == expected


# ---------------------------------------------------------
# 4. Credit Utilization Tests
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "utilization,expected",
    [
        (0.0, 0),
        (0.29, 0),
        (0.30, 10),
        (0.79, 10),
        (0.80, 25),
        (1.0, 25),
    ]
)
def test_credit_utilization(utilization, expected):

    assert engine.score_credit_utilization(
        utilization
    ) == expected


def test_negative_credit_utilization_normalization():

    customer = make_customer(
        latest_credit_utilization=-0.5
    )

    result = engine.calculate_customer_risk(customer)

    assert result["utilization_score"] == 0
    assert result["risk_score"] == 0
    assert result["risk_band"] == "LOW"


# ---------------------------------------------------------
# 5. Payment Ratio Tests
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "ratio,bill,expected",
    [
        (0.10, 10000, 25),
        (0.29, 10000, 25),
        (0.30, 10000, 10),
        (0.79, 10000, 10),
        (0.80, 10000, 0),
        (1.00, 10000, 0),
        (0.10, 0, 0),
        (0.10, -500, 0),
    ]
)
def test_payment_ratio(ratio, bill, expected):

    assert engine.score_payment_ratio(
        ratio, bill
    ) == expected


# ---------------------------------------------------------
# 6. Risk Band Classification
# ---------------------------------------------------------

@pytest.mark.parametrize(
    "score,expected",
    [
        (0, "LOW"),
        (29, "LOW"),
        (30, "MEDIUM"),
        (59, "MEDIUM"),
        (60, "HIGH"),
        (100, "HIGH"),
    ]
)
def test_risk_band(score, expected):

    assert engine.assign_risk_band(score) == expected


@pytest.mark.parametrize("score", [-1, 101, 150])
def test_invalid_risk_band(score):

    with pytest.raises(ValueError):
        engine.assign_risk_band(score)


# ---------------------------------------------------------
# 7. Complete Customer Scoring
# ---------------------------------------------------------

def test_low_risk_customer():

    result = engine.calculate_customer_risk(
        make_customer()
    )

    assert result["risk_score"] == 0
    assert result["risk_band"] == "LOW"
    assert result["rule_version"] == RISK_RULE_VERSION


def test_medium_risk_customer():

    customer = make_customer(
        max_repayment_delay=1,
        months_with_delay=1,
        latest_credit_utilization=0.40,
        payment_to_bill_ratio=1.0
    )

    result = engine.calculate_customer_risk(customer)

    assert result["risk_score"] == 30
    assert result["risk_band"] == "MEDIUM"


def test_high_risk_customer():

    customer = make_customer(
        max_repayment_delay=2,
        months_with_delay=3,
        latest_credit_utilization=0.90,
        payment_to_bill_ratio=0.10
    )

    result = engine.calculate_customer_risk(customer)

    assert result["risk_score"] == 100
    assert result["risk_band"] == "HIGH"


def test_score_components_add_up():

    customer = make_customer(
        max_repayment_delay=2,
        months_with_delay=1,
        latest_credit_utilization=0.50,
        payment_to_bill_ratio=0.20
    )

    result = engine.calculate_customer_risk(customer)

    total = (
        result["delay_score"]
        + result["delay_frequency_score"]
        + result["utilization_score"]
        + result["payment_score"]
    )

    assert result["risk_score"] == total
    assert total == 70


def test_scoring_is_deterministic():

    customer = make_customer(
        max_repayment_delay=2,
        months_with_delay=3
    )

    first = engine.calculate_customer_risk(customer)
    second = engine.calculate_customer_risk(customer)

    assert first == second


# ---------------------------------------------------------
# 8. Zero and Negative Bill Handling
# ---------------------------------------------------------

@pytest.mark.parametrize("bill", [0, -1000])
def test_non_positive_bill(bill):

    customer = make_customer(
        total_bill_amount=bill,
        payment_to_bill_ratio=0.10
    )

    result = engine.calculate_customer_risk(customer)

    assert result["payment_score"] == 0
    assert "No positive net bill balance" in result["risk_reason"]


# ---------------------------------------------------------
# 9. Explainability Tests
# ---------------------------------------------------------

def test_risk_reasons():

    customer = make_customer(
        max_repayment_delay=2,
        months_with_delay=3,
        latest_credit_utilization=0.90,
        payment_to_bill_ratio=0.10
    )

    result = engine.calculate_customer_risk(customer)

    assert "History of repayment delays" in result["risk_reason"]
    assert "Repeated delayed repayments" in result["risk_reason"]
    assert "Elevated credit utilization" in result["risk_reason"]
    assert "Low payment coverage" in result["risk_reason"]


# ---------------------------------------------------------
# 10. DataFrame Validation
# ---------------------------------------------------------

def test_missing_required_column():

    df = pd.DataFrame([
        make_customer()
    ]).drop(columns=["months_with_delay"])

    with pytest.raises(
        ValueError,
        match="Missing required columns"
    ):
        engine.calculate_risk_scores(df)


def test_null_customer_id():

    df = pd.DataFrame([
        make_customer(customer_id=None)
    ])

    with pytest.raises(
        ValueError,
        match="Customer ID cannot be null"
    ):
        engine.calculate_risk_scores(df)


def test_duplicate_customer_ids():

    df = pd.DataFrame([
        make_customer(customer_id=1),
        make_customer(customer_id=1)
    ])

    with pytest.raises(
        ValueError,
        match="Duplicate customer IDs"
    ):
        engine.calculate_risk_scores(df)


def test_multiple_customers():

    df = pd.DataFrame([
        make_customer(customer_id=1),
        make_customer(
            customer_id=2,
            max_repayment_delay=2,
            months_with_delay=3,
            latest_credit_utilization=0.90,
            payment_to_bill_ratio=0.10
        )
    ])

    result = engine.calculate_risk_scores(df)

    assert len(result) == 2
    assert result["customer_id"].is_unique
    assert set(result["risk_band"]) == {"LOW", "HIGH"}


def test_empty_dataframe():

    df = pd.DataFrame(columns=engine.REQUIRED_COLUMNS)

    result = engine.calculate_risk_scores(df)

    assert result.empty
    assert list(result.columns) == [
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


# ---------------------------------------------------------
# 11. Configurability Test
# ---------------------------------------------------------

def test_scoring_uses_configured_thresholds(monkeypatch):

    custom_rules = {
        key: value.copy()
        for key, value in engine.RISK_RULES.items()
    }

    custom_rules["max_repayment_delay"][
        "high_threshold"
    ] = 5

    monkeypatch.setattr(
        engine,
        "RISK_RULES",
        custom_rules
    )

    # Under the custom configuration, 2 months
    # should now receive medium points, not high.
    assert engine.score_repayment_delay(2) == 10

    # At the new high threshold, high points apply.
    assert engine.score_repayment_delay(5) == 25
