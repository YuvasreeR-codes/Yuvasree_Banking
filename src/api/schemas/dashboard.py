
from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ---------------------------------------------------------
# Portfolio Summary
# Table: agg_portfolio_summary
# ---------------------------------------------------------

class PortfolioSummaryResponse(BaseModel):
    summary_id: int
    total_customers: int
    total_credit_exposure: Decimal
    average_credit_limit: Optional[Decimal]
    average_risk_score: Optional[Decimal]
    total_defaulted_customers: int
    historical_default_rate: Optional[Decimal]
    last_refreshed_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Risk Distribution
# Table: agg_risk_distribution
# ---------------------------------------------------------

class RiskDistributionResponse(BaseModel):
    risk_band: str
    customer_count: int
    percentage: Optional[Decimal]
    average_risk_score: Optional[Decimal]
    total_credit_exposure: Decimal
    defaulted_customers: int
    historical_default_rate: Optional[Decimal]
    last_refreshed_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Monthly Financial Trends
# Table: agg_monthly_financials
# ---------------------------------------------------------

class MonthlyFinancialResponse(BaseModel):
    month: str
    customer_count: int
    total_bill_amount: Decimal
    total_payment_amount: Decimal
    average_bill_amount: Optional[Decimal]
    average_payment_amount: Optional[Decimal]
    payment_to_bill_ratio: Optional[Decimal]
    last_refreshed_at: datetime

    model_config = ConfigDict(from_attributes=True)


# ---------------------------------------------------------
# Customer Segment Risk
# Table: agg_segment_risk
# ---------------------------------------------------------

class SegmentRiskResponse(BaseModel):
    segment_type: str
    segment_value: str
    customer_count: int
    high_risk_customers: int
    high_risk_percentage: Optional[Decimal]
    average_risk_score: Optional[Decimal]
    average_delayed_months: Optional[Decimal]
    historical_default_rate: Optional[Decimal]
    total_credit_exposure: Decimal
    last_refreshed_at: datetime

    model_config = ConfigDict(from_attributes=True)
