
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Allowed Values
# ---------------------------------------------------------

ReviewStatus = Literal[
    "Pending",
    "In Progress",
    "Completed"
]

ReviewPriority = Literal[
    "Low",
    "Medium",
    "High"
]


# ---------------------------------------------------------
# Create Review Request
# ---------------------------------------------------------

class ReviewCreate(BaseModel):
    customer_id: int = Field(gt=0)

    review_status: ReviewStatus = "Pending"

    priority: ReviewPriority = "Medium"

    review_notes: str | None = Field(
        default=None,
        max_length=5000
    )


# ---------------------------------------------------------
# Update Review Request
# ---------------------------------------------------------

class ReviewUpdate(BaseModel):
    review_status: ReviewStatus | None = None

    priority: ReviewPriority | None = None

    review_notes: str | None = Field(
        default=None,
        max_length=5000
    )

    model_config = ConfigDict(
        extra="forbid"
    )


# ---------------------------------------------------------
# Review Response
# ---------------------------------------------------------

class ReviewResponse(BaseModel):
    review_id: int
    customer_id: int

    review_status: ReviewStatus
    priority: ReviewPriority

    review_notes: str | None

    review_date: datetime
    updated_at: datetime

    model_config = ConfigDict(
        from_attributes=True
    )


# ---------------------------------------------------------
# Paginated Review List Response
# ---------------------------------------------------------

class PaginatedReviewResponse(BaseModel):
    total_records: int = Field(ge=0)

    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)

    data: list[ReviewResponse]
