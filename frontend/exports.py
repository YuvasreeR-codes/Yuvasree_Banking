
import os
from datetime import datetime

import pandas as pd
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

def fetch_export_data(endpoint, token, params=None):

    try:
        response = requests.get(
            f"{API_BASE_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            params=params,
            timeout=120
        )

        if response.status_code == 401:
            st.error("Session expired. Please log in again.")
            return None

        if response.status_code == 403:
            st.error("You do not have permission to export data.")
            return None

        if response.status_code == 422:
            st.error(f"Invalid export filters: {response.text}")
            return None

        response.raise_for_status()

        return response

    except requests.RequestException as exc:
        st.error(f"Export request failed: {exc}")
        return None


# ---------------------------------------------------------
# Customer CSV Export Page
# ---------------------------------------------------------

def show_exports(token):

    st.title("📥 Customer Data Export")

    st.write(
        "Export customer credit profiles and risk "
        "assessments as CSV files."
    )

    st.subheader("Export Filters")

    col1, col2, col3, col4, col5, col6 = st.columns(6)
    
    with col1:
        risk_band = st.selectbox(
            "Risk Band",
            ["All", "LOW", "MEDIUM", "HIGH"],
            key="export_risk_band"
        )
    
    with col2:
    
        gender = st.selectbox(
            "Gender",
            ["All", "Male", "Female"],
            key="export_gender"
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
            ],key="export_education"
        )
    with col4:
        marriage = st.selectbox(
            "Marital Status",
            ["All", "Married", "Single", "Other"],
            key="export_marriage"
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
        ],key="export_age_group"
    )


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

    params = {
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

    # -----------------------------------------------------
    # Preview
    # -----------------------------------------------------

    st.divider()

    st.subheader("Export Preview")

    preview_params = {
        **params,
        "page": 1,
        "page_size": 10
    }

    preview_response = fetch_export_data(
        "/api/customers",
        token,
        params=preview_params
    )

    if preview_response is not None:

        preview_data = preview_response.json()

        total_records = preview_data.get(
            "total_records", 0
        )

        st.metric(
            "Matching Customers",
            f"{total_records:,}"
        )

        records = preview_data.get("data", [])

        if records:

            df = pd.DataFrame(records)

            st.dataframe(
                df,
                use_container_width=True,
                hide_index=True
            )

            st.caption(
                "Showing the first 10 matching records."
            )

        else:
            st.info("No customers match the selected filters.")

    # -----------------------------------------------------
    # Generate CSV
    # -----------------------------------------------------

    st.divider()

    st.subheader("Download Customer Data")

    st.info(
        "The exported file includes customer information "
        "returned by the existing FastAPI CSV endpoint."
    )

    current_filters = (
        risk_band,
        gender,
        education,
        marriage,
        age_group,
        sort_by,
        sort_order
    )

    if st.session_state.get("export_filters") != current_filters:
        st.session_state.export_filters = current_filters
        st.session_state.export_csv = None
        st.session_state.export_filename = None

    if st.button(
        "Generate CSV",
        type="primary",
        use_container_width=True
    ):

        with st.spinner("Preparing customer export..."):

            response = fetch_export_data(
                "/api/exports/customers",
                token,
                params=params
            )

            if response is not None:

                st.session_state.export_csv = response.content

                timestamp = datetime.now().strftime(
                    "%Y%m%d_%H%M%S"
                )

                st.session_state.export_filename = (
                    f"bank_customer_export_{timestamp}.csv"
                )

                st.success(
                    "CSV file generated successfully."
                )

    if st.session_state.get("export_csv") is not None:

        st.download_button(
            label="Download CSV",
            data=st.session_state.export_csv,
            file_name=st.session_state.export_filename,
            mime="text/csv",
            use_container_width=True
        )
