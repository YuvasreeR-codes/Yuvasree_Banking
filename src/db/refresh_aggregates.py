
import logging
from sqlalchemy import text
from src.db.connection import engine

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s"
)

logger = logging.getLogger(__name__)


def refresh_aggregates():
    """
    Refresh all reporting aggregate tables.

    All DELETE and INSERT operations execute in one
    database transaction. On failure, changes roll back.
    """

    logger.info("Starting aggregate refresh")

    try:
        with engine.begin() as conn:

            # ---------------------------------------
            # Validate source data before refresh
            # ---------------------------------------

            source = conn.execute(text("""
                SELECT
                    (SELECT COUNT(*) FROM customers)
                        AS customer_count,
                    (SELECT COUNT(*) FROM credit_profiles)
                        AS profile_count,
                    (SELECT COUNT(*) FROM customer_risk_scores)
                        AS risk_count,
                    (SELECT COUNT(*) FROM bills)
                        AS bill_count,
                    (SELECT COUNT(*) FROM payments)
                        AS payment_count
            """)).mappings().one()

            logger.info("Source counts: %s", dict(source))

            if source["customer_count"] == 0:
                raise ValueError("No customers available")

            if not (
                source["customer_count"]
                == source["profile_count"]
                == source["risk_count"]
            ):
                raise ValueError(
                    "Customer, credit profile and risk "
                    "score counts do not match"
                )

            if (
                source["bill_count"] == 0
                or source["payment_count"] == 0
            ):
                raise ValueError(
                    "Bill or payment records are missing"
                )

            # ---------------------------------------
            # 1. Portfolio Summary
            # ---------------------------------------

            conn.execute(text(
                "DELETE FROM agg_portfolio_summary"
            ))

            conn.execute(text("""
                INSERT INTO agg_portfolio_summary (
                    summary_id,
                    total_customers,
                    total_credit_exposure,
                    average_credit_limit,
                    average_risk_score,
                    total_defaulted_customers,
                    historical_default_rate,
                    last_refreshed_at
                )
                SELECT
                    1,
                    COUNT(*),
                    COALESCE(SUM(cp.credit_limit), 0),
                    AVG(cp.credit_limit),
                    AVG(r.risk_score),
                    COALESCE(
                        SUM(cp.default_next_month = 1), 0
                    ),
                    AVG(cp.default_next_month) * 100,
                    CURRENT_TIMESTAMP
                FROM customers c
                JOIN credit_profiles cp
                    ON c.customer_id = cp.customer_id
                JOIN customer_risk_scores r
                    ON c.customer_id = r.customer_id
            """))

            logger.info("Portfolio summary refreshed")

            # ---------------------------------------
            # 2. Risk Distribution
            # ---------------------------------------

            conn.execute(text(
                "DELETE FROM agg_risk_distribution"
            ))

            conn.execute(text("""
                INSERT INTO agg_risk_distribution (
                    risk_band,
                    customer_count,
                    percentage,
                    average_risk_score,
                    total_credit_exposure,
                    defaulted_customers,
                    historical_default_rate,
                    last_refreshed_at
                )
                SELECT
                    r.risk_band,
                    COUNT(*),
                    COUNT(*) * 100.0 /
                        NULLIF(
                            (SELECT COUNT(*)
                             FROM customer_risk_scores), 0
                        ),
                    AVG(r.risk_score),
                    COALESCE(SUM(cp.credit_limit), 0),
                    COALESCE(
                        SUM(cp.default_next_month = 1), 0
                    ),
                    AVG(cp.default_next_month) * 100,
                    CURRENT_TIMESTAMP
                FROM customer_risk_scores r
                JOIN credit_profiles cp
                    ON r.customer_id = cp.customer_id
                GROUP BY r.risk_band
            """))

            logger.info("Risk distribution refreshed")

            # ---------------------------------------
            # 3. Monthly Financial Trends
            # ---------------------------------------

            conn.execute(text(
                "DELETE FROM agg_monthly_financials"
            ))

            conn.execute(text("""
                INSERT INTO agg_monthly_financials (
                    month,
                    customer_count,
                    total_bill_amount,
                    total_payment_amount,
                    average_bill_amount,
                    average_payment_amount,
                    payment_to_bill_ratio,
                    last_refreshed_at
                )
                SELECT
                    b.month,
                    COUNT(DISTINCT b.customer_id),
                    COALESCE(SUM(b.bill_amount), 0),
                    COALESCE(SUM(p.payment_amount), 0),
                    AVG(b.bill_amount),
                    AVG(p.payment_amount),
                    SUM(p.payment_amount) /
                        NULLIF(
                            SUM(
                                CASE
                                    WHEN b.bill_amount > 0
                                    THEN b.bill_amount
                                    ELSE 0
                                END
                            ), 0
                        ),
                    CURRENT_TIMESTAMP
                FROM bills b
                JOIN payments p
                    ON b.customer_id = p.customer_id
                    AND b.month = p.month
                GROUP BY b.month
            """))

            logger.info("Monthly financials refreshed")

            # ---------------------------------------
            # 4. Customer Segment Risk
            # ---------------------------------------

            conn.execute(text(
                "DELETE FROM agg_segment_risk"
            ))

            conn.execute(text("""
                INSERT INTO agg_segment_risk (
                    segment_type,
                    segment_value,
                    customer_count,
                    high_risk_customers,
                    high_risk_percentage,
                    average_risk_score,
                    average_delayed_months,
                    historical_default_rate,
                    total_credit_exposure,
                    last_refreshed_at
                )
                SELECT
                    s.segment_type,
                    s.segment_value,
                    COUNT(*),
                    SUM(r.risk_band = 'HIGH'),
                    AVG(r.risk_band = 'HIGH') * 100,
                    AVG(r.risk_score),
                    AVG(cp.months_with_delay),
                    AVG(cp.default_next_month) * 100,
                    COALESCE(SUM(cp.credit_limit), 0),
                    CURRENT_TIMESTAMP
                FROM (
                    SELECT customer_id,
                           'AGE_GROUP' AS segment_type,
                           COALESCE(age_group, 'UNKNOWN')
                               AS segment_value
                    FROM customers

                    UNION ALL

                    SELECT customer_id,
                           'GENDER',
                           COALESCE(gender_label, 'UNKNOWN')
                    FROM customers

                    UNION ALL

                    SELECT customer_id,
                           'EDUCATION',
                           COALESCE(education_label, 'UNKNOWN')
                    FROM customers

                    UNION ALL

                    SELECT customer_id,
                           'MARITAL_STATUS',
                           COALESCE(marriage_label, 'UNKNOWN')
                    FROM customers
                ) s
                JOIN credit_profiles cp
                    ON s.customer_id = cp.customer_id
                JOIN customer_risk_scores r
                    ON s.customer_id = r.customer_id
                GROUP BY
                    s.segment_type,
                    s.segment_value
            """))

            logger.info("Segment risk refreshed")

            # ---------------------------------------
            # Validate aggregate results
            # ---------------------------------------

            portfolio_count = conn.execute(text("""
                SELECT total_customers
                FROM agg_portfolio_summary
                WHERE summary_id = 1
            """)).scalar_one()

            risk_total = conn.execute(text("""
                SELECT COALESCE(SUM(customer_count), 0)
                FROM agg_risk_distribution
            """)).scalar_one()

            segment_totals = conn.execute(text("""
                SELECT segment_type, SUM(customer_count)
                FROM agg_segment_risk
                GROUP BY segment_type
            """)).all()

            monthly_count = conn.execute(text("""
                SELECT COUNT(*)
                FROM agg_monthly_financials
            """)).scalar_one()

            expected = source["customer_count"]

            if portfolio_count != expected:
                raise ValueError(
                    "Portfolio aggregate count mismatch"
                )

            if risk_total != expected:
                raise ValueError(
                    "Risk aggregate count mismatch"
                )

            if monthly_count != 6:
                raise ValueError(
                    "Expected six monthly aggregate rows, "
                    f"found {monthly_count}"
                )

            if len(segment_totals) != 4:
                raise ValueError(
                    "Expected four segment types"
                )

            for segment_type, count in segment_totals:
                if count != expected:
                    raise ValueError(
                        f"Segment count mismatch: "
                        f"{segment_type}"
                    )

            logger.info(
                "Aggregate validation passed: %s customers",
                expected
            )

        logger.info(
            "Aggregate refresh committed successfully"
        )

    except Exception:
        logger.exception("Aggregate refresh failed")
        raise


if __name__ == "__main__":
    refresh_aggregates()
