
import os

import pandas as pd
import requests
import streamlit as st
from dotenv import load_dotenv


load_dotenv()

API_BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

STATUSES = ["Pending", "In Progress", "Completed"]
PRIORITIES = ["Low", "Medium", "High"]


# ---------------------------------------------------------
# API Helper
# ---------------------------------------------------------

def review_api(method, endpoint, token, **kwargs):

    try:
        response = requests.request(
            method,
            f"{API_BASE_URL}{endpoint}",
            headers={
                "Authorization": f"Bearer {token}"
            },
            timeout=30,
            **kwargs
        )

    except requests.RequestException:
        st.error("Unable to connect to the FastAPI server.")
        return None

    if response.status_code == 401:
        st.error("Session expired. Please log in again.")
        return None

    if response.status_code == 403:
        st.error("You do not have permission for this action.")
        return None

    if response.status_code == 404:
        st.error("Review or customer not found.")
        return None

    if response.status_code == 422:
        try:
            st.error(f"Validation error: {response.json()['detail']}")
        except (ValueError, KeyError):
            st.error("Invalid input.")
        return None

    if response.status_code >= 400:
        st.error(f"Request failed: HTTP {response.status_code}")
        return None

    if response.status_code == 204:
        return {"success": True}

    try:
        return response.json()
    except ValueError:
        st.error("Invalid response from server.")
        return None


# ---------------------------------------------------------
# Create Review
# ---------------------------------------------------------

def create_review(token):

    st.subheader("Create Risk Review")

    with st.form("create_review_form", clear_on_submit=True):

        customer_id = st.number_input(
            "Customer ID",
            min_value=1,
            step=1
        )

        status = st.selectbox(
            "Review Status",
            STATUSES
        )

        priority = st.selectbox(
            "Priority",
            PRIORITIES,
            index=1
        )

        notes = st.text_area(
            "Review Notes",
            max_chars=5000
        )

        submitted = st.form_submit_button(
            "Create Review",
            use_container_width=True
        )

    if submitted:

        result = review_api(
            "POST",
            "/api/reviews",
            token,
            json={
                "customer_id": int(customer_id),
                "review_status": status,
                "priority": priority,
                "review_notes": notes or None
            }
        )

        if result is not None:
            st.success(
                f"Review #{result['review_id']} created successfully."
            )


# ---------------------------------------------------------
# View Reviews
# ---------------------------------------------------------


def view_reviews(token):

    st.subheader("Review Records")

    # Filters
    col1, col2, col3 = st.columns(3)

    with col1:
        status_filter = st.selectbox(
            "Filter by Status",
            ["All"] + STATUSES,
            key="review_status_filter"
        )

    with col2:
        priority_filter = st.selectbox(
            "Filter by Priority",
            ["All"] + PRIORITIES,
            key="review_priority_filter"
        )

    with col3:
        page_size = st.selectbox(
            "Records Per Page",
            [10, 20, 50],
            key="review_page_size"
        )

    # Sorting controls
    sort_col1, sort_col2 = st.columns(2)

    with sort_col1:
        sort_by = st.selectbox(
            "Sort By",
            [
                "Review ID",
                "Review Status",
                "Priority"
            ],
            key="review_sort_by"
        )

    with sort_col2:
        sort_order = st.selectbox(
            "Sort Order",
            ["Ascending", "Descending"],
            key="review_sort_order"
        )

    if "review_page" not in st.session_state:
        st.session_state.review_page = 1

    filters = (
        status_filter,
        priority_filter,
        page_size,
        sort_by,
        sort_order
    )

    if st.session_state.get("review_filters") != filters:
        st.session_state.review_filters = filters
        st.session_state.review_page = 1

    params = {
        "page": st.session_state.review_page,
        "page_size": page_size
    }

    if status_filter != "All":
        params["review_status"] = status_filter

    if priority_filter != "All":
        params["priority"] = priority_filter

    # Fetch records
    data = review_api(
        "GET",
        "/api/reviews",
        token,
        params=params
    )

    if data is None:
        return

    reviews = data.get("data", [])
    total_records = data.get("total_records", 0)
    total_pages = data.get("total_pages", 0)

    if not reviews:
        st.info("No reviews found.")
        return

    df = pd.DataFrame(reviews)

    # Define custom sorting order
    status_order = {
        "Pending": 1,
        "In Progress": 2,
        "Completed": 3
    }

    priority_order = {
        "Low": 1,
        "Medium": 2,
        "High": 3
    }

    ascending = sort_order == "Ascending"

    if sort_by == "Review Status":

        df["_sort_key"] = df["review_status"].map(
            status_order
        )

        df = df.sort_values(
            ["_sort_key", "review_id"],
            ascending=[ascending, True]
        )

        df = df.drop(columns=["_sort_key"])

    elif sort_by == "Priority":

        df["_sort_key"] = df["priority"].map(
            priority_order
        )

        df = df.sort_values(
            ["_sort_key", "review_id"],
            ascending=[ascending, True]
        )

        df = df.drop(columns=["_sort_key"])

    else:

        df = df.sort_values(
            "review_id",
            ascending=ascending
        )

    st.caption(
        f"Total Reviews: {total_records} | "
        f"Page {st.session_state.review_page} "
        f"of {max(total_pages, 1)}"
    )

    st.dataframe(
        df,
        use_container_width=True,
        hide_index=True
    )

    # Pagination
    prev_col, page_col, next_col = st.columns(
        [1, 2, 1]
    )

    with prev_col:
        if st.button(
            "Previous",
            key="review_previous",
            disabled=st.session_state.review_page <= 1
        ):
            st.session_state.review_page -= 1
            st.rerun()

    with page_col:
        st.markdown(
            f"**Page {st.session_state.review_page} "
            f"of {max(total_pages, 1)}**"
        )

    with next_col:
        if st.button(
            "Next",
            key="review_next",
            disabled=st.session_state.review_page >= total_pages
        ):
            st.session_state.review_page += 1
            st.rerun()


