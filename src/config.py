from pathlib import Path


# ============================================================
# PROJECT PATHS
# ============================================================

# Root directory of the project
BASE_DIR = Path(__file__).resolve().parent


# Main data directory
DATA_DIR = BASE_DIR / "data"

INCOMING_DIR = DATA_DIR / "incoming"
PROCESSED_DIR = DATA_DIR / "processed"
REJECTED_DIR = DATA_DIR / "rejected"
ARCHIVE_DIR = DATA_DIR / "archive"

LOG_DIR = BASE_DIR / "logs"


# Create directories automatically if they do not exist
for directory in [
    DATA_DIR,
    INCOMING_DIR,
    PROCESSED_DIR,
    REJECTED_DIR,
    ARCHIVE_DIR,
    LOG_DIR
]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# INPUT FILE SETTINGS
# ============================================================

SUPPORTED_FILE_EXTENSIONS = [".xls", ".xlsx"]

EXCEL_SHEET_NAME = "Data"

# UCI XLS dataset has the real column header on row 2.
# Pandas uses zero-based indexing, therefore header=1.
EXCEL_HEADER_ROW = 1


# ============================================================
# EXPECTED RAW DATASET COLUMNS
# ============================================================

REQUIRED_RAW_COLUMNS = [
    "ID",
    "LIMIT_BAL",
    "SEX",
    "EDUCATION",
    "MARRIAGE",
    "AGE",

    "PAY_0",
    "PAY_2",
    "PAY_3",
    "PAY_4",
    "PAY_5",
    "PAY_6",

    "BILL_AMT1",
    "BILL_AMT2",
    "BILL_AMT3",
    "BILL_AMT4",
    "BILL_AMT5",
    "BILL_AMT6",

    "PAY_AMT1",
    "PAY_AMT2",
    "PAY_AMT3",
    "PAY_AMT4",
    "PAY_AMT5",
    "PAY_AMT6",

    "default payment next month"
]


# ============================================================
# STANDARDIZED COLUMN NAMES
# ============================================================

COLUMN_RENAME_MAP = {

    "id": "customer_id",

    "limit_bal": "credit_limit",

    "sex": "gender",

    "pay_0": "repayment_status_sep",
    "pay_2": "repayment_status_aug",
    "pay_3": "repayment_status_jul",
    "pay_4": "repayment_status_jun",
    "pay_5": "repayment_status_may",
    "pay_6": "repayment_status_apr",

    "bill_amt1": "bill_amt_sep",
    "bill_amt2": "bill_amt_aug",
    "bill_amt3": "bill_amt_jul",
    "bill_amt4": "bill_amt_jun",
    "bill_amt5": "bill_amt_may",
    "bill_amt6": "bill_amt_apr",

    "pay_amt1": "payment_amt_sep",
    "pay_amt2": "payment_amt_aug",
    "pay_amt3": "payment_amt_jul",
    "pay_amt4": "payment_amt_jun",
    "pay_amt5": "payment_amt_may",
    "pay_amt6": "payment_amt_apr",

    "default_payment_next_month": "default_next_month"
}


# ============================================================
# DATA QUALITY RULES
# ============================================================

MIN_AGE = 18
MAX_AGE = 100

MIN_CREDIT_LIMIT = 1

VALID_GENDER_VALUES = [1, 2]

# Dataset contains some undocumented education codes
# such as 0, 5 and 6.
VALID_EDUCATION_VALUES = [0, 1, 2, 3, 4, 5, 6]

# Dataset also contains marriage value 0.
VALID_MARRIAGE_VALUES = [0, 1, 2, 3]

VALID_DEFAULT_VALUES = [0, 1]


# ============================================================
# REPAYMENT STATUS
# ============================================================

# Actual values observed in the supplied UCI dataset.
#
# -1 is officially described as paid duly.
#
# -2 and 0 occur in the source dataset but their precise
# meanings are not documented in the dataset description.
#
# For derived delay indicators, values <= 0 are treated
# as non-delay states while the original values are preserved.

VALID_REPAYMENT_VALUES = [
    -2,
    -1,
    0,
    1,
    2,
    3,
    4,
    5,
    6,
    7,
    8
]


# ============================================================
# REPAYMENT COLUMNS
# ============================================================

REPAYMENT_COLUMNS = [
    "repayment_status_sep",
    "repayment_status_aug",
    "repayment_status_jul",
    "repayment_status_jun",
    "repayment_status_may",
    "repayment_status_apr"
]


# ============================================================
# BILL COLUMNS
# ============================================================

BILL_COLUMNS = [
    "bill_amt_sep",
    "bill_amt_aug",
    "bill_amt_jul",
    "bill_amt_jun",
    "bill_amt_may",
    "bill_amt_apr"
]


# ============================================================
# PAYMENT COLUMNS
# ============================================================

PAYMENT_COLUMNS = [
    "payment_amt_sep",
    "payment_amt_aug",
    "payment_amt_jul",
    "payment_amt_jun",
    "payment_amt_may",
    "payment_amt_apr"
]


# ============================================================
# MONTH MAPPINGS
# ============================================================

BILL_MONTH_MAP = {
    "bill_amt_apr": "APR",
    "bill_amt_may": "MAY",
    "bill_amt_jun": "JUN",
    "bill_amt_jul": "JUL",
    "bill_amt_aug": "AUG",
    "bill_amt_sep": "SEP"
}


PAYMENT_MONTH_MAP = {
    "payment_amt_apr": "APR",
    "payment_amt_may": "MAY",
    "payment_amt_jun": "JUN",
    "payment_amt_jul": "JUL",
    "payment_amt_aug": "AUG",
    "payment_amt_sep": "SEP"
}


# ============================================================
# DEMOGRAPHIC LABELS
# ============================================================

GENDER_MAP = {
    1: "Male",
    2: "Female"
}


EDUCATION_MAP = {
    1: "Graduate School",
    2: "University",
    3: "High School",
    4: "Other",
    0: "Other",
    5: "Other",
    6: "Other"
}


MARRIAGE_MAP = {
    1: "Married",
    2: "Single",
    3: "Other",
    0: "Other"
}


# ============================================================
# AGE GROUP SETTINGS
# ============================================================

AGE_BINS = [
    17,
    25,
    35,
    45,
    55,
    65,
    100
]


AGE_LABELS = [
    "18-25",
    "26-35",
    "36-45",
    "46-55",
    "56-65",
    "65+"
]


# ============================================================
# INCREMENTAL ETL SETTINGS
# ============================================================

RECORD_ACTION_NEW = "INSERT"
RECORD_ACTION_DUPLICATE = "SKIP"
RECORD_ACTION_CORRECTION = "UPDATE"
RECORD_ACTION_REJECT = "REJECT"


# ============================================================
# ETL STATUS VALUES
# ============================================================

ETL_STATUS_RUNNING = "RUNNING"
ETL_STATUS_SUCCESS = "SUCCESS"
ETL_STATUS_FAILED = "FAILED"

RECONCILIATION_PASSED = "PASSED"
RECONCILIATION_FAILED = "FAILED"


# ============================================================
# LOGGING
# ============================================================

LOG_FILE = LOG_DIR / "etl.log"

LOG_FORMAT = (
    "%(asctime)s - "
    "%(levelname)s - "
    "%(name)s - "
    "%(message)s"
)

# Batch loading configuration
BATCH_SIZE = 500