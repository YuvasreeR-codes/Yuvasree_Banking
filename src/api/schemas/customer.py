
from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict, Field


# ---------------------------------------------------------
# Base Model Configuration
# ---------------------------------------------------------

class CustomerBaseModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Customer List Response
# ---------------------------------------------------------

class CustomerResponse(CustomerBaseModel):
    customer_id: int
    gender_label: str | None
    education_label: str | None
    marriage_label: str | None
    age: int | None
    age_group: str | None
    credit_limit: Decimal | None
    months_with_delay: int | None
    latest_credit_utilization: Decimal | None
    payment_to_bill_ratio: Decimal | None
    default_next_month: int | None
    risk_score: int | None
    risk_band: str | None
    risk_reason: str | None


class PaginatedCustomerResponse(CustomerBaseModel):
    total_records: int = Field(ge=0)
    page: int = Field(ge=1)
    page_size: int = Field(ge=1)
    total_pages: int = Field(ge=0)
    data: list[CustomerResponse]


# ---------------------------------------------------------
# Customer Demographic Details
# ---------------------------------------------------------

class CustomerDemographics(CustomerBaseModel):
    customer_id: int
    gender: int | None
    gender_label: str | None
    education: int | None
    education_label: str | None
    marriage: int | None
    marriage_label: str | None
    age: int | None
    age_group: str | None


# ---------------------------------------------------------
# Credit Profile
# ---------------------------------------------------------

class CreditProfileResponse(CustomerBaseModel):
    credit_limit: Decimal

    repayment_status_sep: int | None
    repayment_status_aug: int | None
    repayment_status_jul: int | None
    repayment_status_jun: int | None
    repayment_status_may: int | None
    repayment_status_apr: int | None

    months_with_delay: int | None
    max_repayment_delay: int | None

    total_bill_amount: Decimal | None
    total_payment_amount: Decimal | None
    avg_bill_amount: Decimal | None
    avg_payment_amount: Decimal | None

    latest_credit_utilization: Decimal | None
    payment_to_bill_ratio: Decimal | None
    default_next_month: int | None


# ---------------------------------------------------------
# Risk Score Breakdown
# ---------------------------------------------------------

class RiskScoreResponse(CustomerBaseModel):
    risk_score: int | None
    risk_band: str

    delay_score: int | None
    delay_frequency_score: int | None
    utilization_score: int | None
    payment_score: int | None

    rule_version: str
    risk_reason: str | None
    calculated_at: datetime | None


# ---------------------------------------------------------
# Bill and Payment Records
# ---------------------------------------------------------

class BillResponse(CustomerBaseModel):
    bill_id: int
    month: str
    bill_amount: Decimal | None


class PaymentResponse(CustomerBaseModel):
    payment_id: int
    month: str
    payment_amount: Decimal | None


# ---------------------------------------------------------
# Complete Customer Detail Response
# ---------------------------------------------------------

class CustomerDetailResponse(CustomerBaseModel):
    customer: CustomerDemographics
    credit_profile: CreditProfileResponse | None
    risk_assessment: RiskScoreResponse | None
    bills: list[BillResponse]
    payments: list[PaymentResponse]
