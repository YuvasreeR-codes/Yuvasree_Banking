
import os

import pandas as pd
import requests
import streamlit as st
import plotly.express as px
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


# ---------------------------------------------------------
# API Helper
# ---------------------------------------------------------

def fetch_customer_data(endpoint, token, params=None):

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
            st.error("Session expired. Please log in again.")
            return None

        if response.status_code == 404:
            st.warning("Customer not found.")
            return None

        response.raise_for_status()
        return response.json()

    except requests.RequestException as exc:
        st.error(f"Unable to load customer data: {exc}")
        return None


# ---------------------------------------------------------
# Customer Detail View
# ---------------------------------------------------------

def show_customer_details(customer_id, token):

    data = fetch_customer_data(
        f"/api/customers/{customer_id}",
        token
    )

    if data is None:
        return

    customer = data.get("customer") or {}
    credit = data.get("credit_profile") or {}
    risk = data.get("risk_assessment") or {}
    bills = data.get("bills") or []
    payments = data.get("payments") or []

    st.subheader(f"Customer #{customer_id}")

    # Demographics
    st.markdown("#### Customer Information")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Age", customer.get("age", "N/A"))
    col2.metric("Gender", customer.get("gender_label", "N/A"))
    col3.metric("Education", customer.get("education_label", "N/A"))
    col4.metric("Marital Status", customer.get("marriage_label", "N/A"))

    st.divider()

    # Credit Profile
    st.markdown("#### Credit Profile")

    col1, col2, col3, col4 = st.columns(4)

    col1.metric(
        "Credit Limit",
        f"₹{float(credit.get('credit_limit') or 0):,.2f}"
    )

    col2.metric(
        "Months With Delay",
        credit.get("months_with_delay", "N/A")
    )

    col3.metric(
        "Maximum Repayment Delay",
        credit.get("max_repayment_delay", "N/A")
    )

    col4.metric(
        "Payment-to-Bill Ratio",
        (
            f"{float(credit['payment_to_bill_ratio']):.2f}"
            if credit.get("payment_to_bill_ratio") is not None
            else "N/A"
        )
    )

    # Risk Assessment
    st.divider()
    st.markdown("#### Risk Assessment")

    col1, col2, col3 = st.columns(3)

    col1.metric(
        "Risk Score",
        risk.get("risk_score", "N/A")
    )

    col2.metric(
        "Risk Band",
        risk.get("risk_band", "N/A")
    )

    col3.metric(
        "Rule Version",
        risk.get("rule_version", "N/A")
    )

    if risk.get("risk_reason"):
        st.info(risk["risk_reason"])

    # Repayment History
    st.divider()
    st.markdown("#### Monthly Billing and Payments")

    bills_df = pd.DataFrame(bills)
    payments_df = pd.DataFrame(payments)

    if not bills_df.empty and not payments_df.empty:

        history = bills_df[
            ["month", "bill_amount"]
        ].merge(
            payments_df[
                ["month", "payment_amount"]
            ],
            on="month",
            how="outer"
        )

        month_order = [
            "Apr", "May", "Jun",
            "Jul", "Aug", "Sep"
        ]

        history["month"] = pd.Categorical(
            history["month"].astype(str).str.title(),
            categories=month_order,
            ordered=True
        )

        history = history.sort_values("month")

        history["bill_amount"] = pd.to_numeric(
            history["bill_amount"],
            errors="coerce"
        )

        history["payment_amount"] = pd.to_numeric(
            history["payment_amount"],
            errors="coerce"
        )

        fig = px.bar(
            history,
            x="month",
            y=["bill_amount", "payment_amount"],
            barmode="group",
            title="Monthly Bills vs Payments",
            labels={
                "month": "Month",
                "value": "Amount (₹)",
                "variable": "Type"
            }
        )

        st.plotly_chart(
            fig,
            use_container_width=True
        )

        st.dataframe(
            history,
            use_container_width=True,
            hide_index=True
        )

    else:
        st.info("No billing or payment history available.")


# ---------------------------------------------------------
# Customer Explorer
# ---------------------------------------------------------

