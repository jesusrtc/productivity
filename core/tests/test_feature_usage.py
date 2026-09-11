from concurrent.futures import ThreadPoolExecutor

from core import feature_usage
from core.routes import log


def test_daily_totals_merge_vaults_and_sort_without_duplicate_roots(client, tmp_path, monkeypatch):
    first, second = tmp_path / 'first', tmp_path / 'second'
    feature_usage.increment(first, '2026-09-10', 'Create workspace (+ button)')
    for _ in range(3):
        feature_usage.increment(first, '2026-09-11', 'Link terminal to document (drag and drop)')
    feature_usage.increment(second, '2026-09-11', 'Link terminal to document (drag and drop)')
    feature_usage.increment(second, '2026-09-11', 'Link terminal to document (secondary click)')
    monkeypatch.setattr(log, '_vault_log_dirs', lambda request: [('one', first), ('alias', first), ('two', second)])
    result = client.get('/api/log/usage').json()
    assert result['total_usage'] == 6
    assert [(row['date'], row['usage_count']) for row in result['entries']] == [
        ('2026-09-11', 4), ('2026-09-11', 1), ('2026-09-10', 1)]
    assert 'drag and drop' in result['entries'][0]['feature']
    assert 'secondary click' in result['entries'][1]['feature']
    assert client.get('/api/log/usage?day=2026-09-10').json()['total_usage'] == 1
    assert client.get('/api/log/usage?day=2026-09-09').json()['entries'] == []
    assert client.get('/api/log/usage?day=bad').status_code == 422


def test_ingestion_survives_diagnostic_rate_limit_and_clear_is_independent(client, tmp_path, monkeypatch):
    monkeypatch.setattr(log, '_log_dir', lambda request: tmp_path)
    monkeypatch.setattr(log, '_vault_log_dirs', lambda request: [('test', tmp_path)])
    monkeypatch.setattr(log, '_check_rate', lambda n: False)
    event = {'day': '2026-09-11', 'feature': 'Create workspace (+ button)'}
    for _ in range(2):
        assert client.post('/api/log/usage', json=event).status_code == 200
    assert client.get('/api/log/usage').json()['entries'][0]['usage_count'] == 2
    (tmp_path / 'frontend.log').write_text('keep diagnostic history\n')
    assert client.delete('/api/log/usage').json()['cleared'] == ['test']
    assert client.get('/api/log/usage').json()['entries'] == []
    assert (tmp_path / 'frontend.log').read_text() == 'keep diagnostic history\n'
    assert client.post('/api/log/usage', json=event).status_code == 200
    assert client.get('/api/log/usage').json()['total_usage'] == 1
    assert client.delete('/api/log/clear/all?file=frontend.log').status_code == 200
    assert client.get('/api/log/usage').json()['total_usage'] == 1


def test_usage_input_validation(client):
    for event in [
        {'day': 'not-a-day', 'feature': 'Create workspace'},
        {'day': '2026-09-11', 'feature': ''},
        {'day': '2026-09-11', 'feature': 'x' * 121},
        {'day': '2026-09-11', 'feature': 'Injected\nrow'},
    ]:
        assert client.post('/api/log/usage', json=event).status_code == 422


def test_usage_requires_login_and_admin_for_history(client):
    client.post('/api/auth/logout')
    for method in (client.get, client.delete):
        assert method('/api/log/usage').status_code in (401, 403)
    assert client.post('/api/log/usage', json={'day': '2026-09-11', 'feature': 'Create file'}).status_code in (401, 403)


def test_concurrent_increments_are_atomic_and_persist(tmp_path):
    with ThreadPoolExecutor(max_workers=8) as pool:
        list(pool.map(lambda _: feature_usage.increment(tmp_path, '2026-09-11', 'Create file'), range(100)))
    assert feature_usage.read(tmp_path) == [{'date': '2026-09-11', 'feature': 'Create file', 'usage_count': 100}]
