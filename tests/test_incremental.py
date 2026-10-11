from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.etl import incremental as inc


@pytest.fixture
def customers_df():
    return pd.DataFrame({
        "customer_id": [1, 2, 3],
        "record_hash": ["hash_a", "hash_b", "hash_c"],
    })


@pytest.fixture
def tables(customers_df):
    ids = customers_df["customer_id"].tolist()
    return {
        "customers": customers_df.copy(),
        "credit_profiles": pd.DataFrame({"customer_id": ids, "credit_limit": [10000, 20000, 30000]}),
        "bills": pd.DataFrame({"customer_id": [i for i in ids for _ in range(6)], "bill_amount": [100] * 18}),
        "payments": pd.DataFrame({"customer_id": [i for i in ids for _ in range(6)], "payment_amount": [50] * 18}),
    }


# Database retrieval

def test_fetch_existing_hashes_empty(monkeypatch):
    def unexpected_engine():
        pytest.fail("Database engine must not be created for empty IDs")

    monkeypatch.setattr(inc, "get_engine", unexpected_engine)
    assert inc.fetch_existing_hashes([]) == {}


def test_fetch_existing_hashes_with_connection(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = [
        {"customer_id": 1, "record_hash": "hash_a"},
        {"customer_id": 2, "record_hash": "hash_b"},
    ]
    monkeypatch.setattr(inc, "get_engine", lambda: MagicMock())

    result = inc.fetch_existing_hashes([1, 2, 2], connection=connection)

    assert result == {1: "hash_a", 2: "hash_b"}
    assert connection.execute.call_count == 1
    query, params = connection.execute.call_args.args
    assert "FROM customers" in str(query)
    assert set(params.values()) == {1, 2}


def test_fetch_existing_hashes_uses_engine_connection(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = [
        {"customer_id": 3, "record_hash": "stored"}
    ]
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(inc, "get_engine", lambda: engine)

    assert inc.fetch_existing_hashes([3]) == {3: "stored"}
    engine.connect.assert_called_once()


def test_fetch_existing_hashes_chunks(monkeypatch):
    connection = MagicMock()
    connection.execute.return_value.mappings.return_value = []
    monkeypatch.setattr(inc, "get_engine", lambda: MagicMock())

    assert inc.fetch_existing_hashes(range(1001), connection=connection) == {}
    assert connection.execute.call_count == 2
    assert sorted(len(call.args[1]) for call in connection.execute.call_args_list) == [1, 1000]


# Classification

def test_classify_all_insert(customers_df):
    result = inc.classify_incremental_records(customers_df, {})
    assert result["action"].tolist() == ["INSERT"] * 3


def test_classify_all_skip(customers_df):
    existing = {1: "hash_a", 2: "hash_b", 3: "hash_c"}
    result = inc.classify_incremental_records(customers_df, existing)
    assert result["action"].tolist() == ["SKIP"] * 3


def test_classify_all_update(customers_df):
    existing = {1: "old_a", 2: "old_b", 3: "old_c"}
    result = inc.classify_incremental_records(customers_df, existing)
    assert result["action"].tolist() == ["UPDATE"] * 3


def test_classify_mixed_actions(customers_df):
    result = inc.classify_incremental_records(
        customers_df, {2: "hash_b", 3: "old_c"}
    )
    assert result["action"].tolist() == ["INSERT", "SKIP", "UPDATE"]
    assert list(result.columns) == ["customer_id", "record_hash", "action"]


@pytest.mark.parametrize("missing_column", ["customer_id", "record_hash"])
def test_classify_missing_column(customers_df, missing_column):
    with pytest.raises(ValueError, match="Missing required columns"):
        inc.classify_incremental_records(customers_df.drop(columns=[missing_column]), {})


@pytest.mark.parametrize("column", ["customer_id", "record_hash"])
def test_classify_null_value(customers_df, column):
    customers_df.loc[0, column] = None
    with pytest.raises(ValueError, match=f"{column} contains missing values"):
        inc.classify_incremental_records(customers_df, {})


def test_classify_duplicate_customer_id(customers_df):
    customers_df.loc[1, "customer_id"] = 1
    with pytest.raises(ValueError, match="Duplicate customer IDs"):
        inc.classify_incremental_records(customers_df, {})


def test_classify_does_not_modify_input(customers_df):
    original = customers_df.copy(deep=True)
    inc.classify_incremental_records(customers_df, {})
    pd.testing.assert_frame_equal(customers_df, original)


# Filtering

def test_filter_tables_subset(tables):
    filtered = inc.filter_tables_by_customer_ids(tables, [1, 3])
    assert set(filtered) == set(tables)
    assert filtered["customers"]["customer_id"].tolist() == [1, 3]
    assert len(filtered["credit_profiles"]) == 2
    assert len(filtered["bills"]) == 12
    assert len(filtered["payments"]) == 12


def test_filter_tables_empty_ids(tables):
    filtered = inc.filter_tables_by_customer_ids(tables, [])
    assert all(df.empty for df in filtered.values())


def test_filter_tables_does_not_modify_original(tables):
    original = {name: df.copy(deep=True) for name, df in tables.items()}
    inc.filter_tables_by_customer_ids(tables, [1])
    for name in tables:
        pd.testing.assert_frame_equal(tables[name], original[name])


# End-to-end incremental classification (mocked database lookup)

def test_process_incremental_batch_mixed(monkeypatch, tables):
    def fake_fetch(customer_ids, connection=None):
        assert set(customer_ids) == {1, 2, 3}
        return {2: "hash_b", 3: "previous_hash"}

    monkeypatch.setattr(inc, "fetch_existing_hashes", fake_fetch)
    result = inc.process_incremental_batch(tables)

    assert result["summary"] == {
        "total_valid_records": 3,
        "new_count": 1,
        "duplicate_count": 1,
        "correction_count": 1,
    }
    assert result["classification"]["action"].tolist() == ["INSERT", "SKIP", "UPDATE"]
    assert result["insert_tables"]["customers"]["customer_id"].tolist() == [1]
    assert result["update_tables"]["customers"]["customer_id"].tolist() == [3]
    assert result["skipped_customers"]["customer_id"].tolist() == [2]
    assert len(result["insert_tables"]["bills"]) == 6
    assert len(result["update_tables"]["payments"]) == 6


def test_process_incremental_batch_all_new(monkeypatch, tables):
    monkeypatch.setattr(inc, "fetch_existing_hashes", lambda ids, connection=None: {})
    result = inc.process_incremental_batch(tables)
    assert result["summary"]["new_count"] == 3
    assert result["summary"]["duplicate_count"] == 0
    assert result["summary"]["correction_count"] == 0
    assert result["update_tables"]["customers"].empty
    assert result["skipped_customers"].empty


def test_process_incremental_batch_all_unchanged(monkeypatch, tables):
    hashes = {1: "hash_a", 2: "hash_b", 3: "hash_c"}
    monkeypatch.setattr(inc, "fetch_existing_hashes", lambda ids, connection=None: hashes)
    result = inc.process_incremental_batch(tables)
    assert result["summary"]["duplicate_count"] == 3
    assert result["insert_tables"]["customers"].empty
    assert result["update_tables"]["customers"].empty
    assert len(result["skipped_customers"]) == 3


def test_process_incremental_batch_missing_table(monkeypatch, tables):
    tables.pop("payments")
    monkeypatch.setattr(inc, "fetch_existing_hashes", lambda ids, connection=None: {})
    with pytest.raises(ValueError, match="Missing transformed tables"):
        inc.process_incremental_batch(tables)


def test_process_incremental_batch_passes_connection(monkeypatch, tables):
    connection = object()
    received = []

    def fake_fetch(customer_ids, connection=None):
        received.append(connection)
        return {}

    monkeypatch.setattr(inc, "fetch_existing_hashes", fake_fetch)
    inc.process_incremental_batch(tables, connection=connection)
    assert received == [connection]
