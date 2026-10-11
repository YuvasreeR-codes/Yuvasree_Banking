
import logging
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.connection import get_engine

from src.api.schemas.customer import (
    CustomerResponse,
    PaginatedCustomerResponse,
    CustomerDetailResponse,
    CustomerDemographics,
    CreditProfileResponse,
    RiskScoreResponse,
    BillResponse,
    PaymentResponse,
)
from fastapi import Depends
from src.api.security import require_analyst_or_admin

router = APIRouter(
    prefix="/api/customers",
    tags=["Customers"],
    dependencies=[
        Depends(require_analyst_or_admin)
    ]
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Customer List API
# ---------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedCustomerResponse
)
def get_customers(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),

    risk_band: Literal["LOW", "MEDIUM", "HIGH"] | None = None,
    gender_label: str | None = None,
    education_label: str | None = None,
    marriage_label: str | None = None,
    age_group: str | None = None,

    min_age: int | None = Query(default=None, ge=0),
    max_age: int | None = Query(default=None, ge=0),

    min_credit_limit: Decimal | None = Query(
        default=None, ge=0
    ),
    max_credit_limit: Decimal | None = Query(
        default=None, ge=0
    ),

    sort_by: Literal[
        "customer_id",
        "age",
        "credit_limit",
        "risk_score",
        "months_with_delay",
        "latest_credit_utilization"
    ] = "customer_id",

    sort_order: Literal["asc", "desc"] = "asc"
):

    if (
        min_age is not None
        and max_age is not None
        and min_age > max_age
    ):
        raise HTTPException(
            status_code=400,
            detail="min_age cannot exceed max_age"
        )

    if (
        min_credit_limit is not None
        and max_credit_limit is not None
        and min_credit_limit > max_credit_limit
    ):
        raise HTTPException(
            status_code=400,
            detail="min_credit_limit cannot exceed max_credit_limit"
        )

    offset = (page - 1) * page_size

    joins = """
        FROM customers c
        LEFT JOIN credit_profiles cp
            ON c.customer_id = cp.customer_id
        LEFT JOIN customer_risk_scores r
            ON c.customer_id = r.customer_id
    """

    filters = """
    WHERE (:risk_band IS NULL OR r.risk_band = :risk_band)

      AND (:gender_label IS NULL
           OR c.gender_label = :gender_label)

      AND (:education_label IS NULL
           OR c.education_label = :education_label)

      AND (:marriage_label IS NULL
           OR c.marriage_label = :marriage_label)

      AND (:age_group IS NULL
           OR c.age_group = :age_group)

      AND (:min_age IS NULL OR c.age >= :min_age)
      AND (:max_age IS NULL OR c.age <= :max_age)

      AND (
          :min_credit_limit IS NULL
          OR cp.credit_limit >= :min_credit_limit
      )

      AND (
          :max_credit_limit IS NULL
          OR cp.credit_limit <= :max_credit_limit
      )
"""

    sort_columns = {
        "customer_id": "c.customer_id",
        "age": "c.age",
        "credit_limit": "cp.credit_limit",
        "risk_score": "r.risk_score",
        "months_with_delay": "cp.months_with_delay",
        "latest_credit_utilization":
            "cp.latest_credit_utilization"
    }

    sort_column = sort_columns[sort_by]

    count_query = text(
        "SELECT COUNT(*) " + joins + filters
    )

    data_query = text(f"""
        SELECT
            c.customer_id,
            c.gender_label,
            c.education_label,
            c.marriage_label,
            c.age,
            c.age_group,
            cp.credit_limit,
            cp.months_with_delay,
            cp.latest_credit_utilization,
            cp.payment_to_bill_ratio,
            cp.default_next_month,
            r.risk_score,
            r.risk_band,
            r.risk_reason
        {joins}
        {filters}
        ORDER BY
            {sort_column} {sort_order.upper()},
            c.customer_id ASC
        LIMIT :limit OFFSET :offset
    """)

    params = {
    "risk_band": risk_band,
    "gender_label": gender_label,
    "education_label": education_label,
    "marriage_label": marriage_label,
    "age_group": age_group,
    "min_age": min_age,
    "max_age": max_age,
    "min_credit_limit": min_credit_limit,
    "max_credit_limit": max_credit_limit,
    "limit": page_size,
    "offset": offset
}

    try:
        engine = get_engine()

        with engine.connect() as connection:
            total_records = connection.execute(
                count_query, params
            ).scalar_one()

            rows = connection.execute(
                data_query, params
            ).mappings().all()

        total_pages = (
            total_records + page_size - 1
        ) // page_size

        return PaginatedCustomerResponse(
            total_records=total_records,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            data=[
                CustomerResponse.model_validate(dict(row))
                for row in rows
            ]
        )

    except SQLAlchemyError:
        logger.exception("Error fetching customers")

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# Customer Detail API
# ---------------------------------------------------------

