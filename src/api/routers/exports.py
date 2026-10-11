
import csv
import logging
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from typing import Literal

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from src.db.connection import get_engine
from fastapi import Depends
from src.api.security import require_analyst_or_admin

router = APIRouter(
    prefix="/api/exports",
    tags=["Exports"],
    dependencies=[
        Depends(require_analyst_or_admin)
    ]
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Customer CSV Export
# ---------------------------------------------------------

@router.get("/customers")
def export_customers(
    risk_band: Literal[
        "LOW", "MEDIUM", "HIGH"
    ] | None = None,

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

    query = text(f"""
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

        FROM customers c

        LEFT JOIN credit_profiles cp
            ON c.customer_id = cp.customer_id

        LEFT JOIN customer_risk_scores r
            ON c.customer_id = r.customer_id

        WHERE
    (:risk_band IS NULL
        OR r.risk_band = :risk_band)

    AND (:gender_label IS NULL
        OR c.gender_label = :gender_label)

    AND (:education_label IS NULL
        OR c.education_label = :education_label)

    AND (:marriage_label IS NULL
        OR c.marriage_label = :marriage_label)

    AND (:age_group IS NULL
        OR c.age_group = :age_group)

    AND (:min_age IS NULL
        OR c.age >= :min_age)

    AND (:max_age IS NULL
        OR c.age <= :max_age)

    AND (:min_credit_limit IS NULL
        OR cp.credit_limit >= :min_credit_limit)

    AND (:max_credit_limit IS NULL
        OR cp.credit_limit <= :max_credit_limit)

ORDER BY
    {sort_column} {sort_order.upper()},
    c.customer_id ASC
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
    "max_credit_limit": max_credit_limit
}

    columns = [
        "customer_id",
        "gender_label",
        "education_label",
        "marriage_label",
        "age",
        "age_group",
        "credit_limit",
        "months_with_delay",
        "latest_credit_utilization",
        "payment_to_bill_ratio",
        "default_next_month",
        "risk_score",
        "risk_band",
        "risk_reason"
    ]

    try:
        engine = get_engine()

        # Stream database rows in batches.
        # The connection stays open during CSV generation.
        def generate_csv():
            with engine.connect() as connection:
                result = connection.execution_options(
                    stream_results=True
                ).execute(query, params)

                buffer = StringIO()
                writer = csv.writer(buffer)

                writer.writerow(columns)
                yield buffer.getvalue()
                buffer.seek(0)
                buffer.truncate(0)

                while True:
                    rows = result.fetchmany(1000)

                    if not rows:
                        break

                    for row in rows:
                        record = dict(row._mapping)

                        # Protect spreadsheet applications
                        # against CSV formula injection.
                        values = []

                        for column in columns:
                            value = record[column]

                            if value is None:
                                value = ""

                            elif isinstance(value, str):
                                if value.lstrip().startswith(
                                    ("=", "+", "-", "@")
                                ):
                                    value = "'" + value

                            values.append(value)

                        writer.writerow(values)

                    yield buffer.getvalue()
                    buffer.seek(0)
                    buffer.truncate(0)

        filename = (
            "customer_risk_export_"
            + datetime.now(timezone.utc).strftime(
                "%Y%m%d_%H%M%S"
            )
            + ".csv"
        )

        logger.info("Customer CSV export requested")

        return StreamingResponse(
            generate_csv(),
            media_type="text/csv",
            headers={
                "Content-Disposition":
                    f'attachment; filename="{filename}"',
                "Cache-Control": "no-store"
            }
        )

    except SQLAlchemyError:
        logger.exception(
            "Database error preparing customer export"
        )

        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )
