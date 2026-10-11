import logging

import pandas as pd
from sqlalchemy import text

from src.db.connection import get_engine


logger = logging.getLogger(__name__)


# ============================================================
# 1. FETCH EXISTING CUSTOMER HASHES
# ============================================================

def fetch_existing_hashes(customer_ids, connection=None):
    """
    Retrieve existing customer IDs and record hashes
    from the MySQL customers table.

    Only fetch records relevant to the incoming batch.

    Parameters
    ----------
    customer_ids : list
        Customer IDs from the incoming batch.

    connection : SQLAlchemy Connection, optional
        Existing connection supplied by the caller.

    Returns
    -------
    dict
        {customer_id: record_hash}
    """

    customer_ids = [
        int(customer_id)
        for customer_id in set(customer_ids)
    ]

    if not customer_ids:
        return {}

    engine = get_engine()

    existing_hashes = {}

    # Process IDs in chunks to avoid overly large queries.
    chunk_size = 1000

    def execute_queries(conn):

        for start in range(0, len(customer_ids), chunk_size):

            batch_ids = customer_ids[
                start:start + chunk_size
            ]

            # Build named placeholders:
            # :id_0, :id_1, :id_2, ...
            placeholders = []

            parameters = {}

            for index, customer_id in enumerate(batch_ids):

                parameter_name = f"id_{index}"

                placeholders.append(
                    f":{parameter_name}"
                )

                parameters[parameter_name] = customer_id

            query = text(
                """
                SELECT customer_id, record_hash
                FROM customers
                WHERE customer_id IN (
                """
                + ", ".join(placeholders)
                + ")"
            )

            result = conn.execute(
                query,
                parameters
            )

            for row in result.mappings():

                existing_hashes[
                    int(row["customer_id"])
                ] = row["record_hash"]

    if connection is not None:
        execute_queries(connection)
    else:
        with engine.connect() as conn:
            execute_queries(conn)

    logger.info(
        "Found %d existing customers among %d incoming IDs",
        len(existing_hashes),
        len(customer_ids)
    )

    return existing_hashes


# ============================================================
# 2. CLASSIFY INCOMING CUSTOMERS
# ============================================================

def classify_incremental_records(
    customers_df,
    existing_hashes
):
    """
    Classify incoming customer records.

    INSERT:
        Customer ID does not exist in MySQL.

    SKIP:
        Customer ID exists and record_hash is unchanged.

    UPDATE:
        Customer ID exists but record_hash differs.

    Returns
    -------
    pandas.DataFrame
        customer_id, record_hash, action
    """

    required_columns = [
        "customer_id",
        "record_hash"
    ]

    missing_columns = [
        column
        for column in required_columns
        if column not in customers_df.columns
    ]

    if missing_columns:
        raise ValueError(
            f"Missing required columns: {missing_columns}"
        )

    if customers_df["customer_id"].isna().any():
        raise ValueError(
            "customer_id contains missing values"
        )

    if customers_df["record_hash"].isna().any():
        raise ValueError(
            "record_hash contains missing values"
        )

    if customers_df["customer_id"].duplicated().any():
        raise ValueError(
            "Duplicate customer IDs found in valid customers_df"
        )

    result = customers_df[
        ["customer_id", "record_hash"]
    ].copy()

    def determine_action(row):

        customer_id = int(row["customer_id"])

        incoming_hash = row["record_hash"]

        if customer_id not in existing_hashes:
            return "INSERT"

        stored_hash = existing_hashes[customer_id]

        if incoming_hash == stored_hash:
            return "SKIP"

        return "UPDATE"

    result["action"] = result.apply(
        determine_action,
        axis=1
    )

    logger.info(
        "Incremental classification: %s",
        result["action"].value_counts().to_dict()
    )

    return result.reset_index(drop=True)


# ============================================================
# 3. FILTER TRANSFORMED TABLES BY ACTION
# ============================================================

def filter_tables_by_customer_ids(
    tables,
    customer_ids
):
    """
    Filter all four transformed tables using customer IDs.

    Parameters
    ----------
    tables : dict
        Output from transform_data().

    customer_ids : list or set
        Customer IDs to retain.

    Returns
    -------
    dict
        Filtered customers, credit_profiles,
        bills and payments DataFrames.
    """

    customer_ids = set(customer_ids)

    filtered_tables = {}

    for table_name, table_df in tables.items():

        filtered_tables[table_name] = (
            table_df[
                table_df["customer_id"].isin(customer_ids)
            ]
            .copy()
            .reset_index(drop=True)
        )

    return filtered_tables


# ============================================================
# 4. MAIN INCREMENTAL FUNCTION
# ============================================================

def process_incremental_batch(
    tables,
    connection=None
):
    """
    Compare transformed records with MySQL and separate
    INSERT, UPDATE and SKIP records.

    This function does not modify the database.

    Parameters
    ----------
    tables : dict
        Dictionary returned by transform_data().

    connection : SQLAlchemy Connection, optional
        Existing connection for transactional processing.

    Returns
    -------
    dict
        classification
        insert_tables
        update_tables
        skipped_customers
        summary
    """

    logger.info(
        "Starting incremental classification"
    )

    required_tables = {
        "customers",
        "credit_profiles",
        "bills",
        "payments"
    }

    missing_tables = required_tables - set(tables)

    if missing_tables:
        raise ValueError(
            f"Missing transformed tables: {missing_tables}"
        )

    customers_df = tables["customers"]

    customer_ids = (
        customers_df["customer_id"]
        .astype(int)
        .tolist()
    )

    # --------------------------------------------------------
    # Fetch current hashes
    # --------------------------------------------------------

    existing_hashes = fetch_existing_hashes(
        customer_ids,
        connection=connection
    )

    # --------------------------------------------------------
    # Classify customers
    # --------------------------------------------------------

    classification = classify_incremental_records(
        customers_df,
        existing_hashes
    )

    # --------------------------------------------------------
    # Separate customer IDs
    # --------------------------------------------------------

    insert_ids = classification.loc[
        classification["action"] == "INSERT",
        "customer_id"
    ].tolist()

    update_ids = classification.loc[
        classification["action"] == "UPDATE",
        "customer_id"
    ].tolist()

    skip_ids = classification.loc[
        classification["action"] == "SKIP",
        "customer_id"
    ].tolist()

    # --------------------------------------------------------
    # Filter all relational tables
    # --------------------------------------------------------

    insert_tables = filter_tables_by_customer_ids(
        tables,
        insert_ids
    )

    update_tables = filter_tables_by_customer_ids(
        tables,
        update_ids
    )

    skipped_customers = customers_df[
        customers_df["customer_id"].isin(skip_ids)
    ].copy().reset_index(drop=True)

    # --------------------------------------------------------
    # Summary
    # --------------------------------------------------------

    summary = {
        "total_valid_records": len(customers_df),
        "new_count": len(insert_ids),
        "duplicate_count": len(skip_ids),
        "correction_count": len(update_ids)
    }

    if (
        summary["new_count"]
        + summary["duplicate_count"]
        + summary["correction_count"]
        != summary["total_valid_records"]
    ):
        raise ValueError(
            "Incremental classification count mismatch"
        )

    logger.info(
        "Incremental classification completed: %s",
        summary
    )

    return {
        "classification": classification,
        "insert_tables": insert_tables,
        "update_tables": update_tables,
        "skipped_customers": skipped_customers,
        "summary": summary
    }