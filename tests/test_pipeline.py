"""Unit tests for etl.pipeline, without a live database or source-file changes."""
from contextlib import nullcontext
from pathlib import Path
from unittest.mock import MagicMock

import pandas as pd
import pytest

from src.etl import pipeline as p


@pytest.fixture
def paths(tmp_path, monkeypatch):
    for name in ('incoming', 'processed', 'rejected', 'archive'):
        path = tmp_path / name
        path.mkdir()
        monkeypatch.setattr(p, name.upper() + '_DIR', path)
    return tmp_path


@pytest.fixture
def source(paths):
    file = paths / 'incoming' / 'customers.csv'
    file.write_text('customer_id\n1\n', encoding='utf-8')
    return file


@pytest.fixture
def workflow(monkeypatch, source):
    """Replace all external stages and the DB engine with controlled doubles."""
    calls = []
    connection = MagicMock()
    engine = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    monkeypatch.setattr(p, 'get_engine', lambda: engine)
    monkeypatch.setattr(p, 'generate_run_id', lambda: 'ETL_TEST_001')
    monkeypatch.setattr(p, 'acquire_etl_lock', lambda conn: calls.append('lock'))
    monkeypatch.setattr(p, 'release_etl_lock', lambda conn: calls.append('unlock'))

    source_df = pd.DataFrame({'customer_id': [1, 2, 3]})
    valid_df = source_df.iloc[:2].copy()
    rejected_df = pd.DataFrame({'customer_id': [3], 'rejection_reason': ['Invalid']})
    issues_df = pd.DataFrame({'customer_id': [3], 'reason': ['Invalid']})
    tables = {name: pd.DataFrame({'customer_id': [1, 2]}) for name in
              ('customers', 'credit_profiles', 'bills', 'payments')}
    classification = pd.DataFrame({
        'customer_id': [1, 2], 'record_hash': ['a', 'b'], 'action': ['INSERT', 'SKIP']
    })
    incremental = {
        'classification': classification,
        'summary': {'new_count': 1, 'duplicate_count': 1, 'correction_count': 0},
    }
    counts = {'inserted_count': 1, 'updated_count': 0,
              'skipped_count': 1, 'failed_count': 0}
    reconciliation = {'status': 'SUCCESS', 'passed': True, 'errors': []}

    def stage(name, value):
        def inner(*args, **kwargs):
            calls.append(name)
            return value
        return inner

    monkeypatch.setattr(p, 'extract_data', stage('extract', source_df))
    monkeypatch.setattr(p, 'run_data_quality_checks',
                        stage('quality', (valid_df, rejected_df, issues_df)))
    monkeypatch.setattr(p, 'transform_data', stage('transform', tables))
    monkeypatch.setattr(p, 'process_incremental_batch', stage('incremental', incremental))
    monkeypatch.setattr(p, 'create_etl_run', stage('create_run', None))
    monkeypatch.setattr(p, 'save_data_quality_issues', stage('save_issues', None))
    monkeypatch.setattr(p, 'save_rejected_record_audits', stage('save_reject_audit', None))
    monkeypatch.setattr(p, 'load_incremental_batch', stage('load', counts))
    monkeypatch.setattr(p, 'reconcile_etl_run', stage('reconcile', reconciliation))
    monkeypatch.setattr(p, 'mark_run_failed', stage('mark_failed', None))
    return {'calls': calls, 'source': source, 'tables': tables,
            'reconciliation': reconciliation, 'counts': counts,
            'connection': connection, 'engine': engine}


def test_run_id_format_and_uniqueness():
    first = p.generate_run_id()
    second = p.generate_run_id()
    assert first.startswith('ETL_')
    assert len(first.split('_')[-1]) == 8
    assert first != second


def test_export_rejected_empty(paths):
    assert p.export_rejected_records(pd.DataFrame(), 'R1') is None
    assert list((paths / 'rejected').iterdir()) == []


def test_export_rejected_rows(paths):
    df = pd.DataFrame({'customer_id': [3], 'rejection_reason': ['Invalid']})
    result = Path(p.export_rejected_records(df, 'R1'))
    assert result == paths / 'rejected' / 'rejected_R1.csv'
    pd.testing.assert_frame_equal(pd.read_csv(result), df)


def test_export_curated_tables(paths):
    tables = {'customers': pd.DataFrame({'customer_id': [1]}),
              'bills': pd.DataFrame({'customer_id': [1], 'month': ['Sep']})}
    result = Path(p.export_curated_tables(tables, 'R1'))
    assert result == paths / 'processed' / 'R1'
    for name, expected in tables.items():
        pd.testing.assert_frame_equal(pd.read_csv(result / f'{name}.csv'), expected)


def test_archive_moves_file(source, paths):
    archived = Path(p.archive_source_file(source, 'R1'))
    assert archived == paths / 'archive' / 'customers_R1.csv'
    assert archived.exists()
    assert not source.exists()