@router.get(
    "/{customer_id}",
    response_model=CustomerDetailResponse
)
def get_customer_details(
    customer_id: int = Path(ge=1)
):

    customer_query = text("""
        SELECT
            c.customer_id,
            c.gender,
            c.gender_label,
            c.education,
            c.education_label,
            c.marriage,
            c.marriage_label,
            c.age,
            c.age_group
        FROM customers c
        WHERE c.customer_id = :customer_id
    """)

    credit_query = text("""
        SELECT
            credit_limit,
            repayment_status_sep,
            repayment_status_aug,
            repayment_status_jul,
            repayment_status_jun,
            repayment_status_may,
            repayment_status_apr,
            months_with_delay,
            max_repayment_delay,
            total_bill_amount,
            total_payment_amount,
            avg_bill_amount,
            avg_payment_amount,
            latest_credit_utilization,
            payment_to_bill_ratio,
            default_next_month
        FROM credit_profiles
        WHERE customer_id = :customer_id
    """)

    risk_query = text("""
        SELECT
            risk_score,
            risk_band,
            delay_score,
            delay_frequency_score,
            utilization_score,
            payment_score,
            rule_version,
            risk_reason,
            calculated_at
        FROM customer_risk_scores
        WHERE customer_id = :customer_id
    """)

    bills_query = text("""
        SELECT
            bill_id,
            month,
            bill_amount
        FROM bills
        WHERE customer_id = :customer_id
        ORDER BY
            FIELD(
                LOWER(month),
                'apr', 'may', 'jun',
                'jul', 'aug', 'sep'
            ),
            bill_id
    """)

    payments_query = text("""
        SELECT
            payment_id,
            month,
            payment_amount
        FROM payments
        WHERE customer_id = :customer_id
        ORDER BY
            FIELD(
                LOWER(month),
                'apr', 'may', 'jun',
                'jul', 'aug', 'sep'
            ),
            payment_id
    """)

    params = {"customer_id": customer_id}

    try:
        engine = get_engine()

        with engine.connect() as connection:

            customer = connection.execute(
                customer_query, params
            ).mappings().first()

            if customer is None:
                raise HTTPException(
                    status_code=404,
                    detail="Customer not found"
                )

            credit = connection.execute(
                credit_query, params
            ).mappings().first()

            risk = connection.execute(
                risk_query, params
            ).mappings().first()

            bills = connection.execute(
                bills_query, params
            ).mappings().all()

            payments = connection.execute(
                payments_query, params
            ).mappings().all()

        return CustomerDetailResponse(
            customer=CustomerDemographics.model_validate(
                dict(customer)
            ),

            credit_profile=(
                CreditProfileResponse.model_validate(
                    dict(credit)
                )
                if credit is not None else None
            ),

            risk_assessment=(
                RiskScoreResponse.model_validate(
                    dict(risk)
                )
                if risk is not None else None
            ),

            bills=[
                BillResponse.model_validate(dict(row))
                for row in bills
            ],

            payments=[
                PaymentResponse.model_validate(dict(row))
                for row in payments
            ]
        )

    except SQLAlchemyError:
        logger.exception(
            "Error fetching customer %s",
            customer_id
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )
