"""Unit tests for etl.load; all database interactions are mocked."""
from contextlib import contextmanager
from unittest.mock import MagicMock

import numpy as np
import pandas as pd
import pytest

from src.etl import load as ld


@pytest.fixture
def tables():
    ids = [1, 2]
    customers = pd.DataFrame([{
        **{col: None for col in ld.TABLE_COLUMNS['customers']},
        'customer_id': i, 'record_hash': f'hash-{i}'
    } for i in ids])
    profiles = pd.DataFrame([{
        **{col: 0 for col in ld.TABLE_COLUMNS['credit_profiles']},
        'customer_id': i
    } for i in ids])
    bills = pd.DataFrame([{'customer_id': i, 'month': m, 'bill_amount': 100}
                          for i in ids for m in range(1, 7)])
    payments = pd.DataFrame([{'customer_id': i, 'month': m, 'payment_amount': 10}
                             for i in ids for m in range(1, 7)])
    return dict(customers=customers, credit_profiles=profiles,
                bills=bills, payments=payments)


@pytest.fixture
def mock_db(monkeypatch):
    connection = MagicMock()
    engine = MagicMock()
    @contextmanager
    def begin():
        yield connection
    engine.begin.side_effect = begin
    monkeypatch.setattr(ld, 'get_engine', lambda: engine)
    return connection


def test_to_sql_value_none_and_nan():
    assert ld.to_sql_value(None) is None
    assert ld.to_sql_value(np.nan) is None
    assert ld.to_sql_value(pd.NA) is None


def test_to_sql_value_numpy_scalar():
    assert ld.to_sql_value(np.int64(7)) == 7
    assert isinstance(ld.to_sql_value(np.int64(7)), int)


def test_dataframe_to_records():
    df = pd.DataFrame({'customer_id': [1], 'amount': [np.nan]})
    assert ld.dataframe_to_records(df) == [{'customer_id': 1, 'amount': None}]


@pytest.mark.parametrize('name', list(ld.TABLE_COLUMNS))
def test_insert_query(name):
    query = str(ld.build_insert_query(name))
    assert f'INSERT INTO `{name}`' in query
    for col in ld.TABLE_COLUMNS[name]:
        assert f':{col}' in query


@pytest.mark.parametrize('name', ['customers', 'credit_profiles'])
def test_update_query(name):
    query = str(ld.build_update_query(name))
    assert f'UPDATE `{name}`' in query
    assert 'WHERE customer_id = :customer_id' in query
    assert '`customer_id` =' not in query


@pytest.mark.parametrize('name', ['bills', 'payments'])
def test_update_query_rejects_child_tables(name):
    with pytest.raises(ValueError, match='Unsupported update table'):
        ld.build_update_query(name)


def test_split_batches():
    assert list(ld.split_into_batches([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_split_batches_empty():
    assert list(ld.split_into_batches([], 2)) == []


def test_split_batches_invalid_size():
    with pytest.raises(ValueError, match='Batch size'):
        list(ld.split_into_batches([1], 0))


def test_filter_batch_tables(tables):
    result = ld.filter_batch_tables(tables, [2])
    assert all(set(df.customer_id) == {2} for df in result.values())
    assert len(result['bills']) == 6
    assert len(tables['bills']) == 12


def test_validate_batch_tables_success(tables):
    ld.validate_batch_tables(tables, [1, 2])


def test_validate_batch_tables_bad_count(tables):
    tables['bills'] = tables['bills'].iloc[:-1]
    with pytest.raises(ValueError, match='bills: expected 12 rows'):
        ld.validate_batch_tables(tables, [1, 2])


def test_validate_batch_tables_wrong_customer_ids(tables):
    tables['customers'].loc[0, 'customer_id'] = 99
    with pytest.raises(ValueError, match='customer IDs do not match'):
        ld.validate_batch_tables(tables, [1, 2])


def test_validate_batch_tables_duplicate_month(tables):
    tables['payments'].loc[0, 'month'] = tables['payments'].loc[1, 'month']
    with pytest.raises(ValueError, match='duplicate customer/month'):
        ld.validate_batch_tables(tables, [1, 2])


def test_bulk_insert_four_tables(tables):
    conn = MagicMock()
    ld.bulk_insert(conn, tables)
    assert conn.execute.call_count == 4
    assert [len(c.args[1]) for c in conn.execute.call_args_list] == [2, 2, 12, 12]


def test_bulk_insert_empty_tables(tables):
    conn = MagicMock()
    empty = {name: df.iloc[:0] for name, df in tables.items()}
    ld.bulk_insert(conn, empty)
    conn.execute.assert_not_called()


def test_bulk_update_replaces_children(tables):
    conn = MagicMock()
    ld.bulk_update(conn, tables)
    queries = [str(call.args[0]) for call in conn.execute.call_args_list]
    assert sum(q.startswith('UPDATE') for q in queries) == 2
    assert sum(q.startswith('DELETE') for q in queries) == 4
    assert sum(q.startswith('INSERT') for q in queries) == 2


def test_create_etl_run(mock_db):
    ld.create_etl_run('run1', 'source.xls', 2, 2, 0, 1, 1, 0)
    query, params = mock_db.execute.call_args.args
    assert 'INSERT INTO etl_runs' in str(query)
    assert params['run_id'] == 'run1'
    assert params['source_count'] == 2


def test_update_etl_run_counts(mock_db):
    counts = dict(inserted_count=1, updated_count=2, skipped_count=3, failed_count=0)
    ld.update_etl_run_counts('run1', counts)
    assert mock_db.execute.call_args.args[1] == {'run_id': 'run1', **counts}


def test_save_issues_empty(mock_db):
    ld.save_data_quality_issues('run1', pd.DataFrame())
    mock_db.execute.assert_not_called()


def test_save_issues_normalizes_invalid_id(mock_db):
    issues = pd.DataFrame([dict(customer_id='bad', check_name='INVALID_CUSTOMER_ID',
                                column_name='customer_id', invalid_value='x' * 300,
                                reason='r' * 600)])
    ld.save_data_quality_issues('run1', issues)
    records = mock_db.execute.call_args.args[1]
    assert records[0]['customer_id'] is None
    assert len(records[0]['invalid_value']) == 255
    assert len(records[0]['reason']) == 500


def test_save_rejected_audits(mock_db):
    rejected = pd.DataFrame([{'customer_id': 'bad', 'rejection_reason': 'Invalid ID'},
                             {'customer_id': 3, 'rejection_reason': 'Invalid age'}])
    ld.save_rejected_record_audits('run1', rejected)
    records = mock_db.execute.call_args.args[1]
    assert [r['customer_id'] for r in records] == [None, 3]
    assert all(r['action'] == 'REJECT' and r['status'] == 'REJECTED' for r in records)


def test_create_audit_records():
    records = ld.create_audit_records('run1', [1, 2], 'INSERT', 'SUCCESS', 'ok')
    assert len(records) == 2
    assert records[0]['customer_id'] == 1
    assert records[1]['status'] == 'SUCCESS'


def test_save_audit_records_empty():
    conn = MagicMock()
    ld.save_audit_records(conn, [])
    conn.execute.assert_not_called()


@pytest.mark.parametrize('action,handler', [('INSERT', 'bulk_insert'), ('UPDATE', 'bulk_update')])
def test_execute_batch_action(tables, mock_db, monkeypatch, action, handler):
    operation = MagicMock()
    monkeypatch.setattr(ld, handler, operation)
    ld.execute_batch('run1', [1], action, tables)
    operation.assert_called_once()
    assert mock_db.execute.call_count == 1  # success audit
    records = mock_db.execute.call_args.args[1]
    assert records[0]['action'] == action


def test_execute_batch_invalid_action(tables, mock_db):
    with pytest.raises(ValueError, match='Unsupported batch action'):
        ld.execute_batch('run1', [1], 'SKIP', tables)
    mock_db.execute.assert_not_called()


def test_execute_batch_invalid_tables_before_transaction(tables, mock_db):
    tables['bills'] = tables['bills'].iloc[:-1]
    with pytest.raises(ValueError, match='bills: expected 6 rows'):
        ld.execute_batch('run1', [2], 'INSERT', tables)
    mock_db.execute.assert_not_called()


def test_retry_individually(tables, mock_db, monkeypatch):
    def execute(run_id, ids, action, all_tables):
        if ids == [2]:
            raise RuntimeError('write failed')
    monkeypatch.setattr(ld, 'execute_batch', execute)
    assert ld.process_failed_batch_individually('run1', [1, 2], 'INSERT', tables) == (1, 1)
    records = mock_db.execute.call_args.args[1]
    assert records[0]['customer_id'] == 2
    assert records[0]['status'] == 'FAILED'


def test_process_action_batches_success(tables, monkeypatch):
    execute = MagicMock()
    monkeypatch.setattr(ld, 'execute_batch', execute)
    assert ld.process_action_batches('run1', [1, 2], 'INSERT', tables, 1) == (2, 0)
    assert execute.call_count == 2


def test_process_action_batches_fallback(tables, monkeypatch):
    monkeypatch.setattr(ld, 'execute_batch', MagicMock(side_effect=RuntimeError('batch failed')))
    fallback = MagicMock(return_value=(1, 1))
    monkeypatch.setattr(ld, 'process_failed_batch_individually', fallback)
    assert ld.process_action_batches('run1', [1, 2], 'INSERT', tables, 2) == (1, 1)
    fallback.assert_called_once()


def test_process_skipped_records(mock_db):
    assert ld.process_skipped_records('run1', [1, 2, 3], batch_size=2) == 3
    assert mock_db.execute.call_count == 2
    assert all(r['action'] == 'SKIP' for r in mock_db.execute.call_args.args[1])


def test_load_incremental_batch_counts(monkeypatch, tables):
    classification = pd.DataFrame({'customer_id': [1, 2, 3],
                                   'action': ['INSERT', 'UPDATE', 'SKIP']})
    calls = []
    def action_batches(run_id, ids, action, data, size):
        calls.append((action, ids, size))
        return len(ids), 0
    monkeypatch.setattr(ld, 'process_action_batches', action_batches)
    monkeypatch.setattr(ld, 'process_skipped_records', lambda *args: 1)
    save_counts = MagicMock()
    monkeypatch.setattr(ld, 'update_etl_run_counts', save_counts)
    result = ld.load_incremental_batch('run1', {
        'classification': classification,
        'insert_tables': tables,
        'update_tables': tables,
    }, batch_size=2)
    assert result == dict(inserted_count=1, updated_count=1, skipped_count=1, failed_count=0)
    assert calls == [('INSERT', [1], 2), ('UPDATE', [2], 2)]
    save_counts.assert_called_once_with('run1', result)


def test_load_incremental_batch_invalid_size():
    with pytest.raises(ValueError, match='Batch size must be positive'):
        ld.load_incremental_batch('run1', {}, batch_size=0)
