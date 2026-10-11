import logging
from datetime import datetime
import math

import pandas as pd
from sqlalchemy import text

from src.config import BATCH_SIZE
from src.db.connection import get_engine


logger = logging.getLogger(__name__)


# ============================================================
# 1. SQL VALUE CONVERSION
# ============================================================

def to_sql_value(value):
    """Convert Pandas/NumPy values into SQL-compatible values."""

    if value is None:
        return None

    if pd.isna(value):
        return None

    if hasattr(value, "item"):
        return value.item()

    return value


def dataframe_to_records(df):
    """Convert a DataFrame into SQL-ready dictionaries."""

    return [
        {
            column: to_sql_value(value)
            for column, value in row.items()
        }
        for row in df.to_dict(orient="records")
    ]


# ============================================================
# 2. PARAMETERIZED SQL QUERIES
# ============================================================

TABLE_COLUMNS = {
    "customers": [
        "customer_id", "gender", "gender_label",
        "education", "education_label",
        "marriage", "marriage_label",
        "age", "age_group", "record_hash"
    ],
    "credit_profiles": [
        "customer_id", "credit_limit",
        "repayment_status_sep", "repayment_status_aug",
        "repayment_status_jul", "repayment_status_jun",
        "repayment_status_may", "repayment_status_apr",
        "months_with_delay", "max_repayment_delay",
        "total_bill_amount", "total_payment_amount",
        "avg_bill_amount", "avg_payment_amount",
        "latest_credit_utilization",
        "payment_to_bill_ratio", "default_next_month"
    ],
    "bills": [
        "customer_id", "month", "bill_amount"
    ],
    "payments": [
        "customer_id", "month", "payment_amount"
    ]
}


def build_insert_query(table_name):
    """Create a safe parameterized INSERT statement."""

    columns = TABLE_COLUMNS[table_name]

    column_sql = ", ".join(f"`{c}`" for c in columns)
    values_sql = ", ".join(f":{c}" for c in columns)

    return text(
        f"INSERT INTO `{table_name}` "
        f"({column_sql}) VALUES ({values_sql})"
    )


def build_update_query(table_name):
    """Create UPDATE statement for a parent table."""

    if table_name not in ("customers", "credit_profiles"):
        raise ValueError(f"Unsupported update table: {table_name}")

    columns = [
        c for c in TABLE_COLUMNS[table_name]
        if c != "customer_id"
    ]

    assignments = ", ".join(
        f"`{c}` = :{c}" for c in columns
    )

    return text(
        f"UPDATE `{table_name}` "
        f"SET {assignments} "
        "WHERE customer_id = :customer_id"
    )


# ============================================================
# 3. BATCH UTILITIES
# ============================================================

def split_into_batches(customer_ids, batch_size=BATCH_SIZE):
    """Yield batches of customer IDs."""

    if batch_size <= 0:
        raise ValueError("Batch size must be greater than zero")

    for start in range(0, len(customer_ids), batch_size):
        yield customer_ids[start:start + batch_size]


def filter_batch_tables(tables, customer_ids):
    """Extract all four relational tables for a batch."""

    ids = set(customer_ids)

    return {
        name: df[df["customer_id"].isin(ids)].copy()
        for name, df in tables.items()
    }


def validate_batch_tables(tables, customer_ids):
    """Check relational record counts before writing."""

    n = len(customer_ids)

    expected = {
        "customers": n,
        "credit_profiles": n,
        "bills": n * 6,
        "payments": n * 6
    }

    for name, count in expected.items():
        if len(tables[name]) != count:
            raise ValueError(
                f"{name}: expected {count} rows, "
                f"found {len(tables[name])}"
            )

    for name in expected:
        if set(tables[name]["customer_id"]) != set(customer_ids):
            raise ValueError(
                f"{name}: customer IDs do not match batch"
            )

    for name in ("bills", "payments"):
        if tables[name].duplicated(
            subset=["customer_id", "month"]
        ).any():
            raise ValueError(
                f"{name}: duplicate customer/month combinations"
            )


