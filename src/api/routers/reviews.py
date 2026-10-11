
import logging
from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError, SQLAlchemyError

from src.db.connection import get_engine
from src.api.schemas.reviews import (
    ReviewCreate,
    ReviewUpdate,
    ReviewResponse,
    PaginatedReviewResponse,
)
from fastapi import Depends
from src.api.security import (
    require_analyst_or_admin,
    require_admin
)

router = APIRouter(
    prefix="/api/reviews",
    tags=["Customer Risk Reviews"],
    dependencies=[
        Depends(require_analyst_or_admin)
    ]
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------
# Common SQL Query
# ---------------------------------------------------------

REVIEW_SELECT = """
    SELECT
        review_id,
        customer_id,
        review_status,
        priority,
        review_notes,
        review_date,
        updated_at
    FROM customer_risk_reviews
"""


# ---------------------------------------------------------
# CREATE - POST /api/reviews
# ---------------------------------------------------------

@router.post(
    "",
    response_model=ReviewResponse,
    status_code=201
)
def create_review(review: ReviewCreate):

    engine = get_engine()

    try:
        with engine.begin() as connection:

            customer_exists = connection.execute(
                text("""
                    SELECT customer_id
                    FROM customers
                    WHERE customer_id = :customer_id
                """),
                {"customer_id": review.customer_id}
            ).first()

            if customer_exists is None:
                raise HTTPException(
                    status_code=404,
                    detail="Customer not found"
                )

            result = connection.execute(
                text("""
                    INSERT INTO customer_risk_reviews (
                        customer_id,
                        review_status,
                        priority,
                        review_notes
                    )
                    VALUES (
                        :customer_id,
                        :review_status,
                        :priority,
                        :review_notes
                    )
                """),
                review.model_dump()
            )

            review_id = result.lastrowid

            created_review = connection.execute(
                text(
                    REVIEW_SELECT
                    + " WHERE review_id = :review_id"
                ),
                {"review_id": review_id}
            ).mappings().first()

        return ReviewResponse.model_validate(
            dict(created_review)
        )

    except IntegrityError:
        logger.exception("Review creation integrity error")
        raise HTTPException(
            status_code=409,
            detail="Unable to create review due to a data conflict"
        )

    except SQLAlchemyError:
        logger.exception("Error creating review")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# READ ALL - GET /api/reviews
# ---------------------------------------------------------

@router.get(
    "",
    response_model=PaginatedReviewResponse
)
def get_reviews(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),

    customer_id: int | None = Query(
        default=None, ge=1
    ),

    review_status: Literal[
        "Pending",
        "In Progress",
        "Completed"
    ] | None = None,

    priority: Literal[
        "Low",
        "Medium",
        "High"
    ] | None = None,

    sort_by: Literal[
        "review_id",
        "customer_id",
        "review_date",
        "updated_at",
        "priority",
        "review_status"
    ] = "review_date",

    sort_order: Literal[
        "asc", "desc"
    ] = "desc"
):

    offset = (page - 1) * page_size

    sort_columns = {
        "review_id": "review_id",
        "customer_id": "customer_id",
        "review_date": "review_date",
        "updated_at": "updated_at",
        "priority": "priority",
        "review_status": "review_status"
    }

    order_column = sort_columns[sort_by]

    filters = """
        WHERE (:customer_id IS NULL
               OR customer_id = :customer_id)
          AND (:review_status IS NULL
               OR review_status = :review_status)
          AND (:priority IS NULL
               OR priority = :priority)
    """

    params = {
        "customer_id": customer_id,
        "review_status": review_status,
        "priority": priority,
        "limit": page_size,
        "offset": offset
    }

    count_query = text(
        "SELECT COUNT(*) FROM customer_risk_reviews "
        + filters
    )

    data_query = text(f"""
        {REVIEW_SELECT}
        {filters}
        ORDER BY
            {order_column} {sort_order.upper()},
            review_id DESC
        LIMIT :limit OFFSET :offset
    """)

    try:
        engine = get_engine()

        with engine.connect() as connection:

            total_records = connection.execute(
                count_query, params
            ).scalar_one()

            rows = connection.execute(
                data_query, params
            ).mappings().all()

        return PaginatedReviewResponse(
            total_records=total_records,
            page=page,
            page_size=page_size,
            total_pages=(
                total_records + page_size - 1
            ) // page_size,
            data=[
                ReviewResponse.model_validate(dict(row))
                for row in rows
            ]
        )

    except SQLAlchemyError:
        logger.exception("Error fetching reviews")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# READ ONE - GET /api/reviews/{review_id}
