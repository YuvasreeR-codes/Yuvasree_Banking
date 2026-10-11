"""Unit tests for etl/reconciliation.py (no real MySQL access)."""
from contextlib import nullcontext
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.etl import reconciliation as rec


@pytest.fixture
def run():
    return {
        'source_count': 4, 'valid_count': 3, 'rejected_count': 1,
        'new_count': 1, 'duplicate_count': 1, 'correction_count': 1,
        'inserted_count': 1, 'updated_count': 1, 'skipped_count': 1,
        'failed_count': 0,
    }


@pytest.fixture
def classification():
    return pd.DataFrame({
        'customer_id': [1, 2, 3],
        'record_hash': ['hash1', 'hash2', 'hash3'],
        'action': ['INSERT', 'UPDATE', 'SKIP'],
    })


@pytest.fixture
def audit_df():
    return pd.DataFrame([
        {'customer_id': 1, 'action': 'INSERT', 'status': 'SUCCESS', 'reason': 'Inserted'},
        {'customer_id': 2, 'action': 'UPDATE', 'status': 'SUCCESS', 'reason': 'Updated'},
        {'customer_id': 3, 'action': 'SKIP', 'status': 'SUCCESS', 'reason': 'Unchanged'},
        {'customer_id': None, 'action': 'REJECT', 'status': 'REJECTED', 'reason': 'Bad ID'},
    ])


@pytest.fixture
def db_records():
    return {
        i: {'record_hash': f'hash{i}', 'credit_profiles': 1, 'bills': 6, 'payments': 6}
        for i in (1, 2, 3)
    }


def test_chunk_ids():
    assert list(rec.chunk_ids([1, 2, 3, 4, 5], 2)) == [[1, 2], [3, 4], [5]]


def test_chunk_ids_empty():
    assert list(rec.chunk_ids([], 2)) == []


def test_get_etl_run_found(run):
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = run
    assert rec.get_etl_run('run-1', conn) == run
    assert conn.execute.call_args.args[1] == {'run_id': 'run-1'}


def test_get_etl_run_missing():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.first.return_value = None
    with pytest.raises(ValueError, match='ETL run not found'):
        rec.get_etl_run('missing', conn)


def test_reconcile_counts_valid(run):
    assert rec.reconcile_counts(run) == []


@pytest.mark.parametrize('field,value,message', [
    ('source_count', 5, 'Source count mismatch'),
    ('new_count', 2, 'Incremental classification count mismatch'),
    ('inserted_count', 0, 'Load outcome count mismatch'),
    ('failed_count', 1, 'failed loading'),
])
def test_reconcile_counts_mismatch(run, field, value, message):
    run[field] = value
    assert any(message in error for error in rec.reconcile_counts(run))


def test_get_record_audit():
    conn = MagicMock()
    rows = [{'customer_id': 1, 'action': 'INSERT', 'status': 'SUCCESS', 'reason': 'ok'}]
    conn.execute.return_value.mappings.return_value.all.return_value = rows
    result = rec.get_record_audit('r1', conn)
    assert result.to_dict('records') == rows
    assert conn.execute.call_args.args[1] == {'run_id': 'r1'}


def test_get_record_audit_empty():
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value.all.return_value = []
    result = rec.get_record_audit('r1', conn)
    assert result.empty
    assert list(result.columns) == ['customer_id', 'action', 'status', 'reason']


def test_reconcile_audit_valid(run, audit_df, classification):
    assert rec.reconcile_audit(run, audit_df, classification, 1) == []


@pytest.mark.parametrize('action', ['INSERT', 'UPDATE', 'SKIP'])
def test_reconcile_audit_missing_success(run, audit_df, classification, action):
    modified = audit_df[audit_df['action'] != action].copy()
    errors = rec.reconcile_audit(run, modified, classification, 1)
    assert any(f'{action} audit mismatch' in e for e in errors)


def test_reconcile_audit_failed_count(run, audit_df, classification):
    run['failed_count'] = 1
    assert 'Failed audit count mismatch' in rec.reconcile_audit(run, audit_df, classification, 1)


def test_reconcile_audit_rejected_count(run, audit_df, classification):
    errors = rec.reconcile_audit(run, audit_df, classification, 2)
    assert any('Rejected audit count mismatch' in e for e in errors)


def test_reconcile_audit_duplicate_entry(run, audit_df, classification):
    modified = pd.concat([audit_df, audit_df.iloc[[0]]], ignore_index=True)
    errors = rec.reconcile_audit(run, modified, classification, 1)
    assert any('exactly one final audit record' in e for e in errors)


def test_reconcile_audit_unexpected_customer(run, audit_df, classification):
    extra = pd.DataFrame([{'customer_id': 99, 'action': 'INSERT', 'status': 'SUCCESS', 'reason': 'extra'}])
    modified = pd.concat([audit_df, extra], ignore_index=True)
    errors = rec.reconcile_audit(run, modified, classification, 1)
    assert any('Unexpected customer IDs' in e for e in errors)


def test_fetch_database_records_empty():
    conn = MagicMock()
    assert rec.fetch_database_records([], conn) == {}
    conn.execute.assert_not_called()


