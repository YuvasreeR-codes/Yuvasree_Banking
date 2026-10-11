
import os

import pandas as pd
import plotly.express as px
import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


# ---------------------------------------------------------
# API Helper
# ---------------------------------------------------------

def fetch_dashboard_data(endpoint, token, params=None):

    try:
        response = requests.get(
            f"{API_BASE_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params=params,
            timeout=30
        )

        if response.status_code == 401:
            st.error(
                "Session expired. Please log in again."
            )
            return None

        if response.status_code == 403:
            st.error(
                "You do not have permission to view this data."
            )
            return None

        if response.status_code == 404:
            st.warning(
                "No dashboard data is available."
            )
            return None

        response.raise_for_status()

        return response.json()

    except requests.RequestException as exc:
        st.error(f"Unable to load dashboard data: {exc}")
        return None


# ---------------------------------------------------------
# Formatting Helpers
# ---------------------------------------------------------

def format_currency(value):

    if value is None:
        return "N/A"

    amount = float(value)

    if abs(amount) >= 10_000_000:
        return f"₹{amount / 10_000_000:,.2f} Cr"

    if abs(amount) >= 100_000:
        return f"₹{amount / 100_000:,.2f} L"

    return f"₹{amount:,.2f}"


def format_percentage(value):

    if value is None:
        return "N/A"

    return f"{float(value):.2f}%"


# ---------------------------------------------------------
# Portfolio KPIs
# ---------------------------------------------------------

def show_portfolio_kpis(token):

    st.subheader("Portfolio Overview")

    data = fetch_dashboard_data(
        "/api/dashboard/portfolio",
        token
    )

    if not data:
        return

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Total Customers",
        f"{data['total_customers']:,}"
    )

    col2.metric(
        "Total Credit Exposure",
        format_currency(
            data["total_credit_exposure"]
        )
    )

    col3.metric(
        "Average Risk Score",
        (
            f"{float(data['average_risk_score']):.2f}"
            if data["average_risk_score"] is not None
            else "N/A"
        )
    )

    col4.metric(
        "Historical Default Rate",
        format_percentage(
            data["historical_default_rate"]
        )
    )

    col5, col6 = st.columns(2)

    col5.metric(
        "Average Credit Limit",
        format_currency(
            data["average_credit_limit"]
        )
    )

    col6.metric(
        "Defaulted Customers",
        f"{data['total_defaulted_customers']:,}"
    )

    if data.get("last_refreshed_at"):
        st.caption(
            "Last refreshed: "
            f"{data['last_refreshed_at']}"
        )


# ---------------------------------------------------------
# Risk Distribution
# ---------------------------------------------------------