# ============================================================
# 4. BULK INSERT
# ============================================================

def bulk_insert(connection, tables):
    """
    Insert multiple customers and their related records.

    Transaction is controlled by the caller.
    """

    for table_name in (
        "customers",
        "credit_profiles",
        "bills",
        "payments"
    ):

        records = dataframe_to_records(tables[table_name])

        if records:
            connection.execute(
                build_insert_query(table_name),
                records
            )


# ============================================================
# 5. BULK UPDATE
# ============================================================

def bulk_update(connection, tables):
    """
    Update historical source corrections.

    Update parent tables and replace monthly child rows.
    """

    customer_ids = (
        tables["customers"]["customer_id"]
        .astype(int)
        .tolist()
    )

    for table_name in ("customers", "credit_profiles"):

        records = dataframe_to_records(tables[table_name])

        if not records:
            continue

        result = connection.execute(
            build_update_query(table_name),
            records
        )

        # MySQL drivers may report matched or changed rows.
        # Therefore rowcount alone is not a reliable indicator
        # that every expected customer was updated.

    # Delete historical monthly rows for these customers.
    # IDs are passed as bound parameters.
    for customer_id in customer_ids:

        for table_name in ("bills", "payments"):

            connection.execute(
                text(
                    f"DELETE FROM `{table_name}` "
                    "WHERE customer_id = :customer_id"
                ),
                {"customer_id": customer_id}
            )

    # Reinsert corrected monthly data.
    for table_name in ("bills", "payments"):

        records = dataframe_to_records(tables[table_name])

        if records:
            connection.execute(
                build_insert_query(table_name),
                records
            )


# ============================================================
# 6. ETL RUN TRACKING
# ============================================================

def create_etl_run(
    run_id,
    source_file,
    source_count,
    valid_count,
    rejected_count,
    new_count,
    duplicate_count,
    correction_count
):
    """Create the initial ETL run record."""

    query = text("""
        INSERT INTO etl_runs (
            run_id, source_file, start_time,
            source_count, valid_count, rejected_count,
            new_count, duplicate_count, correction_count,
            status
        )
        VALUES (
            :run_id, :source_file, :start_time,
            :source_count, :valid_count, :rejected_count,
            :new_count, :duplicate_count, :correction_count,
            'RUNNING'
        )
    """)

    with get_engine().begin() as connection:
        connection.execute(
            query,
            {
                "run_id": run_id,
                "source_file": source_file,
                "start_time": datetime.now(),
                "source_count": source_count,
                "valid_count": valid_count,
                "rejected_count": rejected_count,
                "new_count": new_count,
                "duplicate_count": duplicate_count,
                "correction_count": correction_count
            }
        )


def update_etl_run_counts(run_id, counts):
    """Save actual committed processing counts."""

    query = text("""
        UPDATE etl_runs
        SET inserted_count = :inserted_count,
            updated_count = :updated_count,
            skipped_count = :skipped_count,
            failed_count = :failed_count
        WHERE run_id = :run_id
    """)

    with get_engine().begin() as connection:
        connection.execute(
            query,
            {"run_id": run_id, **counts}
        )


# ============================================================
# 7. DATA QUALITY ISSUE STORAGE
# ============================================================

def save_data_quality_issues(run_id, issues_df):
    """Persist data-quality issues for the ETL run."""

    if issues_df.empty:
        return

    records = dataframe_to_records(issues_df)

    for record in records:
        record["run_id"] = run_id

        customer_id = record.get("customer_id")

        try:
            number = float(customer_id)

            if (
                not number.is_integer()
                or number <= 0
                or number > 2147483647
            ):
                record["customer_id"] = None
            else:
                record["customer_id"] = int(number)

        except (TypeError, ValueError, OverflowError):
            record["customer_id"] = None

        if record.get("invalid_value") is not None:
            record["invalid_value"] = str(
                record["invalid_value"]
            )[:255]

        record["reason"] = str(record["reason"])[:500]

    query = text("""
        INSERT INTO data_quality_issues (
            run_id, customer_id, check_name,
            column_name, invalid_value, reason
        )
        VALUES (
            :run_id, :customer_id, :check_name,
            :column_name, :invalid_value, :reason
        )
    """)

    with get_engine().begin() as connection:
        connection.execute(query, records)


