from lab import assistant as db, assistant_meetings as meetings

from .test_assistant_routes import _seed


def patch(client, root, source, field, value, expected=None):
    return client.patch('/api/assistant/metadata', json={
        'path': str(source.relative_to(root)), 'field': field, 'value': value, 'expected': expected,
    })


def test_metadata_round_trip_keeps_content_and_unknown_fields(client, monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    metadata, _ = db.read_markdown(task)
    db.write_markdown(task, {**metadata, 'custom': {'retain': True}}, '# Context\n\nKeep this body.\n')
    for field, value, expected in [('priority', 'P2', 'P0'), ('due', '2026-12-31', None),
                                    ('recurrence', 'monthly', None), ('due', None, '2026-12-31')]:
        response = patch(client, root, task, field, value, expected)
        assert response.status_code == 200, response.text
        assert response.json()['metadata'][field] == value
        assert response.json()['metadata']['custom'] == {'retain': True}
        assert response.json()['body'].strip() == '# Context\n\nKeep this body.'
    index = client.get('/api/assistant').json()['tasks'][0]
    assert index['priority'] == 'P2' and index['recurrence'] == 'monthly' and index['due'] is None


def test_invalid_and_stale_metadata_never_overwrites(client, monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    before = task.read_bytes()
    for field, value, expected in [('priority', 'P9', 'P0'), ('priority', None, 'P0'),
                                    ('due', '2026-02-30', None), ('recurrence', 'daily', None),
                                    ('id', 'replacement', task.stem), ('workspace', 'other', 'demo')]:
        assert patch(client, root, task, field, value, expected).status_code == 400
        assert task.read_bytes() == before
    assert patch(client, root, task, 'priority', 'P2', 'P1').status_code == 409
    assert task.read_bytes() == before
    response = client.patch('/api/assistant/metadata', json={
        'path': '../outside.md', 'field': 'title', 'value': 'Changed', 'expected': None,
    })
    assert response.status_code == 400


def test_metadata_status_respects_completion_and_reopening(client, monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    child = db.create_subtask(root, 'Review deliverable', parent=task.stem)
    assert patch(client, root, task, 'status', 'done', 'in_progress').status_code == 400
    child_status = db.read_markdown(child)[0]['status']
    assert patch(client, root, child, 'status', 'done', child_status).status_code == 200
    response = patch(client, root, task, 'status', 'done', 'in_progress')
    assert response.status_code == 200
    assert response.json()['metadata']['completed']
    response = patch(client, root, task, 'status', 'ready', 'done')
    assert response.status_code == 200 and 'completed' not in response.json()['metadata']


def test_note_date_and_series_keep_originals(client, monkeypatch, tmp_path, monorepo):
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    series = meetings.create_series(root, 'weekly', workspace_id='demo', title='Weekly review')
    raw = tmp_path / 'original.txt'
    raw.write_bytes(b'  Original\r\n\r\n')
    note = meetings.create_meeting(root, 'Review', workspace_id='demo', date='2026-09-15', raw_file=raw)
    response = patch(client, root, note, 'date', '2026-09-22', '2026-09-15')
    assert response.status_code == 200 and response.json()['metadata']['date'] == '2026-09-22'
    response = patch(client, root, note, 'series', 'weekly')
    assert response.status_code == 200 and response.json()['series']['title'] == 'Weekly review'
    assert patch(client, root, note, 'series', 'missing', 'weekly').status_code == 400
    assert patch(client, root, note, 'series', None, 'weekly').json()['series'] is None
    assert meetings.raw_path(root, note).read_bytes() == raw.read_bytes()
    assert patch(client, root, series, 'title', 'Review history', 'Weekly review').status_code == 200
    response = patch(client, root, meetings.raw_path(root, note), 'title', 'Overwrite')
    assert response.status_code == 400
