
import pytest
from decimal import Decimal
from sqlalchemy import text

from src.db.connection import engine
from src.db.refresh_aggregates import refresh_aggregates


def query_one(sql, params=None):
    with engine.connect() as conn:
        return conn.execute(
            text(sql), params or {}
        ).mappings().one()


def query_all(sql, params=None):
    with engine.connect() as conn:
        return conn.execute(
            text(sql), params or {}
        ).mappings().all()


def assert_close(actual, expected, tolerance=Decimal("0.01")):
    """Compare SQL numeric values with rounding tolerance."""
    if actual is None or expected is None:
        assert actual is None and expected is None
        return

    assert abs(
        Decimal(str(actual)) - Decimal(str(expected))
    ) <= tolerance


# ============================================================
# TEST 1: PORTFOLIO SUMMARY
# ============================================================

def test_portfolio_summary():

    source = query_one("""
        SELECT
            COUNT(*) AS total_customers,
            SUM(cp.credit_limit) AS total_credit_exposure,
            AVG(cp.credit_limit) AS average_credit_limit,
            AVG(r.risk_score) AS average_risk_score,
            SUM(cp.default_next_month = 1)
                AS total_defaulted_customers,
            AVG(cp.default_next_month) * 100
                AS historical_default_rate
        FROM customers c
        JOIN credit_profiles cp
            ON c.customer_id = cp.customer_id
        JOIN customer_risk_scores r
            ON c.customer_id = r.customer_id
    """)

    aggregate = query_one("""
        SELECT *
        FROM agg_portfolio_summary
        WHERE summary_id = 1
    """)

    assert aggregate["total_customers"] == source["total_customers"]

    assert (
        aggregate["total_defaulted_customers"]
        == source["total_defaulted_customers"]
    )

    for column in [
        "total_credit_exposure",
        "average_credit_limit",
        "average_risk_score",
        "historical_default_rate"
    ]:
        assert_close(aggregate[column], source[column])


# ============================================================
# TEST 2: RISK DISTRIBUTION
# ============================================================

def test_risk_distribution():

    source_rows = query_all("""
        SELECT
            r.risk_band,
            COUNT(*) AS customer_count,
            SUM(cp.credit_limit) AS total_credit_exposure,
            SUM(cp.default_next_month = 1)
                AS defaulted_customers,
            AVG(r.risk_score) AS average_risk_score,
            AVG(cp.default_next_month) * 100
                AS historical_default_rate
        FROM customer_risk_scores r
        JOIN credit_profiles cp
            ON r.customer_id = cp.customer_id
        GROUP BY r.risk_band
    """)

    aggregate_rows = query_all("""
        SELECT *
        FROM agg_risk_distribution
    """)

    source = {
        row["risk_band"]: row
        for row in source_rows
    }

    aggregate = {
        row["risk_band"]: row
        for row in aggregate_rows
    }

    assert source.keys() == aggregate.keys()

    for band in source:

        expected = source[band]
        actual = aggregate[band]

        assert (
            actual["customer_count"]
            == expected["customer_count"]
        )

        assert (
            actual["defaulted_customers"]
            == expected["defaulted_customers"]
        )

        for column in [
            "total_credit_exposure",
            "average_risk_score",
            "historical_default_rate"
        ]:
            assert_close(actual[column], expected[column])

    total = sum(
        row["customer_count"]
        for row in aggregate_rows
    )

    customer_count = query_one("""
        SELECT COUNT(*) AS count
        FROM customers
    """)["count"]

    assert total == customer_count

    assert_close(
        sum(Decimal(str(row["percentage"]))
            for row in aggregate_rows),
        Decimal("100"),
        tolerance=Decimal("0.05")
    )


# ============================================================
# TEST 3: MONTHLY FINANCIALS
# ============================================================