def save_rejected_record_audits(run_id, rejected_df):
    """
    Save one REJECT audit entry per rejected source row.

    Invalid customer IDs are stored as NULL.
    """

    if rejected_df.empty:
        return

    records = []

    for _, row in rejected_df.iterrows():

        raw_id = row.get("customer_id")

        customer_id = None

        try:
            number = float(raw_id)

            if (
        math.isfinite(number)
        and number.is_integer()
        and 0 < number <= 2147483647
            ):
                customer_id = int(number)

        except (TypeError, ValueError, OverflowError):
             pass

        records.append({
            "run_id": run_id,
            "customer_id": customer_id,
            "action": "REJECT",
            "status": "REJECTED",
            "reason": str(
                row.get(
                    "rejection_reason",
                    "Data-quality validation failed"
                )
            )[:500]
        })

    with get_engine().begin() as connection:
        save_audit_records(
            connection,
            records
        )


# ============================================================
# 8. RECORD-LEVEL AUDITING
# ============================================================

AUDIT_QUERY = text("""
    INSERT INTO etl_record_audit (
        run_id, customer_id, action, status, reason
    )
    VALUES (
        :run_id, :customer_id, :action, :status, :reason
    )
""")


def create_audit_records(
    run_id,
    customer_ids,
    action,
    status,
    reason
):
    """Build one audit entry per customer."""

    return [
        {
            "run_id": run_id,
            "customer_id": int(customer_id),
            "action": action,
            "status": status,
            "reason": reason[:500]
        }
        for customer_id in customer_ids
    ]


def save_audit_records(connection, records):
    """Bulk insert audit records in the active transaction."""

    if records:
        connection.execute(AUDIT_QUERY, records)


# ============================================================
# 9. EXECUTE A BATCH TRANSACTION
# ============================================================

def execute_batch(
    run_id,
    customer_ids,
    action,
    tables
):
    """
    Execute one atomic batch.

    All business-table changes and successful audit records
    commit together or roll back together.
    """

    batch_tables = filter_batch_tables(
        tables,
        customer_ids
    )

    validate_batch_tables(
        batch_tables,
        customer_ids
    )

    with get_engine().begin() as connection:

        if action == "INSERT":
            bulk_insert(connection, batch_tables)

        elif action == "UPDATE":
            bulk_update(connection, batch_tables)

        else:
            raise ValueError(f"Unsupported batch action: {action}")

        audit_records = create_audit_records(
            run_id,
            customer_ids,
            action,
            "SUCCESS",
            (
                "New customer inserted"
                if action == "INSERT"
                else "Historical source correction applied"
            )
        )

        save_audit_records(
            connection,
            audit_records
        )


# ============================================================
# 10. FALLBACK: PROCESS INDIVIDUAL CUSTOMERS
# ============================================================

def process_failed_batch_individually(
    run_id,
    customer_ids,
    action,
    tables
):
    """
    After batch rollback, retry customers individually.

    Returns counts of successes and failures.
    """

    successful = 0
    failed = 0

    for customer_id in customer_ids:

        try:
            execute_batch(
                run_id,
                [customer_id],
                action,
                tables
            )

            successful += 1

        except Exception as exc:

            failed += 1

            logger.exception(
                "Customer %s failed during %s",
                customer_id,
                action
            )

            failure_audit = create_audit_records(
                run_id,
                [customer_id],
                action,
                "FAILED",
                str(exc)
            )

            try:
                with get_engine().begin() as connection:
                    save_audit_records(
                        connection,
                        failure_audit
                    )
            except Exception:
                logger.exception(
                    "Unable to save failure audit "
                    "for customer %s",
                    customer_id
                )

    return successful, failed


