# Banking Loan Risk Analysis Application

## Project Overview

A Python full-stack application for analyzing customer credit exposure, repayment behavior, and rule-based risk indicators using the **UCI Default of Credit Card Clients** dataset. The system extracts and validates credit data, performs incremental ETL into MySQL, calculates explainable risk bands, exposes REST APIs, and presents dashboards and customer review workflows in Streamlit.

**Data flow:** Excel dataset → Pandas ETL / data-quality checks → MySQL → risk scoring / reporting aggregates → FastAPI → Streamlit.

### Main Features

- Excel ingestion, cleansing, transformation, and batch loading
- Duplicate and invalid-record checks, rejected-record exports, and reconciliation
- Hash-based incremental inserts, updates, and skips
- ETL run logs and record-level audit history
- Rule-based risk scoring with LOW, MEDIUM, HIGH, and UNCLASSIFIED bands
- Portfolio, monthly financial, segment, and risk-distribution reports
- Customer search, filtering, pagination, detail views, and CSV exports
- Risk-review creation, updates, listing, and administrator-only deletion
- JWT login and analyst/administrator roles
- Automated tests for ETL, APIs, business rules, and reporting

## Technology Stack

| Layer | Technology |
| --- | --- |
| Language | Python |
| ETL | Pandas, SQLAlchemy |
| Database | MySQL (PyMySQL driver) |
| API | FastAPI, Uvicorn, Pydantic |
| Frontend | Streamlit, Plotly, Requests |
| Authentication | JWT (PyJWT), pwdlib |
| Testing | pytest |

## Repository Structure

```text
bank_risk_project-main/
├── .env.example
├── frontend/
│   ├── app.py
│   ├── dashboard.py
│   ├── customers.py
│   ├── reviews.py
│   └── exports.py
├── src/
│   ├── api/
│   │   ├── main.py
│   │   ├── routers/       # auth, dashboard, customers, reviews, exports
│   │   ├── schemas/
│   │   └── security.py
│   ├── config.py
│   ├── db/                 # connection, SQL schemas, aggregate refresh
│   ├── etl/                # extract, quality, transform, incremental, load, reconcile
│   ├── risk/               # scoring configuration, engine, repository
│   └── logs/
├── notebooks/
├── tests/
└── test_reports/
```

## Prerequisites

- Python 3.10+ (recommended)
- MySQL Server 8+ and MySQL command-line client (or MySQL Workbench)
- Git (optional, for cloning)
- UCI Default of Credit Card Clients Excel dataset: https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients

## Setup Instructions

### 1. Open the project

Extract the ZIP, open a terminal, and enter the folder containing `src` and `frontend`:

```bash
cd bank_risk_project-main
```

Run all subsequent commands from this **repository root**, so imports such as `src.api.main` work correctly.

### 2. Create and activate a virtual environment

**Windows (PowerShell):**

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

**macOS / Linux:**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

Run`requirements.txt` in the project root with:

```bash
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 4. Configure environment variables

Copy `.env.example` to `.env` in the repository root:

**Windows:**

```powershell
Copy-Item .env.example .env
```

**macOS / Linux:**

```bash
cp .env.example .env
```

Edit `.env`:

```dotenv
DB_HOST=localhost
DB_PORT=3306
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password
DB_NAME=bank_loan_risk

JWT_SECRET_KEY=replace_with_a_random_secret_of_at_least_32_characters
ANALYST_PASSWORD_HASH=replace_with_a_real_pwdlib_hash
ADMIN_PASSWORD_HASH=replace_with_a_real_pwdlib_hash

