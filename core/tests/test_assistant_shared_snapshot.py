"""One fresh record read serves the index's independent schema-2 projections."""
from copy import deepcopy
from functools import wraps

import pytest

from lab import assistant as db, assistant_meetings as meetings
from lab import assistant_records as records, assistant_documents as documents
from lab import assistant_migration as migration, assistant_storage as storage
from lab import assistant_tasks as tasks
from core.routes import assistant_v2
from .test_assistant_routes import _seed


@pytest.fixture(params=['legacy', 'schema2', 'embedded', 'unified', 'tasks'])
def mixed_library(request, monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    db.create_subtask(root, 'Review draft', parent=task.stem)
    meetings.create_series(root, 'weekly', workspace_id='demo', title='Weekly series')
    raw = tmp_path / 'raw.txt'
    raw.write_bytes(b'Original notes\r\n')
    for title, day in [('Older', '2026-01-01'), ('Latest', '2026-01-08'), ('Undated', None)]:
        source = meetings.create_meeting(root, title, workspace_id='demo', series='weekly',
                                         date=day, undated=day is None, raw_file=raw if day else None)
        meta, _ = db.read_markdown(source)
        db.write_markdown(source, meta, '# Summary\n\nDecision.\n\n# Action items\n\n- [ ] Follow up\n- [x] Done\n')
        meetings.create_content(root, title + ' source', meeting_id=source.stem, kind='question')
    if request.param != 'legacy':
        migration.migrate(root, dry_run=False)
        if request.param in {'embedded', 'unified', 'tasks'}:
            documents.migrate(root, dry_run=False)
        if request.param in {'unified', 'tasks'}:
            storage.migrate(root, dry_run=False)
        if request.param == 'tasks':
            tasks.migrate(root, dry_run=False)
        project = records.create(root, 'project', 'Project', identifier='project')
        records.create(root, 'note', 'Guide', identifier='guide', workspace='demo', project=project.stem,
                       starred=True, body='Guide body\n', custom={'nested': ['original']})
    return root, task.stem, request.param


def independent_reads(monkeypatch):
    """Restore independently read projections as an output-equivalence control."""
    for module, name in [(db, 'iter_tasks'), (meetings, 'list_rows'), (meetings, 'iter_series'),
                         (records, 'task_rows'), (records, 'note_rows'),
                         (assistant_v2, 'document_rows'), (assistant_v2, 'plain_note_rows')]:
        original = getattr(module, name)

        @wraps(original)
        def fresh(*args, _original=original, **kwargs):
            kwargs.pop('record_rows', None)
            return _original(*args, **kwargs)

        monkeypatch.setattr(module, name, fresh)


def test_all_projections_match_independent_reads_and_share_one_read(client, mixed_library, monkeypatch):
    root, _, layout = mixed_library
    original = records.records
    reads = []
    captured = []

    def observed(folder, collection=None):
        reads.append((folder, collection))
        rows = list(original(folder, collection))
        captured.append((rows, deepcopy(rows)))
        yield from rows

    with monkeypatch.context() as tracing:
        tracing.setattr(records, 'records', observed)
        response = client.get('/api/assistant')
    assert response.status_code == 200, response.text
    assert reads == ([] if layout == 'legacy' else [(root, None)])
    assert all(rows == before for rows, before in captured), 'A projection mutated the shared input'
    actual = response.json()
    with monkeypatch.context() as control:
        independent_reads(control)
        before = client.get('/api/assistant')
    assert before.status_code == 200 and actual == before.json()
    assert len(actual['meetings']) == 3 and len(actual['meeting_series']) == 1
    assert [row.get('date') for row in actual['meetings']] == ['2026-01-08', '2026-01-01', None]
    assert actual['meeting_series'][0]['latest_date'] == '2026-01-08'
    assert actual['meeting_series'][0]['meeting_count'] == 3
    assert [row['has_raw'] for row in actual['meetings']] == [True, True, False]
    assert all(row['content_count'] >= 1 and row['series_title'] == 'Weekly series' for row in actual['meetings'])
    assert all('body' not in row for row in actual['meetings'])
    assert actual['tasks'] and actual['workspaces'][0]['name'] == 'Demo'
    if layout != 'legacy':
        assert actual['projects'] == list(original(root, 'projects'))
        guide = next(row for row in actual['documents'] if row['id'] == 'guide')
        assert guide['starred'] and guide['workspace_name'] == 'Demo' and guide['project'] == 'project'
        assert guide['custom'] == {'nested': ['original']}


def test_next_request_sees_edits_and_does_not_reuse_another_root(client, mixed_library, tmp_path, monkeypatch):
    root, task_id, layout = mixed_library
    if layout == 'legacy':
        source, metadata, body = db.find_task(root, task_id)
    else:
        source, metadata, body = records.resolve(root, task_id)
    first = client.get('/api/assistant')
    assert first.status_code == 200
    if layout == 'legacy':
        db.write_markdown(source, {**metadata, 'title': 'Fresh task'}, body)
    else:
        records.write_document(source, {**metadata, 'title': 'Fresh task'}, body)
    second = client.get('/api/assistant')
    assert second.status_code == 200
    if layout != 'legacy':
        assert next(row for row in second.json()['documents'] if row['id'] == task_id)['title'] == 'Fresh task'
    # Document-task titles belong to task items, independently of the document.
    if layout != 'tasks':
        assert next(row for row in second.json()['tasks'] if row['id'] == task_id)['title'] == 'Fresh task'
    other = tmp_path / 'other-assistant'
    db.initialize(other)
    migration.migrate(other, dry_run=False)
    documents.migrate(other, dry_run=False)
    with monkeypatch.context() as scope:
        scope.setenv('LAB_ASSISTANT_HOME', str(other))
        result = client.get('/api/assistant')
    assert result.status_code == 200
    assert result.json()['root'] == str(other)
    assert result.json()['documents'] == result.json()['notes'] == result.json()['projects'] == []
    third = client.get('/api/assistant')
    assert third.status_code == 200 and third.json() == second.json()


def test_empty_supplied_snapshot_is_not_reloaded(monkeypatch, tmp_path):
    root = tmp_path / 'empty'
    db.initialize(root)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)

    def unexpected(*args, **kwargs):
        pytest.fail('The supplied empty snapshot was reread')

    monkeypatch.setattr(records, 'records', unexpected)
    assert list(db.iter_tasks(root, record_rows=[])) == []
    assert list(meetings.iter_series(root, record_rows=[])) == []
    assert meetings.list_rows(root, record_rows=[]) == []
    assert list(assistant_v2.document_rows(root, record_rows=[])) == []
    assert list(assistant_v2.plain_note_rows(root, record_rows=[])) == []


def test_migration_completed_after_legacy_capture_keeps_fresh_fallback(client, monkeypatch, tmp_path, monorepo):
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    original = db.iter_tasks

    def migrate_before_projection(folder, workspaces=None, *, record_rows=None):
        assert record_rows is None
        migration.migrate(root, dry_run=False)
        records.create(root, 'project', 'Fresh project', identifier='fresh-project')
        return original(folder, workspaces, record_rows=record_rows)

    monkeypatch.setattr(db, 'iter_tasks', migrate_before_projection)
    response = client.get('/api/assistant')
    assert response.status_code == 200, response.text
    assert response.json()['schema'] == 2 and response.json()['tasks']
    assert [row['id'] for row in response.json()['projects']] == ['fresh-project']