def show_risk_distribution(token):

    st.subheader("Risk Distribution")

    data = fetch_dashboard_data(
        "/api/dashboard/risk-distribution",
        token
    )

    if not data:
        return

    df = pd.DataFrame(data)

    df["customer_count"] = pd.to_numeric(
        df["customer_count"]
    )

    df["total_credit_exposure"] = pd.to_numeric(
        df["total_credit_exposure"]
    )

    df["average_risk_score"] = pd.to_numeric(
        df["average_risk_score"],
        errors="coerce"
    )

    col1, col2 = st.columns(2)

    with col1:

        fig = px.pie(
            df,
            names="risk_band",
            values="customer_count",
            title="Customers by Risk Band",
            hole=0.45,
            color="risk_band",
            color_discrete_map={
                "LOW": "#22c55e",
                "MEDIUM": "#f59e0b",
                "HIGH": "#ef4444"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with col2:

        fig = px.bar(
            df,
            x="risk_band",
            y="total_credit_exposure",
            color="risk_band",
            title="Credit Exposure by Risk Band",
            labels={
                "risk_band": "Risk Band",
                "total_credit_exposure": "Credit Exposure"
            },
            color_discrete_map={
                "LOW": "#22c55e",
                "MEDIUM": "#f59e0b",
                "HIGH": "#ef4444"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with st.expander("View Risk Distribution Data"):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# ---------------------------------------------------------
# Monthly Financial Trends
# ---------------------------------------------------------

def show_monthly_financials(token):

    st.subheader("Monthly Financial Trends")

    data = fetch_dashboard_data(
        "/api/dashboard/monthly-financials",
        token
    )

    if not data:
        return

    df = pd.DataFrame(data)

    month_order = [
        "Apr", "May", "Jun",
        "Jul", "Aug", "Sep"
    ]

    df["month"] = df["month"].astype(str).str.title()

    df["month"] = pd.Categorical(
        df["month"],
        categories=month_order,
        ordered=True
    )

    df = df.sort_values("month")

    numeric_columns = [
        "total_bill_amount",
        "total_payment_amount",
        "average_bill_amount",
        "average_payment_amount",
        "payment_to_bill_ratio"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    col1, col2 = st.columns(2)

    with col1:

        fig = px.line(
            df,
            x="month",
            y=[
                "total_bill_amount",
                "total_payment_amount"
            ],
            markers=True,
            title="Monthly Bills vs Payments",
            labels={
                "month": "Month",
                "value": "Amount",
                "variable": "Metric"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with col2:

        fig = px.bar(
            df,
            x="month",
            y="payment_to_bill_ratio",
            title="Monthly Payment-to-Bill Ratio",
            labels={
                "month": "Month",
                "payment_to_bill_ratio":
                    "Payment-to-Bill Ratio"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with st.expander("View Monthly Financial Data"):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# ---------------------------------------------------------
# Segment Risk Analysis
# ---------------------------------------------------------


def show_segment_risk(token):

    st.subheader("Segment Risk Analysis")

    # Display names mapped to actual database values
    segment_options = {
        "All": None,
        "Gender": "GENDER",
        "Education": "EDUCATION",
        "Marital Status": "MARITAL_STATUS",
        "Age Group": "AGE_GROUP"
    }

    selected_segment = st.selectbox(
        "Select Segment",
        list(segment_options.keys())
    )

    segment_type = segment_options[selected_segment]

    # Fetch all segment records from API
    data = fetch_dashboard_data(
        "/api/dashboard/segment-risk",
        token
    )

    if data is None:
        return

    df = pd.DataFrame(data)

    if df.empty:
        st.warning("No segment risk data available.")
        return

    # Filter using actual database segment names
    if segment_type is not None:
        df = df[
            df["segment_type"].astype(str).str.strip().str.upper()
            == segment_type
        ].copy()

    if df.empty:
        st.warning(
            f"No records found for {selected_segment}."
        )
        return

    numeric_columns = [
        "customer_count",
        "high_risk_customers",
        "high_risk_percentage",
        "average_risk_score",
        "average_delayed_months",
        "historical_default_rate",
        "total_credit_exposure"
    ]

    for column in numeric_columns:
        df[column] = pd.to_numeric(
            df[column],
            errors="coerce"
        )

    if segment_type is None:

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )

        return

    col1, col2 = st.columns(2)

    with col1:

        fig = px.bar(
            df,
            x="segment_value",
            y="high_risk_percentage",
            title=f"High-Risk Percentage by {selected_segment}",
            labels={
                "segment_value": "Segment",
                "high_risk_percentage":
                    "High-Risk Customers (%)"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with col2:

        fig = px.bar(
            df,
            x="segment_value",
            y="total_credit_exposure",
            title=f"Credit Exposure by {selected_segment}",
            labels={
                "segment_value": "Segment",
                "total_credit_exposure":
                    "Credit Exposure"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

    with st.expander("View Segment Risk Data"):

        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True
        )


# ---------------------------------------------------------
# Main Dashboard
# ---------------------------------------------------------

def show_dashboard(token):

    st.title("📊 Banking Loan Risk Dashboard")

    st.write(
        "Monitor portfolio credit exposure, "
        "customer risk distribution, "
        "repayment trends, and demographic risk."
    )

    if st.button("Refresh Dashboard", icon="🔄"):
        with st.spinner("Reloading dashboard data..."):
            st.session_state["dashboard_last_refresh"] = (
                pd.Timestamp.now().strftime("%Y-%m-%d %H:%M:%S")
        )
        st.toast("Dashboard data reloaded")

    if "dashboard_last_refresh" in st.session_state:
        st.caption(
        "Last manually refreshed: "
        + st.session_state["dashboard_last_refresh"]
    )

    show_portfolio_kpis(token)

    st.divider()

    show_risk_distribution(token)

    st.divider()

    show_monthly_financials(token)

    st.divider()

    show_segment_risk(token)