API_BASE_URL=http://127.0.0.1:8000
```

**Important:** The placeholder password hashes in `.env.example` cannot be used to log in. Generate hashes for your chosen passwords:

```bash
python -c "from pwdlib import PasswordHash; h=PasswordHash.recommended(); print(h.hash(input('Password to hash: ')))"
```

Run the command separately for the analyst and administrator passwords, and paste the outputs into the corresponding `.env` variables. The login usernames are **`analyst`** and **`administrator`**. Never commit `.env` or real credentials to GitHub.

### 5. Initialize MySQL tables

From the repository root, execute these SQL scripts in order (enter your MySQL password when prompted):

```bash
mysql -u your_mysql_user -p < src/db/schema.sql
mysql -u your_mysql_user -p bank_loan_risk < src/db/risk.sql
mysql -u your_mysql_user -p bank_loan_risk < src/db/customer_risk_reviews.sql
mysql -u your_mysql_user -p bank_loan_risk < src/db/aggregate_schema.sql
```

Alternatively, open the files in MySQL Workbench and execute them in the same order. `schema.sql` creates the `bank_loan_risk` database.

**Core tables:** `customers`, `credit_profiles`, `bills`, `payments`.

**Risk tables:** `customer_risk_scores`, `customer_risk_reviews`.

**ETL audit tables:** `etl_runs`, `etl_record_audit`, `data_quality_issues`.

**Reporting tables:** `agg_portfolio_summary`, `agg_risk_distribution`, `agg_monthly_financials`, `agg_segment_risk`.

### 6. Place the input dataset

Download the UCI **Default of Credit Card Clients** Excel file and save it at:

```text
src/data/incoming/default_of_credit_card_clients.xls
```

The ETL supports `.xls` and `.xlsx` files, expects worksheet **`Data`**, and reads column headers from the **second row** (`header=1`). A CSV file cannot be passed directly to the current extractor without modifying the code.

The pipeline creates the `src/data/incoming`, `processed`, `rejected`, and `archive` folders automatically. Successful input files are moved to `archive`, so place a fresh input copy in `incoming` before a subsequent run.

## How to Run

Run these steps **in order** from the project root.

### Step 1 — Execute ETL

```bash
python -m src.etl.pipeline
```

The module's direct-execution block uses `data/incoming/default_of_credit_card_clients.xls`, a path relative to the repository root. **Before running this command, correct that path to `src/data/incoming/default_of_credit_card_clients.xls` in the final block of `src/etl/pipeline.py`,** or invoke the function directly as shown below:

```bash
python -c "from src.etl.pipeline import run_etl_pipeline; print(run_etl_pipeline('src/data/incoming/default_of_credit_card_clients.xls'))"
```

The second command works with the existing code without editing it. ETL outputs include inserted/updated/skipped counts, reconciliation results, curated CSV snapshots, rejected-record exports, and an archived source file. The log is written to `src/logs/etl_pipeline.log`.

### Step 2 — Calculate customer risk scores

```bash
python -m src.risk.risk_repository
```

This calculates the configured rule-based scores and writes to `customer_risk_scores`.

### Step 3 — Refresh dashboard aggregates

```bash
python -m src.db.refresh_aggregates
```

This populates reporting tables used by the dashboard APIs. Rerun after changes to underlying data or risk scores.

### Step 4 — Start FastAPI

In a terminal with the virtual environment activated:

```bash
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

- API root: http://127.0.0.1:8000/
- Health check: http://127.0.0.1:8000/health
- Database health: http://127.0.0.1:8000/health/db
- Interactive API documentation: http://127.0.0.1:8000/docs

### Step 5 — Start Streamlit

In a **second terminal**, from the project root, with the virtual environment activated:

```bash
streamlit run frontend/app.py
```