def test_monthly_financials():

    source_rows = query_all("""
        SELECT
            b.month,
            COUNT(DISTINCT b.customer_id)
                AS customer_count,
            SUM(b.bill_amount) AS total_bill_amount,
            SUM(p.payment_amount) AS total_payment_amount,
            AVG(b.bill_amount) AS average_bill_amount,
            AVG(p.payment_amount) AS average_payment_amount
        FROM bills b
        JOIN payments p
            ON b.customer_id = p.customer_id
            AND b.month = p.month
        GROUP BY b.month
    """)

    aggregate_rows = query_all("""
        SELECT *
        FROM agg_monthly_financials
    """)

    source = {
        row["month"]: row
        for row in source_rows
    }

    aggregate = {
        row["month"]: row
        for row in aggregate_rows
    }

    assert len(source) == 6
    assert source.keys() == aggregate.keys()

    for month in source:

        expected = source[month]
        actual = aggregate[month]

        assert (
            actual["customer_count"]
            == expected["customer_count"]
        )

        for column in [
            "total_bill_amount",
            "total_payment_amount",
            "average_bill_amount",
            "average_payment_amount"
        ]:
            assert_close(actual[column], expected[column])


# ============================================================
# TEST 4: SEGMENT RISK
# ============================================================

def test_segment_risk():

    source_rows = query_all("""
        SELECT
            COALESCE(c.age_group, 'UNKNOWN')
                AS segment_value,
            COUNT(*) AS customer_count,
            SUM(r.risk_band = 'HIGH')
                AS high_risk_customers,
            SUM(cp.credit_limit)
                AS total_credit_exposure
        FROM customers c
        JOIN credit_profiles cp
            ON c.customer_id = cp.customer_id
        JOIN customer_risk_scores r
            ON c.customer_id = r.customer_id
        GROUP BY COALESCE(c.age_group, 'UNKNOWN')
    """)

    aggregate_rows = query_all("""
        SELECT *
        FROM agg_segment_risk
        WHERE segment_type = 'AGE_GROUP'
    """)

    source = {
        row["segment_value"]: row
        for row in source_rows
    }

    aggregate = {
        row["segment_value"]: row
        for row in aggregate_rows
    }

    assert source.keys() == aggregate.keys()

    for segment in source:

        expected = source[segment]
        actual = aggregate[segment]

        assert (
            actual["customer_count"]
            == expected["customer_count"]
        )

        assert (
            actual["high_risk_customers"]
            == expected["high_risk_customers"]
        )

        assert_close(
            actual["total_credit_exposure"],
            expected["total_credit_exposure"]
        )


# ============================================================
# TEST 5: REFRESH REPEATABILITY
# ============================================================

def get_reporting_snapshot():

    tables = {
        "portfolio": (
            "SELECT summary_id, total_customers, "
            "total_credit_exposure, average_credit_limit, "
            "average_risk_score, total_defaulted_customers, "
            "historical_default_rate "
            "FROM agg_portfolio_summary ORDER BY summary_id"
        ),
        "risk": (
            "SELECT risk_band, customer_count, percentage, "
            "average_risk_score, total_credit_exposure, "
            "defaulted_customers, historical_default_rate "
            "FROM agg_risk_distribution ORDER BY risk_band"
        ),
        "monthly": (
            "SELECT month, customer_count, total_bill_amount, "
            "total_payment_amount, average_bill_amount, "
            "average_payment_amount, payment_to_bill_ratio "
            "FROM agg_monthly_financials ORDER BY month"
        ),
        "segment": (
            "SELECT segment_type, segment_value, "
            "customer_count, high_risk_customers, "
            "high_risk_percentage, average_risk_score, "
            "average_delayed_months, historical_default_rate, "
            "total_credit_exposure "
            "FROM agg_segment_risk "
            "ORDER BY segment_type, segment_value"
        )
    }

    return {
        name: [tuple(row) for row in query_all(sql)]
        for name, sql in tables.items()
    }


def test_refresh_repeatability():

    refresh_aggregates()
    first = get_reporting_snapshot()

    refresh_aggregates()
    second = get_reporting_snapshot()

    assert first == second


# ============================================================
# TEST 6: TRANSACTION ROLLBACK
#
# Simulate a failed refresh using the aggregate tables.
# Do not modify the source tables.
# ============================================================

def test_transaction_rollback():

    before = get_reporting_snapshot()

    with pytest.raises(RuntimeError):

        with engine.begin() as conn:

            conn.execute(text("""
                DELETE FROM agg_portfolio_summary
            """))

            conn.execute(text("""
                DELETE FROM agg_risk_distribution
            """))

            raise RuntimeError(
                "Simulated aggregate refresh failure"
            )

    after = get_reporting_snapshot()

    assert before == after