# ---------------------------------------------------------

@router.get(
    "/{review_id}",
    response_model=ReviewResponse
)
def get_review(
    review_id: int = Path(ge=1)
):

    try:
        engine = get_engine()

        with engine.connect() as connection:

            review = connection.execute(
                text(
                    REVIEW_SELECT
                    + " WHERE review_id = :review_id"
                ),
                {"review_id": review_id}
            ).mappings().first()

        if review is None:
            raise HTTPException(
                status_code=404,
                detail="Review not found"
            )

        return ReviewResponse.model_validate(
            dict(review)
        )

    except SQLAlchemyError:
        logger.exception("Error fetching review")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# UPDATE - PATCH /api/reviews/{review_id}
# ---------------------------------------------------------

@router.patch(
    "/{review_id}",
    response_model=ReviewResponse
)
def update_review(
    review: ReviewUpdate,
    review_id: int = Path(ge=1)
):

    update_data = review.model_dump(
        exclude_unset=True
    )

    if not update_data:
        raise HTTPException(
            status_code=400,
            detail="No fields provided for update"
        )

    # Status and priority cannot be explicitly set to NULL.
    for field in ("review_status", "priority"):
        if field in update_data and update_data[field] is None:
            raise HTTPException(
                status_code=422,
                detail=f"{field} cannot be null"
            )

    allowed_fields = {
        "review_status",
        "priority",
        "review_notes"
    }

    set_clauses = [
        f"{field} = :{field}"
        for field in update_data
        if field in allowed_fields
    ]

    params = {
        **update_data,
        "review_id": review_id
    }

    update_query = text(f"""
        UPDATE customer_risk_reviews
        SET
            {", ".join(set_clauses)},
            updated_at = CURRENT_TIMESTAMP
        WHERE review_id = :review_id
    """)

    try:
        engine = get_engine()

        with engine.begin() as connection:

            existing = connection.execute(
                text("""
                    SELECT review_id
                    FROM customer_risk_reviews
                    WHERE review_id = :review_id
                    FOR UPDATE
                """),
                {"review_id": review_id}
            ).first()

            if existing is None:
                raise HTTPException(
                    status_code=404,
                    detail="Review not found"
                )

            connection.execute(
                update_query,
                params
            )

            updated_review = connection.execute(
                text(
                    REVIEW_SELECT
                    + " WHERE review_id = :review_id"
                ),
                {"review_id": review_id}
            ).mappings().first()

        return ReviewResponse.model_validate(
            dict(updated_review)
        )

    except IntegrityError:
        logger.exception("Invalid review update")
        raise HTTPException(
            status_code=409,
            detail="Review update violates database constraints"
        )

    except SQLAlchemyError:
        logger.exception("Error updating review")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )


# ---------------------------------------------------------
# DELETE - DELETE /api/reviews/{review_id}
# ---------------------------------------------------------

@router.delete(
    "/{review_id}",
    status_code=204,
    dependencies=[
        Depends(require_admin)
    ]
)
def delete_review(
    review_id: int = Path(ge=1)
):

    try:
        engine = get_engine()

        with engine.begin() as connection:

            result = connection.execute(
                text("""
                    DELETE FROM customer_risk_reviews
                    WHERE review_id = :review_id
                """),
                {"review_id": review_id}
            )

            if result.rowcount == 0:
                raise HTTPException(
                    status_code=404,
                    detail="Review not found"
                )

        return None

    except SQLAlchemyError:
        logger.exception("Error deleting review")
        raise HTTPException(
            status_code=503,
            detail="Database service unavailable"
        )
