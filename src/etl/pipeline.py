import logging
import shutil
from datetime import datetime
from pathlib import Path
from uuid import uuid4

import pandas as pd
from sqlalchemy import text

from src.config import BATCH_SIZE
from src.db.connection import get_engine

from src.etl.extract import extract_data
from src.etl.data_quality import run_data_quality_checks
from src.etl.transform import transform_data
from src.etl.incremental import process_incremental_batch

from src.etl.load import (
    create_etl_run,
    save_data_quality_issues,
    save_rejected_record_audits,
    load_incremental_batch
)

from src.etl.reconciliation import reconcile_etl_run


# ============================================================
# 1. DIRECTORY CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent

DATA_DIR = BASE_DIR / "data"

INCOMING_DIR = DATA_DIR / "incoming"
PROCESSED_DIR = DATA_DIR / "processed"
REJECTED_DIR = DATA_DIR / "rejected"
ARCHIVE_DIR = DATA_DIR / "archive"

LOG_DIR = BASE_DIR / "logs"

for directory in (
    INCOMING_DIR,
    PROCESSED_DIR,
    REJECTED_DIR,
    ARCHIVE_DIR,
    LOG_DIR
):
    directory.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# 2. LOGGING CONFIGURATION
# ============================================================

LOG_FILE = LOG_DIR / "etl_pipeline.log"

logger = logging.getLogger("bank_loan_etl")

logger.setLevel(logging.INFO)

if not logger.handlers:

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | "
        "%(name)s | %(message)s"
    )

    file_handler = logging.FileHandler(
        LOG_FILE,
        encoding="utf-8"
    )

    file_handler.setFormatter(formatter)

    console_handler = logging.StreamHandler()

    console_handler.setFormatter(formatter)

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)


# ============================================================
# 3. GENERATE ETL RUN ID
# ============================================================

def generate_run_id():
    """
    Generate a unique ETL execution identifier.
    """

    timestamp = datetime.now().strftime(
        "%Y%m%d_%H%M%S"
    )

    unique_part = uuid4().hex[:8]

    return f"ETL_{timestamp}_{unique_part}"


# ============================================================
# 4. EXPORT REJECTED RECORDS
# ============================================================

def export_rejected_records(
    rejected_df,
    run_id
):
    """
    Export rejected records for investigation.
    """

    if rejected_df.empty:
        logger.info(
            "No rejected records for run %s",
            run_id
        )

        return None

    output_path = (
        REJECTED_DIR /
        f"rejected_{run_id}.csv"
    )

    rejected_df.to_csv(
        output_path,
        index=False
    )

    logger.info(
        "Exported %d rejected records to %s",
        len(rejected_df),
        output_path
    )

    return str(output_path)


# ============================================================
# 5. EXPORT CURATED DATA
# ============================================================

def export_curated_tables(
    tables,
    run_id
):
    """
    Save transformed tables as CSV snapshots.

    Useful for debugging and verifying ETL outputs.
    """

    output_dir = PROCESSED_DIR / run_id

    output_dir.mkdir(
        parents=True,
        exist_ok=True
    )

    for table_name, df in tables.items():

        output_path = (
            output_dir /
            f"{table_name}.csv"
        )

        df.to_csv(
            output_path,
            index=False
        )

    logger.info(
        "Curated snapshots exported to %s",
        output_dir
    )

    return str(output_dir)


# ============================================================
# 6. ARCHIVE SOURCE FILE
# ============================================================

def archive_source_file(
    source_file,
    run_id
):
    """
    Move a successfully processed source file
    into the archive directory.
    """

    source_path = Path(source_file)

    archive_name = (
        f"{source_path.stem}_{run_id}"
        f"{source_path.suffix}"
    )

    archive_path = (
        ARCHIVE_DIR /
        archive_name
    )

    shutil.move(
        str(source_path),
        str(archive_path)
    )

    logger.info(
        "Archived source file: %s",
        archive_path
    )

    return str(archive_path)


