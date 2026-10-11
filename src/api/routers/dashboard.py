
import logging

from fastapi import APIRouter, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from typing import Literal

from src.db.connection import get_engine
from src.api.schemas.dashboard import PortfolioSummaryResponse,RiskDistributionResponse,MonthlyFinancialResponse,SegmentRiskResponse

from fastapi import Depends
from src.api.security import require_analyst_or_admin
# ---------------------------------------------------------
# Router configuration
# ---------------------------------------------------------

router = APIRouter(
    prefix="/api/dashboard",
    tags=["Dashboard"],
    dependencies=[
        Depends(require_analyst_or_admin)
    ]
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Portfolio Summary API
# ---------------------------------------------------------

@router.get(
    "/portfolio",
    response_model=PortfolioSummaryResponse
)
def get_portfolio_summary():

    logger.info("Portfolio summary requested")

    query = text("""
        SELECT
            summary_id,
            total_customers,
            total_credit_exposure,
            average_credit_limit,
            average_risk_score,
            total_defaulted_customers,
            historical_default_rate,
            last_refreshed_at
        FROM agg_portfolio_summary
        ORDER BY summary_id
        LIMIT 1
    """)

    try:
        engine = get_engine()

        with engine.connect() as connection:
            result = connection.execute(query)
            row = result.mappings().first()

        if row is None:
            logger.warning(
                "Portfolio summary aggregate is empty"
            )

            raise HTTPException(
                status_code=404,
                detail="Portfolio summary data not found"
            )

        return PortfolioSummaryResponse.model_validate(
            dict(row)
        )

    except SQLAlchemyError:
        logger.exception(
            "Database error while fetching portfolio summary"
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# Risk Distribution API
# ---------------------------------------------------------

@router.get(
    "/risk-distribution",
    response_model=list[RiskDistributionResponse]
)
def get_risk_distribution():

    logger.info("Risk distribution requested")

    query = text("""
        SELECT
            risk_band,
            customer_count,
            percentage,
            average_risk_score,
            total_credit_exposure,
            defaulted_customers,
            historical_default_rate,
            last_refreshed_at
        FROM agg_risk_distribution
        ORDER BY
            CASE risk_band
                WHEN 'LOW' THEN 1
                WHEN 'MEDIUM' THEN 2
                WHEN 'HIGH' THEN 3
                ELSE 4
            END,
            risk_band
    """)

    try:
        engine = get_engine()

        with engine.connect() as connection:
            result = connection.execute(query)
            rows = result.mappings().all()

        if not rows:
            logger.warning(
                "Risk distribution aggregate is empty"
            )

            raise HTTPException(
                status_code=404,
                detail="Risk distribution data not found"
            )

        return [
            RiskDistributionResponse.model_validate(
                dict(row)
            )
            for row in rows
        ]

    except SQLAlchemyError:
        logger.exception(
            "Database error while fetching risk distribution"
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )



# ---------------------------------------------------------
# Monthly Financial Trends API
# ---------------------------------------------------------

@router.get(
    "/monthly-financials",
    response_model=list[MonthlyFinancialResponse]
)
def get_monthly_financials(
    month: str | None = None,
    sort_by: Literal[
        "month",
        "customer_count",
        "total_bill_amount",
        "total_payment_amount",
        "payment_to_bill_ratio"
    ] = "month",
    sort_order: Literal["asc", "desc"] = "asc"
):

    logger.info("Monthly financial trends requested")

    allowed_sort_columns = {
        "month",
        "customer_count",
        "total_bill_amount",
        "total_payment_amount",
        "payment_to_bill_ratio"
    }

    if sort_by not in allowed_sort_columns:
        raise HTTPException(
            status_code=400,
            detail="Invalid sorting column"
        )

    query = """
        SELECT
            month,
            customer_count,
            total_bill_amount,
            total_payment_amount,
            average_bill_amount,
            average_payment_amount,
            payment_to_bill_ratio,
            last_refreshed_at
        FROM agg_monthly_financials
        WHERE (:month IS NULL OR month = :month)
    """

    
    if sort_by == "month":
        query += f"""
        ORDER BY
            CASE LOWER(LEFT(month, 3))
                WHEN 'jan' THEN 1
                WHEN 'feb' THEN 2
                WHEN 'mar' THEN 3
                WHEN 'apr' THEN 4
                WHEN 'may' THEN 5
                WHEN 'jun' THEN 6
                WHEN 'jul' THEN 7
                WHEN 'aug' THEN 8
                WHEN 'sep' THEN 9
                WHEN 'oct' THEN 10
                WHEN 'nov' THEN 11
                WHEN 'dec' THEN 12
                ELSE 13
            END {sort_order.upper()}
    """
    else:
        query += f" ORDER BY {sort_by} {sort_order.upper()}, month ASC"


    try:
        engine = get_engine()

        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                {"month": month}
            )

            rows = result.mappings().all()

        return [
            MonthlyFinancialResponse.model_validate(
                dict(row)
            )
            for row in rows
        ]

    except SQLAlchemyError:
        logger.exception(
            "Database error while fetching monthly financials"
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# Segment Risk API
# ---------------------------------------------------------

@router.get(
    "/segment-risk",
    response_model=list[SegmentRiskResponse]
)
def get_segment_risk(
    segment_type: str | None = None,
    segment_value: str | None = None,
    sort_by: Literal[
        "segment_type",
        "segment_value",
        "customer_count",
        "high_risk_customers",
        "high_risk_percentage",
        "average_risk_score",
        "average_delayed_months",
        "historical_default_rate",
        "total_credit_exposure"
    ] = "high_risk_percentage",
    sort_order: Literal["asc", "desc"] = "desc"
):

    logger.info("Segment risk analysis requested")

    allowed_sort_columns = {
        "segment_type",
        "segment_value",
        "customer_count",
        "high_risk_customers",
        "high_risk_percentage",
        "average_risk_score",
        "average_delayed_months",
        "historical_default_rate",
        "total_credit_exposure"
    }

    if sort_by not in allowed_sort_columns:
        raise HTTPException(
            status_code=400,
            detail="Invalid sorting column"
        )

    query = """
        SELECT
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
        FROM agg_segment_risk
        WHERE
            (:segment_type IS NULL
                OR segment_type = :segment_type)
            AND
            (:segment_value IS NULL
                OR segment_value = :segment_value)
    """

    query += (
        f" ORDER BY {sort_by} {sort_order.upper()}, "
        "segment_type ASC, segment_value ASC"
    )

    try:
        engine = get_engine()

        with engine.connect() as connection:
            result = connection.execute(
                text(query),
                {
                    "segment_type": segment_type,
                    "segment_value": segment_value
                }
            )

            rows = result.mappings().all()

        return [
            SegmentRiskResponse.model_validate(
                dict(row)
            )
            for row in rows
        ]

    except SQLAlchemyError:
        logger.exception(
            "Database error while fetching segment risk"
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )
