
import csv
import io
import os

import pytest
import requests
from dotenv import load_dotenv


load_dotenv()

BASE_URL = os.getenv(
    "API_BASE_URL",
    "http://127.0.0.1:8000"
).rstrip("/")

ANALYST_USERNAME = os.getenv("TEST_ANALYST_USERNAME", "analyst")
ANALYST_PASSWORD = os.getenv("TEST_ANALYST_PASSWORD")

ADMIN_USERNAME = os.getenv(
    "TEST_ADMIN_USERNAME", "administrator"
)
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD")


@pytest.fixture(scope="session")
def analyst_token():
    if not ANALYST_PASSWORD:
        pytest.skip("TEST_ANALYST_PASSWORD is not configured")

    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": ANALYST_USERNAME,
            "password": ANALYST_PASSWORD
        },
        timeout=15
    )

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_token():
    if not ADMIN_PASSWORD:
        pytest.skip("TEST_ADMIN_PASSWORD is not configured")

    response = requests.post(
        f"{BASE_URL}/api/auth/login",
        data={
            "username": ADMIN_USERNAME,
            "password": ADMIN_PASSWORD
        },
        timeout=15
    )

    assert response.status_code == 200, response.text

    return response.json()["access_token"]


def get_headers(token):
    return {
        "Authorization": f"Bearer {token}"
    }


# ---------------------------------------------------------
# Authentication
# ---------------------------------------------------------

def test_unauthorized_customers():
    response = requests.get(
        f"{BASE_URL}/api/customers",
        timeout=15
    )

    assert response.status_code == 401


def test_analyst_identity(analyst_token):
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers=get_headers(analyst_token),
        timeout=15
    )

    assert response.status_code == 200
    assert response.json()["role"] == "analyst"


# ---------------------------------------------------------
# Customer Explorer
# ---------------------------------------------------------

def test_customer_pagination(analyst_token):
    response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params={
            "page": 1,
            "page_size": 10
        },
        timeout=30
    )

    assert response.status_code == 200

    data = response.json()

    assert "total_records" in data
    assert "total_pages" in data
    assert len(data["data"]) <= 10


@pytest.mark.parametrize(
    "field,value",
    [
        ("gender_label", "Female"),
        ("education_label", "University"),
        ("marriage_label", "Married"),
        ("age_group", "26-35"),
        ("risk_band", "HIGH")
    ]
)
def test_customer_filters(
    analyst_token,
    field,
    value
):
    response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params={
            field: value,
            "page_size": 50
        },
        timeout=30
    )

    assert response.status_code == 200

    for customer in response.json()["data"]:
        assert customer[field] == value


def test_combined_customer_filters(analyst_token):
    filters = {
        "gender_label": "Female",
        "education_label": "University",
        "marriage_label": "Married",
        "age_group": "26-35",
        "risk_band": "HIGH"
    }

    response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params=filters,
        timeout=30
    )

    assert response.status_code == 200

    for customer in response.json()["data"]:
        for field, value in filters.items():
            assert customer[field] == value


def test_customer_sorting(analyst_token):
    response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params={
            "sort_by": "risk_score",
            "sort_order": "desc",
            "page_size": 50
        },
        timeout=30
    )

    assert response.status_code == 200

    scores = [
        row["risk_score"]
        for row in response.json()["data"]
        if row["risk_score"] is not None
    ]

    assert scores == sorted(scores, reverse=True)


def test_customer_detail(analyst_token):
    list_response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params={"page_size": 1},
        timeout=30
    )

    assert list_response.status_code == 200

    rows = list_response.json()["data"]

    if not rows:
        pytest.skip("No customers available")

    customer_id = rows[0]["customer_id"]

    response = requests.get(
        f"{BASE_URL}/api/customers/{customer_id}",
        headers=get_headers(analyst_token),
        timeout=30
    )

    assert response.status_code == 200

    data = response.json()

    assert data["customer"]["customer_id"] == customer_id
    assert "credit_profile" in data
    assert "risk_assessment" in data
    assert "bills" in data
    assert "payments" in data


# ---------------------------------------------------------
# CSV Export
# ---------------------------------------------------------

def test_filtered_csv_export(analyst_token):
    filters = {
        "gender_label": "Female",
        "education_label": "University",
        "marriage_label": "Married",
        "age_group": "26-35",
        "risk_band": "HIGH"
    }

    response = requests.get(
        f"{BASE_URL}/api/exports/customers",
        headers=get_headers(analyst_token),
        params=filters,
        timeout=120
    )

    assert response.status_code == 200

    reader = csv.DictReader(
        io.StringIO(response.content.decode("utf-8-sig"))
    )

    rows = list(reader)

    for row in rows:
        for field, value in filters.items():
            assert row[field] == value

    count_response = requests.get(
        f"{BASE_URL}/api/customers",
        headers=get_headers(analyst_token),
        params={**filters, "page_size": 1},
        timeout=30
    )

    assert count_response.status_code == 200

    expected_count = count_response.json()["total_records"]

    assert len(rows) == expected_count


# ---------------------------------------------------------
# Risk Reviews
# ---------------------------------------------------------

def test_review_list(analyst_token):
    response = requests.get(
        f"{BASE_URL}/api/reviews",
        headers=get_headers(analyst_token),
        params={"page": 1, "page_size": 10},
        timeout=30
    )

    assert response.status_code == 200

    data = response.json()

    assert "total_records" in data
    assert "data" in data


def test_analyst_cannot_delete_review(analyst_token):
    response = requests.delete(
        f"{BASE_URL}/api/reviews/999999999",
        headers=get_headers(analyst_token),
        timeout=30
    )

    assert response.status_code == 403


def test_admin_identity(admin_token):
    response = requests.get(
        f"{BASE_URL}/api/auth/me",
        headers=get_headers(admin_token),
        timeout=15
    )

    assert response.status_code == 200
    assert response.json()["role"] == "administrator"
