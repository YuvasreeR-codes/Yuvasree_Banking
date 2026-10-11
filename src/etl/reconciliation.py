import logging
from datetime import datetime

import pandas as pd
from sqlalchemy import text, bindparam

from src.db.connection import get_engine


logger = logging.getLogger(__name__)


# ============================================================
# 1. HELPER: SPLIT CUSTOMER IDS INTO CHUNKS
# ============================================================

def chunk_ids(customer_ids, chunk_size=500):
    """
    Split customer IDs into smaller groups for SQL queries.
    """

    customer_ids = list(customer_ids)

    for start in range(0, len(customer_ids), chunk_size):
        yield customer_ids[start:start + chunk_size]


# ============================================================
# 2. FETCH ETL RUN DETAILS
# ============================================================

def get_etl_run(run_id, connection):
    """
    Retrieve ETL run metadata and processing counts.
    """

    query = text("""
        SELECT *
        FROM etl_runs
        WHERE run_id = :run_id
    """)

    result = connection.execute(
        query,
        {"run_id": run_id}
    ).mappings().first()

    if result is None:
        raise ValueError(
            f"ETL run not found: {run_id}"
        )

    return dict(result)


# ============================================================
# 3. COUNT RECONCILIATION
# ============================================================

def reconcile_counts(run):
    """
    Verify source counts and processing counts.

    Returns a list of reconciliation errors.
    """

    errors = []

    source_count = run["source_count"]
    valid_count = run["valid_count"]
    rejected_count = run["rejected_count"]

    inserted_count = run["inserted_count"]
    updated_count = run["updated_count"]
    skipped_count = run["skipped_count"]
    failed_count = run["failed_count"]

    new_count = run["new_count"]
    duplicate_count = run["duplicate_count"]
    correction_count = run["correction_count"]

    # Source = valid + rejected
    if source_count != valid_count + rejected_count:
        errors.append(
            "Source count mismatch: "
            f"{source_count} != "
            f"{valid_count} + {rejected_count}"
        )

    # Valid records must be classified.
    if valid_count != (
        new_count
        + duplicate_count
        + correction_count
    ):
        errors.append(
            "Incremental classification count mismatch"
        )

    # Every valid record must have a final load outcome.
    if valid_count != (
        inserted_count
        + updated_count
        + skipped_count
        + failed_count
    ):
        errors.append(
            "Load outcome count mismatch"
        )

    # Reconciliation cannot pass if loading failed.
    if failed_count > 0:
        errors.append(
            f"{failed_count} customer records failed loading"
        )

    return errors


# ============================================================
# 4. FETCH RECORD-LEVEL AUDIT DATA
# ============================================================

def get_record_audit(run_id, connection):
    """
    Retrieve audit records for the ETL run.
    """

    query = text("""
        SELECT
            customer_id,
            action,
            status,
            reason
        FROM etl_record_audit
        WHERE run_id = :run_id
    """)

    result = connection.execute(
        query,
        {"run_id": run_id}
    ).mappings().all()

    return pd.DataFrame(
        [dict(row) for row in result],
        columns=[
            "customer_id",
            "action",
            "status",
            "reason"
        ]
    )


# ============================================================
# 5. AUDIT RECONCILIATION
# ============================================================