def show_customers(token):

    st.title("👥 Customer Explorer")

    st.write(
        "Search, filter, and explore customer credit "
        "profiles and risk assessments."
    )

    # Filters
    st.subheader("Filter Customers")

    col1, col2, col3, col4, col5, col6 = st.columns(6)

    with col1:
        risk_band = st.selectbox(
        "Risk Band",
        ["All", "LOW", "MEDIUM", "HIGH"]
    )

    with col2:

        gender = st.selectbox(
        "Gender",
        ["All", "Male", "Female"]
    )

    with col3:
        education = st.selectbox(
        "Education",
        [
            "All",
            "Graduate School",
            "University",
            "High School",
            "Other"
        ]
    )
    with col4:
        marriage = st.selectbox(
        "Marital Status",
        ["All", "Married", "Single", "Other"]
    )

    with col5:
        age_group = st.selectbox(
    "Age Group",
    [
        "All",
        "18-25",
        "26-35",
        "36-45",
        "46-55",
        "56-65",
        "65+"
    ]
)
    
    with col6:
        page_size = st.selectbox(
        "Records Per Page",
        [10, 20, 50, 100],
        index=1
    )

    # Sorting
    sort_col1, sort_col2 = st.columns(2)

    with sort_col1:
        sort_by = st.selectbox(
            "Sort By",
            [
                "customer_id",
                "risk_score",
                "credit_limit",
                "age"
            ]
        )

    with sort_col2:
        sort_order = st.selectbox(
            "Sort Order",
            ["asc", "desc"]
        )

    if "customer_page" not in st.session_state:
        st.session_state.customer_page = 1

    # Reset pagination when filters change
    filters = (
    risk_band,
    gender,
    education,
    marriage,
    age_group,
    page_size,
    sort_by,
    sort_order
)

    if st.session_state.get("customer_filters") != filters:
        st.session_state.customer_filters = filters
        st.session_state.customer_page = 1

    # Build query parameters
    params = {
        "page": st.session_state.customer_page,
        "page_size": page_size,
        "sort_by": sort_by,
        "sort_order": sort_order
    }
    if risk_band != "All":
            params["risk_band"] = risk_band
    demographic_filters = {
    "gender_label": gender,
    "education_label": education,
    "marriage_label": marriage,
    "age_group": age_group
}

    for field, value in demographic_filters.items():
        if value != "All":
            params[field] = value

    

    # if customer_id.strip():
    #     try:
    #         params["customer_id"] = int(
    #             customer_id.strip()
    #         )
    #     except ValueError:
    #         st.error("Customer ID must be a number.")
    #         return

    # Fetch customers
    data = fetch_customer_data(
        "/api/customers",
        token,
        params=params
    )

    if data is None:
        return

    customers = data.get("data", [])
    total_records = data.get("total_records", 0)
    total_pages = data.get("total_pages", 0)

    st.caption(
        f"Total Customers: {total_records:,} | "
        f"Page {st.session_state.customer_page} "
        f"of {max(total_pages, 1)}"
    )

    if not customers:
        st.info("No customers match your filters.")
        return

    df = pd.DataFrame(customers)

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    # Pagination Controls
    prev_col, page_col, next_col = st.columns(
        [1, 2, 1]
    )

    with prev_col:
        if st.button(
            "Previous",
            disabled=st.session_state.customer_page <= 1
        ):
            st.session_state.customer_page -= 1
            st.rerun()

    with page_col:
        st.markdown(
            f"**Page {st.session_state.customer_page} "
            f"of {max(total_pages, 1)}**"
        )

    with next_col:
        if st.button(
            "Next",
            disabled=st.session_state.customer_page >= total_pages
        ):
            st.session_state.customer_page += 1
            st.rerun()

    # Customer Detail Selection
    st.divider()

    st.subheader("View Customer Details")

    selected_customer = st.number_input(
    "Enter Customer ID",
    min_value=1,
    step=1,
    value=1
)

    if st.button("View Details"):
        st.session_state.selected_customer_id = int(
        selected_customer
    )

    if st.session_state.get("selected_customer_id"):
        show_customer_details(
        st.session_state.selected_customer_id,
        token
    )