Open the local address displayed by Streamlit (typically http://localhost:8501). Log in as `analyst` or `administrator` using the passwords configured in Step 4 of setup.

## API Endpoints

**Base URL:** `http://127.0.0.1:8000`

| Method | Endpoint | Purpose |
| --- | --- | --- |
| GET | `/` | API welcome |
| GET | `/health` | Application health |
| GET | `/health/db` | MySQL connectivity |
| POST | `/api/auth/login` | Login (form-encoded username/password) |
| GET | `/api/auth/me` | Current authenticated user |
| GET | `/api/dashboard/portfolio` | Portfolio summary |
| GET | `/api/dashboard/risk-distribution` | Risk-band distribution |
| GET | `/api/dashboard/monthly-financials` | Monthly billing and payment trends |
| GET | `/api/dashboard/segment-risk` | Segment-level risk analysis |
| GET | `/api/customers` | Paginated, filtered customer listing |
| GET | `/api/customers/{customer_id}` | Customer details |
| GET | `/api/exports/customers` | CSV customer export |
| POST | `/api/reviews` | Create customer review |
| GET | `/api/reviews` | List reviews |
| GET | `/api/reviews/{review_id}` | Review details |
| PATCH | `/api/reviews/{review_id}` | Update review |
| DELETE | `/api/reviews/{review_id}` | Delete review (administrator only) |

Except for root, health, and login, the application routes require a JWT Bearer token. Analyst and administrator roles can access reporting and review functions; review deletion requires administrator authorization.

### Common query parameters

- Customer list: `page`, `page_size` (maximum 100), `risk_band`, `gender_label`, `education_label`, `marriage_label`, `age_group`, `min_age`, `max_age`, `min_credit_limit`, `max_credit_limit`, `sort_by`, `sort_order`.
- Monthly financials: `month`, `sort_by`, `sort_order`.
- Segment risk: `segment_type`, `segment_value`, `sort_by`, `sort_order`.
- CSV export supports customer filtering and sorting parameters.

For complete request and response schemas, open `/docs` while the API is running.

## Sample Queries and Outputs

The examples below illustrate the documented response structure; numerical results depend on the records actually loaded. They are **not** claimed to be live outputs from your local database.

### Example 1 — Check API health

```bash
curl http://127.0.0.1:8000/health
```

Expected response:

```json
{
  "status": "healthy",
  "message": "Banking Loan Risk Analysis API is running"
}
```

### Example 2 — Authenticate as analyst

```bash
curl -X POST http://127.0.0.1:8000/api/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=analyst&password=YOUR_ANALYST_PASSWORD"
```

Illustrative response (token shortened):

```json
{
  "access_token": "eyJ...",
  "token_type": "bearer",
  "expires_in": 1800,
  "role": "analyst"
}
```

Copy `access_token` and include it in the following requests as `Authorization: Bearer YOUR_ACCESS_TOKEN`.

### Example 3 — Portfolio summary

```bash
curl http://127.0.0.1:8000/api/dashboard/portfolio \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

Illustrative response (values are examples only):

```json
{
  "summary_id": 1,
  "total_customers": 30000,
  "total_credit_exposure": 5000000000.0,
  "average_credit_limit": 166666.67,
  "average_risk_score": 42.5,
  "total_defaulted_customers": 6000,
  "historical_default_rate": 20.0,
  "last_refreshed_at": "2026-10-11T10:00:00"
}
```

### Example 4 — Filter high-risk customers

```bash
curl "http://127.0.0.1:8000/api/customers?risk_band=HIGH&page=1&page_size=20&sort_by=risk_score&sort_order=desc" \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN"
```

The response is a paginated customer collection containing `total_records`, `page`, `page_size`, `total_pages`, and `data`. Each row includes customer demographics, credit indicators, and risk information defined in `src/api/schemas/customer.py`.

### Example 5 — Create a customer review

```bash
curl -X POST http://127.0.0.1:8000/api/reviews \
  -H "Authorization: Bearer YOUR_ACCESS_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"customer_id":1,"review_status":"Pending","priority":"High","review_notes":"Review recent repayment delays"}'
```

Illustrative response (dates and review ID vary):

```json
{
  "review_id": 1,
  "customer_id": 1,
  "review_status": "Pending",
  "priority": "High",
  "review_notes": "Review recent repayment delays",
  "review_date": "2026-10-11T10:00:00",
  "updated_at": "2026-10-11T10:00:00"
}
```

The customer ID must exist in the database. A successful creation returns HTTP **201**.

## Testing

Run automated tests from the repository root:

```bash
python -m pytest tests/ -v
```

The repository contains saved test reports under `test_reports/`. Some tests may require MySQL and valid environment configuration. Historical reports are not a substitute for rerunning the suite in your own environment.

## Troubleshooting

| Problem | Check |
| --- | --- |
| `DB_USER is not configured` | Create `.env` in the repository root and configure database credentials. |
| `JWT_SECRET_KEY must be configured` | Use a secret of at least 32 characters. |
| Login fails | Replace placeholder password hashes with hashes created using `pwdlib`. |
| `FileNotFoundError` during ETL | Confirm the Excel filename and use the direct function invocation shown above. |
| Excel read failure | Confirm `.xls`/`.xlsx`, sheet `Data`, second-row headers, and `xlrd`/`openpyxl`. |
| API returns 401 | Log in again and pass a valid Bearer token. |
| Dashboard returns 404 / empty data | Run ETL, risk scoring, and aggregate refresh in that order. |
| Database connection fails | Start MySQL, verify the credentials, and apply SQL schemas. |

## Dataset Source

**Dataset:** Default of Credit Card Clients, UCI Machine Learning Repository  
**Link:** https://archive.ics.uci.edu/dataset/350/default+of+credit+card+clients  
**Format used by the implementation:** Excel `.xls` / `.xlsx`  
**Records in original dataset:** 30,000 customers  
**Key fields:** `ID`, `LIMIT_BAL`, `SEX`, `EDUCATION`, `MARRIAGE`, `AGE`, `PAY_0`–`PAY_6` (as supplied), `BILL_AMT1`–`BILL_AMT6`, `PAY_AMT1`–`PAY_AMT6`, and `default payment next month`.

## Notes

- This is a rule-based risk analysis system, **not** a trained machine-learning default prediction model.
- Historical default is a dataset label; the application's risk band is calculated separately using configurable business rules.
- Run locally for demonstration; production deployment, automatic scheduling, and secret management require additional operational setup.
- Never commit database passwords, JWT secrets, or real customer data to a public repository.