def reconcile_audit(
    run,
    audit_df,
    classification,
    rejected_count
):
    """
    Verify record-level audit completeness.

    classification:
        Output from incremental.py containing:
        customer_id, record_hash, action

    Rejected records are checked by count because some
    rejected rows may have invalid or missing customer IDs.
    """

    errors = []

    # --------------------------------------------------------
    # Check successful INSERT/UPDATE/SKIP audit counts
    # --------------------------------------------------------

    expected_actions = {
        "INSERT": run["inserted_count"],
        "UPDATE": run["updated_count"],
        "SKIP": run["skipped_count"],
    }

    for action, expected_count in expected_actions.items():

        actual_count = len(
            audit_df[
                (audit_df["action"] == action)
                & (audit_df["status"] == "SUCCESS")
            ]
        )

        if actual_count != expected_count:
            errors.append(
                f"{action} audit mismatch: "
                f"expected {expected_count}, "
                f"found {actual_count}"
            )

    # --------------------------------------------------------
    # Check failed audit count
    # --------------------------------------------------------

    actual_failed = len(
        audit_df[
            audit_df["status"] == "FAILED"
        ]
    )

    if actual_failed != run["failed_count"]:
        errors.append(
            "Failed audit count mismatch"
        )

    # --------------------------------------------------------
    # Check rejected record audit count
    # --------------------------------------------------------

    actual_rejected = len(
        audit_df[
            audit_df["action"] == "REJECT"
        ]
    )

    if actual_rejected != rejected_count:
        errors.append(
            "Rejected audit count mismatch: "
            f"expected {rejected_count}, "
            f"found {actual_rejected}"
        )

    # --------------------------------------------------------
    # Check each valid customer has exactly one audit entry
    # --------------------------------------------------------

    valid_audits = audit_df[
        audit_df["action"].isin([
            "INSERT",
            "UPDATE",
            "SKIP"
        ])
    ]

    audit_counts = (
        valid_audits
        .groupby("customer_id")
        .size()
        .to_dict()
    )

    for customer_id in classification["customer_id"]:

        if audit_counts.get(customer_id, 0) != 1:
            errors.append(
                f"Customer {customer_id} does not have "
                "exactly one final audit record"
            )

    # --------------------------------------------------------
    # Detect unexpected audited customer IDs
    # --------------------------------------------------------

    expected_ids = set(
        classification["customer_id"].astype(int)
    )

    actual_ids = set(
        valid_audits["customer_id"].dropna().astype(int)
    )

    unexpected_ids = actual_ids - expected_ids

    if unexpected_ids:
        errors.append(
            "Unexpected customer IDs in audit: "
            f"{sorted(unexpected_ids)}"
        )

    return errors


# ============================================================
# 6. FETCH DATABASE STATE FOR CUSTOMERS
# ============================================================

def fetch_database_records(customer_ids, connection):
    """
    Fetch customer hashes and related table counts.

    Returns:
        {
            customer_id: {
                record_hash,
                credit_profiles,
                bills,
                payments
            }
        }
    """

    database_records = {}

    if not customer_ids:
        return database_records

    query = text("""
        SELECT
            c.customer_id,
            c.record_hash,
            COUNT(DISTINCT cp.customer_id) AS credit_profiles,
            COUNT(DISTINCT b.bill_id) AS bills,
            COUNT(DISTINCT p.payment_id) AS payments
        FROM customers c
        LEFT JOIN credit_profiles cp
            ON c.customer_id = cp.customer_id
        LEFT JOIN bills b
            ON c.customer_id = b.customer_id
        LEFT JOIN payments p
            ON c.customer_id = p.customer_id
        WHERE c.customer_id IN :customer_ids
        GROUP BY c.customer_id, c.record_hash
    """).bindparams(
        bindparam("customer_ids", expanding=True)
    )

    for batch in chunk_ids(customer_ids):

        rows = connection.execute(
            query,
            {"customer_ids": batch}
        ).mappings()

        for row in rows:

            customer_id = int(row["customer_id"])

            database_records[customer_id] = {
                "record_hash": row["record_hash"],
                "credit_profiles": row["credit_profiles"],
                "bills": row["bills"],
                "payments": row["payments"],
            }

    return database_records


# ============================================================
# 7. DATABASE RECONCILIATION
# ============================================================