def test_fetch_database_records_rows():
    conn = MagicMock()
    rows = [{'customer_id': 1, 'record_hash': 'hash1', 'credit_profiles': 1, 'bills': 6, 'payments': 6}]
    conn.execute.return_value.mappings.return_value = rows
    result = rec.fetch_database_records([1], conn)
    assert result[1]['record_hash'] == 'hash1'
    assert result[1]['bills'] == 6
    assert conn.execute.call_args.args[1] == {'customer_ids': [1]}


def test_fetch_database_records_chunking(monkeypatch):
    conn = MagicMock()
    conn.execute.return_value.mappings.return_value = []
    monkeypatch.setattr(rec, 'chunk_ids', lambda ids: iter([[1, 2], [3]]))
    rec.fetch_database_records([1, 2, 3], conn)
    assert conn.execute.call_count == 2
    assert conn.execute.call_args_list[0].args[1] == {'customer_ids': [1, 2]}
    assert conn.execute.call_args_list[1].args[1] == {'customer_ids': [3]}


def test_reconcile_database_valid(monkeypatch, classification, audit_df, db_records):
    monkeypatch.setattr(rec, 'fetch_database_records', lambda ids, conn: db_records)
    assert rec.reconcile_database(classification, audit_df, MagicMock()) == []


@pytest.mark.parametrize('change,expected', [
    ({'record_hash': 'different'}, 'Record hash mismatch'),
    ({'credit_profiles': 0}, 'expected 1 credit profile'),
    ({'bills': 5}, 'expected 6 bills'),
    ({'payments': 4}, 'expected 6 payments'),
])
def test_reconcile_database_bad_record(monkeypatch, classification, audit_df, db_records, change, expected):
    db_records[1].update(change)
    monkeypatch.setattr(rec, 'fetch_database_records', lambda ids, conn: db_records)
    errors = rec.reconcile_database(classification, audit_df, MagicMock())
    assert any(expected in e for e in errors)


def test_reconcile_database_missing_customer(monkeypatch, classification, audit_df, db_records):
    del db_records[2]
    monkeypatch.setattr(rec, 'fetch_database_records', lambda ids, conn: db_records)
    errors = rec.reconcile_database(classification, audit_df, MagicMock())
    assert any('Customer 2 missing from MySQL' in e for e in errors)


def test_reconcile_database_ignores_rejected(monkeypatch, classification, audit_df):
    seen = []
    def fetch(ids, conn):
        seen.extend(ids)
        return {i: {'record_hash': f'hash{i}', 'credit_profiles': 1, 'bills': 6, 'payments': 6} for i in ids}
    monkeypatch.setattr(rec, 'fetch_database_records', fetch)
    rec.reconcile_database(classification, audit_df, MagicMock())
    assert seen == [1, 2, 3]


@pytest.mark.parametrize('passed,expected_status,expected_reconciliation', [
    (True, 'SUCCESS', 'PASSED'),
    (False, 'FAILED', 'FAILED'),
])
def test_save_reconciliation_result(monkeypatch, passed, expected_status, expected_reconciliation):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value = nullcontext(conn)
    monkeypatch.setattr(rec, 'get_engine', lambda: engine)
    rec.save_reconciliation_result('r1', passed, [] if passed else ['Mismatch'])
    params = conn.execute.call_args.args[1]
    assert params['run_id'] == 'r1'
    assert params['status'] == expected_status
    assert params['reconciliation_status'] == expected_reconciliation
    assert params['error_message'] == (None if passed else 'Mismatch')


def test_save_reconciliation_truncates_errors(monkeypatch):
    conn = MagicMock()
    engine = MagicMock()
    engine.begin.return_value = nullcontext(conn)
    monkeypatch.setattr(rec, 'get_engine', lambda: engine)
    rec.save_reconciliation_result('r1', False, ['x' * 6000])
    assert len(conn.execute.call_args.args[1]['error_message']) == 5000


@pytest.mark.parametrize('errors,expected_passed', [([], True), (['bad count'], False)])
def test_reconcile_etl_run(monkeypatch, run, classification, audit_df, errors, expected_passed):
    conn = MagicMock()
    engine = MagicMock()
    engine.connect.return_value = nullcontext(conn)
    monkeypatch.setattr(rec, 'get_engine', lambda: engine)
    monkeypatch.setattr(rec, 'get_etl_run', lambda rid, c: run)
    monkeypatch.setattr(rec, 'get_record_audit', lambda rid, c: audit_df)
    monkeypatch.setattr(rec, 'reconcile_counts', lambda r: errors)
    monkeypatch.setattr(rec, 'reconcile_audit', lambda *args: [])
    monkeypatch.setattr(rec, 'reconcile_database', lambda *args: [])
    saved = []
    monkeypatch.setattr(rec, 'save_reconciliation_result', lambda *args: saved.append(args))
    result = rec.reconcile_etl_run('r1', {'classification': classification}, 1)
    assert result['passed'] is expected_passed
    assert result['status'] == ('SUCCESS' if expected_passed else 'FAILED')
    assert result['errors'] == errors
    assert saved == [('r1', expected_passed, errors)]