# ---------------------------------------------------------
# Update Review
# ---------------------------------------------------------

def update_review(token):

    st.subheader("Update Risk Review")

    review_id = st.number_input(
        "Review ID to Update",
        min_value=1,
        step=1,
        key="update_review_id"
    )

    if st.button("Load Review", key="load_review"):

        data = review_api(
            "GET",
            f"/api/reviews/{int(review_id)}",
            token
        )

        if data is not None:
            st.session_state.review_to_update = data

    review = st.session_state.get("review_to_update")

    if review is None:
        return

    if int(review_id) != review["review_id"]:
        st.info("Click Load Review to load this review.")
        return

    st.caption(
        f"Editing Review #{review['review_id']} "
        f"for Customer #{review['customer_id']}"
    )

    with st.form("update_review_form"):

        status = st.selectbox(
            "Review Status",
            STATUSES,
            index=STATUSES.index(review["review_status"])
        )

        priority = st.selectbox(
            "Priority",
            PRIORITIES,
            index=PRIORITIES.index(review["priority"])
        )

        notes = st.text_area(
            "Review Notes",
            value=review.get("review_notes") or "",
            max_chars=5000
        )

        submitted = st.form_submit_button(
            "Save Changes",
            use_container_width=True
        )

    if submitted:

        result = review_api(
            "PATCH",
            f"/api/reviews/{review['review_id']}",
            token,
            json={
                "review_status": status,
                "priority": priority,
                "review_notes": notes or None
            }
        )

        if result is not None:
            st.success("Review updated successfully.")
            st.session_state.review_to_update = result


# ---------------------------------------------------------
# Delete Review (Administrator Only)
# ---------------------------------------------------------

def delete_review(token):

    st.subheader("Delete Risk Review")

    if st.session_state.pop("review_delete_success", False):
        st.success("Review deleted successfully.")

    review_id = st.number_input(
        "Review ID to Delete",
        min_value=1,
        step=1,
        key="delete_review_id"
    )

    if st.button("Find Review", key="find_delete_review"):

        data = review_api(
            "GET",
            f"/api/reviews/{int(review_id)}",
            token
        )

        if data is not None:
            st.session_state.review_to_delete = data

    review = st.session_state.get("review_to_delete")

    if review is None:
        return

    if int(review_id) != review["review_id"]:
        st.info("Click Find Review to confirm the selected review.")
        return

    st.warning(
        f"You are about to permanently delete "
        f"Review #{review['review_id']} "
        f"for Customer #{review['customer_id']}."
    )

    confirm = st.checkbox(
        "I understand this review will be permanently deleted.",
        key="confirm_delete_review"
    )

    if st.button(
        "Delete Review Permanently",
        type="primary",
        disabled=not confirm,
        key="confirm_delete_button"
    ):

        result = review_api(
            "DELETE",
            f"/api/reviews/{review['review_id']}",
            token
        )

        if result is not None:
            st.session_state.review_to_delete = None

            st.session_state.pop("confirm_delete_review", None)

            st.session_state["review_delete_success"] = True

            st.rerun()


# ---------------------------------------------------------
# Main Reviews Page
# ---------------------------------------------------------

def show_reviews(token, role):

    st.title("📋 Customer Risk Review Management")

    st.write(
        "Create, monitor, and manage customer risk reviews."
    )

    tabs = st.tabs(
        [
            "View Reviews",
            "Create Review",
            "Update Review"
        ] + (
            ["Delete Review"]
            if role == "administrator"
            else []
        )
    )

    with tabs[0]:
        view_reviews(token)

    with tabs[1]:
        create_review(token)

    with tabs[2]:
        update_review(token)

    if role == "administrator":
        with tabs[3]:
            delete_review(token)