def reconcile_database(
    classification,
    audit_df,
    connection
):
    """
    Verify committed customer records in MySQL.

    Only successful INSERT/UPDATE/SKIP actions are checked.
    """

    errors = []

    successful_audits = audit_df[
        (audit_df["status"] == "SUCCESS")
        & (
            audit_df["action"].isin([
                "INSERT",
                "UPDATE",
                "SKIP"
            ])
        )
    ]

    successful_ids = (
        successful_audits["customer_id"]
        .dropna()
        .astype(int)
        .unique()
        .tolist()
    )

    database_records = fetch_database_records(
        successful_ids,
        connection
    )

    expected_hashes = dict(
        zip(
            classification["customer_id"].astype(int),
            classification["record_hash"]
        )
    )

    for customer_id in successful_ids:

        db_record = database_records.get(customer_id)

        if db_record is None:
            errors.append(
                f"Customer {customer_id} missing from MySQL"
            )
            continue

        if db_record["record_hash"] != expected_hashes.get(
            customer_id
        ):
            errors.append(
                f"Record hash mismatch for customer {customer_id}"
            )

        if db_record["credit_profiles"] != 1:
            errors.append(
                f"Customer {customer_id}: "
                "expected 1 credit profile"
            )

        if db_record["bills"] != 6:
            errors.append(
                f"Customer {customer_id}: "
                f"expected 6 bills, found {db_record['bills']}"
            )

        if db_record["payments"] != 6:
            errors.append(
                f"Customer {customer_id}: "
                f"expected 6 payments, "
                f"found {db_record['payments']}"
            )

    return errors


# ============================================================
# 8. SAVE RECONCILIATION RESULT
# ============================================================

def save_reconciliation_result(
    run_id,
    passed,
    errors
):
    """
    Update the ETL run with reconciliation result.

    PASSED -> SUCCESS
    FAILED -> FAILED
    """

    reconciliation_status = (
        "PASSED" if passed else "FAILED"
    )

    run_status = (
        "SUCCESS" if passed else "FAILED"
    )

    error_message = (
        None if passed
        else " | ".join(errors)[:5000]
    )

    query = text("""
        UPDATE etl_runs
        SET
            reconciliation_status = :reconciliation_status,
            status = :status,
            end_time = :end_time,
            error_message = :error_message
        WHERE run_id = :run_id
    """)

    with get_engine().begin() as connection:

        connection.execute(
            query,
            {
                "run_id": run_id,
                "reconciliation_status": reconciliation_status,
                "status": run_status,
                "end_time": datetime.now(),
                "error_message": error_message
            }
        )


# ============================================================
# 9. MAIN RECONCILIATION FUNCTION
# ============================================================

def reconcile_etl_run(
    run_id,
    incremental_result,
    rejected_count
):
    """
    Run complete reconciliation.

    Steps:
        1. Count reconciliation
        2. Record-level audit reconciliation
        3. Database reconciliation
        4. Update ETL run status

    Returns:
        {
            run_id,
            status,
            passed,
            errors
        }
    """

    logger.info(
        "Starting reconciliation for run %s",
        run_id
    )

    classification = incremental_result["classification"]

    errors = []

    with get_engine().connect() as connection:

        run = get_etl_run(
            run_id,
            connection
        )

        # ----------------------------------------------------
        # Count reconciliation
        # ----------------------------------------------------

        errors.extend(
            reconcile_counts(run)
        )

        # ----------------------------------------------------
        # Audit reconciliation
        # ----------------------------------------------------

        audit_df = get_record_audit(
            run_id,
            connection
        )

        errors.extend(
            reconcile_audit(
                run,
                audit_df,
                classification,
                rejected_count
            )
        )

        # ----------------------------------------------------
        # Database reconciliation
        # ----------------------------------------------------

        errors.extend(
            reconcile_database(
                classification,
                audit_df,
                connection
            )
        )

    passed = len(errors) == 0

    save_reconciliation_result(
        run_id,
        passed,
        errors
    )

    logger.info(
        "Reconciliation completed. "
        "run_id=%s, passed=%s, errors=%d",
        run_id,
        passed,
        len(errors)
    )

    return {
        "run_id": run_id,
        "status": "SUCCESS" if passed else "FAILED",
        "passed": passed,
        "errors": errors
    }