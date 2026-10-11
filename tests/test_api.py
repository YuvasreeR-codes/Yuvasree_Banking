
import os
import uuid

import pytest
from dotenv import load_dotenv
from fastapi.testclient import TestClient
from sqlalchemy import text

from src.api.main import app
from src.db.connection import get_engine


load_dotenv()

client = TestClient(app)
engine = get_engine()


# ---------------------------------------------------------
# Configuration
# ---------------------------------------------------------

ANALYST_USERNAME = "analyst"
ADMIN_USERNAME = "administrator"

ANALYST_PASSWORD = os.getenv("TEST_ANALYST_PASSWORD")
ADMIN_PASSWORD = os.getenv("TEST_ADMIN_PASSWORD")

TEST_CUSTOMER_ID = os.getenv("TEST_CUSTOMER_ID")


# ---------------------------------------------------------
# Fixtures
# ---------------------------------------------------------

@pytest.fixture(scope="session")
def customer_id():

    if not TEST_CUSTOMER_ID:
        pytest.skip(
            "Set TEST_CUSTOMER_ID to an existing customer"
        )

    value = int(TEST_CUSTOMER_ID)

    with engine.connect() as connection:
        exists = connection.execute(
            text("""
                SELECT customer_id
                FROM customers
                WHERE customer_id = :customer_id
            """),
            {"customer_id": value}
        ).first()

    if exists is None:
        pytest.skip("Test customer does not exist")

    return value


def login(username, password):

    response = client.post(
        "/api/auth/login",
        data={
            "username": username,
            "password": password
        }
    )

    assert response.status_code == 200, response.text

    token = response.json()["access_token"]

    return {
        "Authorization": f"Bearer {token}"
    }


@pytest.fixture(scope="session")
def analyst_headers():

    if not ANALYST_PASSWORD:
        pytest.skip("TEST_ANALYST_PASSWORD not configured")

    return login(
        ANALYST_USERNAME,
        ANALYST_PASSWORD
    )


@pytest.fixture(scope="session")
def admin_headers():

    if not ADMIN_PASSWORD:
        pytest.skip("TEST_ADMIN_PASSWORD not configured")

    return login(
        ADMIN_USERNAME,
        ADMIN_PASSWORD
    )


@pytest.fixture
def temporary_review(customer_id, admin_headers):

    marker = f"API_TEST_{uuid.uuid4().hex}"

    response = client.post(
        "/api/reviews",
        headers=admin_headers,
        json={
            "customer_id": customer_id,
            "review_status": "Pending",
            "priority": "Medium",
            "review_notes": marker
        }
    )

    assert response.status_code == 201, response.text

    review_id = response.json()["review_id"]

    yield review_id

    # Cleanup even if the test fails.
    with engine.begin() as connection:
        connection.execute(
            text("""
                DELETE FROM customer_risk_reviews
                WHERE review_id = :review_id
                  AND review_notes LIKE :marker
            """),
            {
                "review_id": review_id,
                "marker": f"%{marker}%"
            }
        )


# ---------------------------------------------------------
# Authentication Tests
# ---------------------------------------------------------

def test_login_invalid_credentials():

    response = client.post(
        "/api/auth/login",
        data={
            "username": "invalid_user",
            "password": "invalid_password"
        }
    )

    assert response.status_code == 401


def test_protected_endpoint_without_token():

    response = client.get("/api/reviews")

    assert response.status_code == 401


def test_invalid_token():

    response = client.get(
        "/api/reviews",
        headers={
            "Authorization": "Bearer invalid.token.value"
        }
    )

    assert response.status_code == 401