# ============================================================
# 7. MARK ETL RUN AS FAILED
# ============================================================

def mark_run_failed(
    run_id,
    error_message
):
    """
    Mark an existing ETL run as failed.

    Used when the pipeline raises an unexpected error.
    """

    query = text("""
        UPDATE etl_runs
        SET
            status = 'FAILED',
            reconciliation_status = 'FAILED',
            end_time = :end_time,
            error_message = :error_message
        WHERE run_id = :run_id
    """)

    with get_engine().begin() as connection:

        connection.execute(
            query,
            {
                "run_id": run_id,
                "end_time": datetime.now(),
                "error_message": str(
                    error_message
                )[:5000]
            }
        )


# ============================================================
# 8. ACQUIRE MYSQL ETL LOCK
# ============================================================

def acquire_etl_lock(connection):
    """
    Prevent simultaneous pipeline executions.

    MySQL advisory locks are connection-scoped.
    """

    result = connection.execute(
        text("""
            SELECT GET_LOCK(
                'bank_loan_risk_etl',
                10
            )
        """)
    ).scalar()

    if result != 1:
        raise RuntimeError(
            "Could not acquire ETL lock. "
            "Another pipeline may be running."
        )

    logger.info(
        "ETL execution lock acquired"
    )


def release_etl_lock(connection):
    """
    Release the MySQL advisory lock.
    """

    connection.execute(
        text("""
            SELECT RELEASE_LOCK(
                'bank_loan_risk_etl'
            )
        """)
    )

    logger.info(
        "ETL execution lock released"
    )


# ============================================================
# 9. MAIN ETL PIPELINE
# ============================================================

