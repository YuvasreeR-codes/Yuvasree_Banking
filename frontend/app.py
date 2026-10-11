
import os

import requests
import streamlit as st
from dotenv import load_dotenv
from dashboard import show_dashboard
from customers import show_customers
from reviews import show_reviews
from exports import show_exports


load_dotenv()

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")


# ---------------------------------------------------------
# Page Configuration
# ---------------------------------------------------------

st.set_page_config(
    page_title="Banking Loan Risk Analysis",
    page_icon="🏦",
    layout="wide",
    initial_sidebar_state="expanded"
)


# ---------------------------------------------------------
# Session State
# ---------------------------------------------------------

if "access_token" not in st.session_state:
    st.session_state.access_token = None

if "username" not in st.session_state:
    st.session_state.username = None

if "role" not in st.session_state:
    st.session_state.role = None


# ---------------------------------------------------------
# Authentication Helpers
# ---------------------------------------------------------

def login_user(username, password):

    try:
        response = requests.post(
            f"{API_BASE_URL}/api/auth/login",
            data={
                "username": username,
                "password": password
            },
            timeout=15
        )

        if response.status_code != 200:
            return False, (
                response.json().get(
                    "detail",
                    "Login failed"
                )
            )

        data = response.json()

        st.session_state.access_token = data["access_token"]
        st.session_state.username = username
        st.session_state.role = data["role"]

        return True, None

    except requests.RequestException:
        return False, (
            "Unable to connect to the FastAPI server."
        )


def logout_user():

    st.session_state.access_token = None
    st.session_state.username = None
    st.session_state.role = None

    st.rerun()


def get_auth_headers():

    return {
        "Authorization":
            f"Bearer {st.session_state.access_token}"
    }


# ---------------------------------------------------------
# Login Screen
# ---------------------------------------------------------

def show_login():

    st.title("🏦 Banking Loan Risk Analysis")

    st.write(
        "Sign in to access banking risk analytics "
        "and customer review management."
    )

    left, center, right = st.columns(
        [1, 1.3, 1]
    )

    with center:

        with st.form("login_form"):

            username = st.text_input(
                "Username"
            )

            password = st.text_input(
                "Password",
                type="password"
            )

            submitted = st.form_submit_button(
                "Sign In",
                use_container_width=True
            )

        if submitted:

            if not username.strip() or not password:
                st.error(
                    "Enter your username and password."
                )
                return

            success, error = login_user(
                username.strip(),
                password
            )

            if success:
                st.rerun()
            else:
                st.error(error)


# ---------------------------------------------------------
# Dashboard Placeholder
# ---------------------------------------------------------

# def show_dashboard():

#     st.title("📊 Banking Risk Dashboard")

#     st.info(
#         "Portfolio KPIs, risk distribution, "
#         "and financial analytics will appear here."
#     )


# ---------------------------------------------------------
# Customer Explorer Placeholder
# ---------------------------------------------------------

# def show_customers():

#     st.title("👥 Customer Explorer")

#     st.info(
#         "Customer search, filtering, pagination, "
#         "and risk details will appear here."
#     )


# ---------------------------------------------------------
# Risk Reviews Placeholder
# ---------------------------------------------------------

# def show_reviews():

#     st.title("📋 Customer Risk Reviews")

#     st.info(
#         "Create, view, and update customer risk reviews."
#     )

#     if st.session_state.role == "administrator":
#         st.success(
#             "Administrator access: "
#             "Review deletion is permitted."
#         )


# ---------------------------------------------------------
# CSV Export Placeholder
# ---------------------------------------------------------

# def show_exports():

#     st.title("📥 Customer Data Export")

#     st.info(
#         "Filtered customer CSV export "
#         "will be available here."
#     )


# ---------------------------------------------------------
# Main Application
# ---------------------------------------------------------

def main():

    if not st.session_state.access_token:
        show_login()
        return

    # Validate the token on every Streamlit rerun.
    try:
        response = requests.get(
            f"{API_BASE_URL}/api/auth/me",
            headers=get_auth_headers(),
            timeout=15
        )

        if response.status_code == 401:
            st.session_state.access_token = None
            st.session_state.username = None
            st.session_state.role = None
            st.warning(
                "Your session has expired. Please sign in again."
            )
            show_login()
            return

        response.raise_for_status()

        user = response.json()

        st.session_state.username = user["username"]
        st.session_state.role = user["role"]

    except requests.RequestException:
        st.error(
            "Unable to verify your session. "
            "Check that the FastAPI server is running."
        )
        return

    # Sidebar Navigation
    with st.sidebar:

        st.title("🏦 Bank Risk")

        st.divider()

        st.write(
            f"**User:** {st.session_state.username}"
        )

        st.write(
            f"**Role:** {st.session_state.role.title()}"
        )

        st.divider()

        selected_page = st.radio(
            "Navigation",
            [
                "Dashboard",
                "Customer Explorer",
                "Risk Reviews",
                "Data Export"
            ]
        )

        st.divider()

        if st.button(
            "Logout",
            use_container_width=True
        ):
            logout_user()

    # Page Routing
    if selected_page == "Dashboard":
        show_dashboard(st.session_state.access_token)

    elif selected_page == "Customer Explorer":
        show_customers(st.session_state.access_token)

    elif selected_page == "Risk Reviews":
        show_reviews(
        st.session_state.access_token,
        st.session_state.role
    )

    elif selected_page == "Data Export":
        show_exports(st.session_state.access_token)


if __name__ == "__main__":
    main()