# ============================================================
# 11. PROCESS INSERT / UPDATE BATCHES
# ============================================================

def process_action_batches(
    run_id,
    customer_ids,
    action,
    tables,
    batch_size=BATCH_SIZE
):
    """
    Process customer IDs in batches.

    On batch failure:
        1. Roll back entire batch
        2. Retry records individually
        3. Record individual failures
    """

    successful = 0
    failed = 0

    for batch_number, batch_ids in enumerate(
        split_into_batches(customer_ids, batch_size),
        start=1
    ):

        logger.info(
            "Processing %s batch %d: %d customers",
            action,
            batch_number,
            len(batch_ids)
        )

        try:
            execute_batch(
                run_id,
                batch_ids,
                action,
                tables
            )

            successful += len(batch_ids)

        except Exception:

            logger.exception(
                "%s batch %d failed; retrying individually",
                action,
                batch_number
            )

            batch_success, batch_failed = (
                process_failed_batch_individually(
                    run_id,
                    batch_ids,
                    action,
                    tables
                )
            )

            successful += batch_success
            failed += batch_failed

    return successful, failed


# ============================================================
# 12. PROCESS SKIPPED RECORDS
# ============================================================

def process_skipped_records(
    run_id,
    customer_ids,
    batch_size=BATCH_SIZE
):
    """Audit unchanged records without modifying business data."""

    skipped = 0

    for batch_ids in split_into_batches(
        customer_ids,
        batch_size
    ):

        records = create_audit_records(
            run_id,
            batch_ids,
            "SKIP",
            "SUCCESS",
            "Unchanged customer record"
        )

        with get_engine().begin() as connection:
            save_audit_records(connection, records)

        skipped += len(batch_ids)

    return skipped


# ============================================================
# 13. MAIN BATCH LOAD FUNCTION
# ============================================================

def load_incremental_batch(
    run_id,
    incremental_result,
    batch_size=BATCH_SIZE
):
    """
    Load incremental data using configurable batch processing.

    Returns:
        inserted_count
        updated_count
        skipped_count
        failed_count
    """

    if batch_size <= 0:
        raise ValueError("Batch size must be positive")

    classification = incremental_result["classification"]

    insert_tables = incremental_result["insert_tables"]
    update_tables = incremental_result["update_tables"]

    insert_ids = classification.loc[
        classification["action"] == "INSERT",
        "customer_id"
    ].astype(int).tolist()

    update_ids = classification.loc[
        classification["action"] == "UPDATE",
        "customer_id"
    ].astype(int).tolist()

    skip_ids = classification.loc[
        classification["action"] == "SKIP",
        "customer_id"
    ].astype(int).tolist()

    counts = {
        "inserted_count": 0,
        "updated_count": 0,
        "skipped_count": 0,
        "failed_count": 0
    }

    logger.info(
        "Starting batch load: run_id=%s, batch_size=%d",
        run_id,
        batch_size
    )

    # --------------------------------------------------------
    # INSERT batches
    # --------------------------------------------------------

    inserted, insert_failed = process_action_batches(
        run_id,
        insert_ids,
        "INSERT",
        insert_tables,
        batch_size
    )

    counts["inserted_count"] = inserted
    counts["failed_count"] += insert_failed

    # --------------------------------------------------------
    # UPDATE batches
    # --------------------------------------------------------

    updated, update_failed = process_action_batches(
        run_id,
        update_ids,
        "UPDATE",
        update_tables,
        batch_size
    )

    counts["updated_count"] = updated
    counts["failed_count"] += update_failed

    # --------------------------------------------------------
    # SKIP batches
    # --------------------------------------------------------

    counts["skipped_count"] = process_skipped_records(
        run_id,
        skip_ids,
        batch_size
    )

    # --------------------------------------------------------
    # Save run counts
    # --------------------------------------------------------

    update_etl_run_counts(
        run_id,
        counts
    )

    logger.info(
        "Batch load completed: %s",
        counts
    )

    return counts