def run_etl_pipeline(
    source_file,
    batch_size=BATCH_SIZE
):
    """
    Execute the complete Banking Loan Risk ETL pipeline.

    Returns a dictionary containing:
        run_id
        source_file
        source_count
        valid_count
        rejected_count
        load_counts
        reconciliation
        archived_file
        rejected_file
        curated_directory
    """

    source_path = Path(source_file).resolve()

    if not source_path.is_file():
        raise FileNotFoundError(
            f"Source file not found: {source_path}"
        )

    if batch_size <= 0:
        raise ValueError(
            "Batch size must be greater than zero"
        )

    run_id = generate_run_id()

    run_created = False

    logger.info("=" * 65)
    logger.info("Starting Banking Loan Risk ETL")
    logger.info("Run ID: %s", run_id)
    logger.info("Source: %s", source_path)
    logger.info("Batch size: %d", batch_size)
    logger.info("=" * 65)

    # Keep this connection open while the ETL runs.
    # Other modules use their own connections for data loading.
    engine = get_engine()

    with engine.connect() as lock_connection:

        acquire_etl_lock(lock_connection)

        try:

            # ------------------------------------------------
            # STEP 1: EXTRACT
            # ------------------------------------------------

            logger.info("STEP 1: Extracting source data")

            source_df = extract_data(
                source_path
            )

            source_count = len(source_df)

            logger.info(
                "Extracted %d source records",
                source_count
            )

            # ------------------------------------------------
            # STEP 2: DATA QUALITY
            # ------------------------------------------------

            logger.info("STEP 2: Validating source data")

            (
                valid_df,
                rejected_df,
                issues_df
            ) = run_data_quality_checks(
                source_df
            )

            valid_count = len(valid_df)
            rejected_count = len(rejected_df)

            logger.info(
                "Validation completed: "
                "valid=%d, rejected=%d, issues=%d",
                valid_count,
                rejected_count,
                len(issues_df)
            )

            # ------------------------------------------------
            # STEP 3: TRANSFORM
            # ------------------------------------------------

            logger.info("STEP 3: Transforming valid data")

            tables = transform_data(
                valid_df
            )

            logger.info(
                "Transformation completed"
            )

            # ------------------------------------------------
            # STEP 4: INCREMENTAL CLASSIFICATION
            # ------------------------------------------------

            logger.info(
                "STEP 4: Classifying incremental records"
            )

            incremental_result = (
                process_incremental_batch(
                    tables
                )
            )

            summary = incremental_result["summary"]

            logger.info(
                "Incremental classification: %s",
                summary
            )

            # ------------------------------------------------
            # STEP 5: CREATE ETL RUN
            # ------------------------------------------------

            logger.info(
                "STEP 5: Creating ETL run record"
            )

            create_etl_run(
                run_id=run_id,
                source_file=source_path.name,
                source_count=source_count,
                valid_count=valid_count,
                rejected_count=rejected_count,
                new_count=summary["new_count"],
                duplicate_count=summary["duplicate_count"],
                correction_count=summary["correction_count"]
            )

            run_created = True

            # ------------------------------------------------
            # STEP 6: SAVE DATA QUALITY INFORMATION
            # ------------------------------------------------

            logger.info(
                "STEP 6: Recording data-quality issues"
            )

            save_data_quality_issues(
                run_id,
                issues_df
            )

            save_rejected_record_audits(
                run_id,
                rejected_df
            )

            rejected_file = export_rejected_records(
                rejected_df,
                run_id
            )

            # ------------------------------------------------
            # STEP 7: EXPORT CURATED SNAPSHOTS
            # ------------------------------------------------

            logger.info(
                "STEP 7: Exporting curated snapshots"
            )

            curated_directory = export_curated_tables(
                tables,
                run_id
            )

            # ------------------------------------------------
            # STEP 8: BATCH LOAD
            # ------------------------------------------------

            logger.info(
                "STEP 8: Loading MySQL batches"
            )

            load_counts = load_incremental_batch(
                run_id=run_id,
                incremental_result=incremental_result,
                batch_size=batch_size
            )

            logger.info(
                "Batch load completed: %s",
                load_counts
            )

            # ------------------------------------------------
            # STEP 9: RECONCILIATION
            # ------------------------------------------------

            logger.info(
                "STEP 9: Running reconciliation"
            )

            reconciliation = reconcile_etl_run(
                run_id=run_id,
                incremental_result=incremental_result,
                rejected_count=rejected_count
            )

            logger.info(
                "Reconciliation result: %s",
                reconciliation["status"]
            )

            # ------------------------------------------------
            # STEP 10: ARCHIVE SUCCESSFUL SOURCE
            # ------------------------------------------------

            archived_file = None

            if reconciliation["passed"]:

                logger.info(
                    "STEP 10: Archiving source file"
                )

                archived_file = archive_source_file(
                    source_path,
                    run_id
                )

            else:

                logger.error(
                    "Reconciliation failed. "
                    "Source file retained for investigation."
                )

            # ------------------------------------------------
            # STEP 11: RETURN RESULT
            # ------------------------------------------------

            result = {
                "run_id": run_id,
                "source_file": str(source_path),
                "source_count": source_count,
                "valid_count": valid_count,
                "rejected_count": rejected_count,
                "load_counts": load_counts,
                "reconciliation": reconciliation,
                "archived_file": archived_file,
                "rejected_file": rejected_file,
                "curated_directory": curated_directory
            }

            logger.info(
                "Pipeline completed: %s",
                reconciliation["status"]
            )

            return result

        except Exception as exc:

            logger.exception(
                "ETL pipeline failed: %s",
                exc
            )

            if run_created:

                try:
                    mark_run_failed(
                        run_id,
                        str(exc)
                    )

                except Exception:
                    logger.exception(
                        "Unable to update ETL run failure status"
                    )

            raise

        finally:

            try:
                release_etl_lock(
                    lock_connection
                )

            except Exception:
                logger.exception(
                    "Unable to release ETL lock"
                )

if __name__ == "__main__":

    result = run_etl_pipeline(
        source_file="data/incoming/default_of_credit_card_clients.xls",
        batch_size=500
    )

    print(result)

#python -m etl.pipeline