def test_mark_run_failed_truncates_message(monkeypatch):
    connection = MagicMock()
    engine = MagicMock()
    engine.begin.return_value.__enter__.return_value = connection
    monkeypatch.setattr(p, 'get_engine', lambda: engine)
    p.mark_run_failed('R1', 'x' * 6000)
    statement, params = connection.execute.call_args.args
    assert 'UPDATE etl_runs' in str(statement)
    assert params['run_id'] == 'R1'
    assert len(params['error_message']) == 5000
    assert params['end_time'] is not None


def test_acquire_lock_success():
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = 1
    p.acquire_etl_lock(conn)
    assert 'GET_LOCK' in str(conn.execute.call_args.args[0])


@pytest.mark.parametrize('result', [0, None, -1])
def test_acquire_lock_failure(result):
    conn = MagicMock()
    conn.execute.return_value.scalar.return_value = result
    with pytest.raises(RuntimeError, match='Could not acquire ETL lock'):
        p.acquire_etl_lock(conn)


def test_release_lock():
    conn = MagicMock()
    p.release_etl_lock(conn)
    assert 'RELEASE_LOCK' in str(conn.execute.call_args.args[0])


def test_pipeline_missing_file(paths):
    with pytest.raises(FileNotFoundError):
        p.run_etl_pipeline(paths / 'incoming' / 'missing.csv')


@pytest.mark.parametrize('batch_size', [0, -1])
def test_pipeline_invalid_batch_size(source, batch_size):
    with pytest.raises(ValueError, match='Batch size'):
        p.run_etl_pipeline(source, batch_size=batch_size)


def test_pipeline_success(workflow, paths):
    result = p.run_etl_pipeline(workflow['source'], batch_size=7)
    assert result['run_id'] == 'ETL_TEST_001'
    assert (result['source_count'], result['valid_count'], result['rejected_count']) == (3, 2, 1)
    assert result['load_counts'] == workflow['counts']
    assert result['reconciliation']['passed'] is True
    assert Path(result['archived_file']).exists()
    assert not workflow['source'].exists()
    assert Path(result['rejected_file']).exists()
    assert Path(result['curated_directory']).exists()
    assert workflow['calls'] == [
        'lock', 'extract', 'quality', 'transform', 'incremental', 'create_run',
        'save_issues', 'save_reject_audit', 'load', 'reconcile', 'unlock'
    ]


def test_pipeline_failed_reconciliation_keeps_source(workflow, monkeypatch):
    def failed(*args, **kwargs):
        workflow['calls'].append('reconcile')
        return {'status': 'FAILED', 'passed': False, 'errors': ['Mismatch']}
    monkeypatch.setattr(p, 'reconcile_etl_run', failed)
    result = p.run_etl_pipeline(workflow['source'])
    assert result['archived_file'] is None
    assert workflow['source'].exists()
    assert result['reconciliation']['status'] == 'FAILED'
    assert workflow['calls'][-1] == 'unlock'


def test_pipeline_failure_after_run_created(workflow, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('simulated load failure')
    monkeypatch.setattr(p, 'load_incremental_batch', fail)
    with pytest.raises(RuntimeError, match='simulated load failure'):
        p.run_etl_pipeline(workflow['source'])
    assert 'mark_failed' in workflow['calls']
    assert workflow['calls'][-1] == 'unlock'
    assert workflow['source'].exists()


def test_pipeline_failure_before_run_created(workflow, monkeypatch):
    def fail(*args, **kwargs):
        raise RuntimeError('extraction failed')
    monkeypatch.setattr(p, 'extract_data', fail)
    with pytest.raises(RuntimeError, match='extraction failed'):
        p.run_etl_pipeline(workflow['source'])
    assert 'mark_failed' not in workflow['calls']
    assert workflow['calls'][-1] == 'unlock'


def test_pipeline_lock_failure_prevents_processing(workflow, monkeypatch):
    def fail(conn):
        raise RuntimeError('lock unavailable')
    monkeypatch.setattr(p, 'acquire_etl_lock', fail)
    with pytest.raises(RuntimeError, match='lock unavailable'):
        p.run_etl_pipeline(workflow['source'])
    assert workflow['calls'] == []
    assert workflow['source'].exists()


def test_pipeline_release_lock_error_does_not_hide_success(workflow, monkeypatch):
    def fail(conn):
        raise RuntimeError('unlock error')
    monkeypatch.setattr(p, 'release_etl_lock', fail)
    result = p.run_etl_pipeline(workflow['source'])
    assert result['reconciliation']['passed'] is True


def test_pipeline_forwards_batch_size(workflow, monkeypatch):
    captured = {}
    def load(*args, **kwargs):
        captured.update(kwargs)
        return workflow['counts']
    monkeypatch.setattr(p, 'load_incremental_batch', load)
    p.run_etl_pipeline(workflow['source'], batch_size=23)
    assert captured['batch_size'] == 23
    assert captured['run_id'] == 'ETL_TEST_001'


def test_pipeline_source_name_saved(workflow, monkeypatch):
    captured = {}
    def create(**kwargs):
        captured.update(kwargs)
    monkeypatch.setattr(p, 'create_etl_run', create)
    p.run_etl_pipeline(workflow['source'])
    assert captured['source_file'] == 'customers.csv'
    assert captured['new_count'] == 1
    assert captured['duplicate_count'] == 1
    assert captured['correction_count'] == 0