def test_analyst_profile(analyst_headers):

    response = client.get(
        "/api/auth/me",
        headers=analyst_headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "analyst"


def test_admin_profile(admin_headers):

    response = client.get(
        "/api/auth/me",
        headers=admin_headers
    )

    assert response.status_code == 200
    assert response.json()["role"] == "administrator"


# ---------------------------------------------------------
# CREATE Tests
# ---------------------------------------------------------

def test_analyst_can_create_review(
    customer_id,
    analyst_headers
):

    marker = f"API_TEST_{uuid.uuid4().hex}"

    response = client.post(
        "/api/reviews",
        headers=analyst_headers,
        json={
            "customer_id": customer_id,
            "review_status": "Pending",
            "priority": "High",
            "review_notes": marker
        }
    )

    assert response.status_code == 201, response.text

    review_id = response.json()["review_id"]

    try:
        assert response.json()["priority"] == "High"
        assert response.json()["customer_id"] == customer_id

    finally:
        with engine.begin() as connection:
            connection.execute(
                text("""
                    DELETE FROM customer_risk_reviews
                    WHERE review_id = :review_id
                      AND review_notes = :marker
                """),
                {
                    "review_id": review_id,
                    "marker": marker
                }
            )


def test_create_review_invalid_customer(admin_headers):

    response = client.post(
        "/api/reviews",
        headers=admin_headers,
        json={
            "customer_id": 2147483647,
            "review_status": "Pending",
            "priority": "High",
            "review_notes": "Invalid customer test"
        }
    )

    assert response.status_code == 404


def test_create_review_invalid_priority(
    customer_id,
    analyst_headers
):

    response = client.post(
        "/api/reviews",
        headers=analyst_headers,
        json={
            "customer_id": customer_id,
            "priority": "Critical"
        }
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# READ Tests
# ---------------------------------------------------------

def test_get_reviews(analyst_headers):

    response = client.get(
        "/api/reviews",
        headers=analyst_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert "total_records" in data
    assert "data" in data
    assert isinstance(data["data"], list)


def test_get_review_by_id(
    temporary_review,
    analyst_headers
):

    response = client.get(
        f"/api/reviews/{temporary_review}",
        headers=analyst_headers
    )

    assert response.status_code == 200
    assert response.json()["review_id"] == temporary_review


def test_get_nonexistent_review(analyst_headers):

    response = client.get(
        "/api/reviews/2147483647",
        headers=analyst_headers
    )

    assert response.status_code == 404


# ---------------------------------------------------------
# UPDATE Tests
# ---------------------------------------------------------

def test_analyst_can_update_review(
    temporary_review,
    analyst_headers
):

    response = client.patch(
        f"/api/reviews/{temporary_review}",
        headers=analyst_headers,
        json={
            "review_status": "In Progress",
            "priority": "High"
        }
    )

    assert response.status_code == 200, response.text

    data = response.json()

    assert data["review_status"] == "In Progress"
    assert data["priority"] == "High"


def test_update_review_invalid_status(
    temporary_review,
    analyst_headers
):

    response = client.patch(
        f"/api/reviews/{temporary_review}",
        headers=analyst_headers,
        json={
            "review_status": "Invalid Status"
        }
    )

    assert response.status_code == 422


def test_update_review_empty_body(
    temporary_review,
    analyst_headers
):

    response = client.patch(
        f"/api/reviews/{temporary_review}",
        headers=analyst_headers,
        json={}
    )

    assert response.status_code == 400


# ---------------------------------------------------------
# DELETE and RBAC Tests
# ---------------------------------------------------------

def test_analyst_cannot_delete_review(
    temporary_review,
    analyst_headers
):

    response = client.delete(
        f"/api/reviews/{temporary_review}",
        headers=analyst_headers
    )

    assert response.status_code == 403


def test_admin_can_delete_review(
    temporary_review,
    admin_headers
):

    response = client.delete(
        f"/api/reviews/{temporary_review}",
        headers=admin_headers
    )

    assert response.status_code == 204

    verify = client.get(
        f"/api/reviews/{temporary_review}",
        headers=admin_headers
    )

    assert verify.status_code == 404


# ---------------------------------------------------------
# Pagination and Filtering Tests
# ---------------------------------------------------------

def test_review_pagination(analyst_headers):

    response = client.get(
        "/api/reviews?page=1&page_size=5",
        headers=analyst_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert data["page"] == 1
    assert data["page_size"] == 5
    assert len(data["data"]) <= 5


def test_review_priority_filter(analyst_headers):

    response = client.get(
        "/api/reviews?priority=High",
        headers=analyst_headers
    )

    assert response.status_code == 200

    for review in response.json()["data"]:
        assert review["priority"] == "High"


def test_invalid_page_size(analyst_headers):

    response = client.get(
        "/api/reviews?page_size=200",
        headers=analyst_headers
    )

    assert response.status_code == 422


# ---------------------------------------------------------
# Dashboard and Customer API Tests
# ---------------------------------------------------------

def test_dashboard_requires_authentication():

    response = client.get(
        "/api/dashboard/portfolio"
    )

    assert response.status_code == 401


def test_dashboard_portfolio(analyst_headers):

    response = client.get(
        "/api/dashboard/portfolio",
        headers=analyst_headers
    )

    assert response.status_code == 200


def test_customer_list(analyst_headers):

    response = client.get(
        "/api/customers?page=1&page_size=10",
        headers=analyst_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert "data" in data
    assert len(data["data"]) <= 10


def test_customer_details(
    customer_id,
    analyst_headers
):

    response = client.get(
        f"/api/customers/{customer_id}",
        headers=analyst_headers
    )

    assert response.status_code == 200

    data = response.json()

    assert data["customer"]["customer_id"] == customer_id
    assert "credit_profile" in data
    assert "risk_assessment" in data


# ---------------------------------------------------------
# Export Tests
# ---------------------------------------------------------

def test_csv_export_requires_authentication():

    response = client.get(
        "/api/exports/customers"
    )

    assert response.status_code == 401


def test_csv_export(admin_headers):

    response = client.get(
        "/api/exports/customers",
        headers=admin_headers
    )

    assert response.status_code == 200
    assert "text/csv" in response.headers["content-type"]
    assert "customer_id" in response.text.splitlines()[0]
