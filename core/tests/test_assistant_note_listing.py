"""Plain-note listings retain their complete descendants and fresh file reads."""
import pytest

from lab import assistant as db, assistant_migration as migration
from lab import assistant_records as records, assistant_documents as documents
from lab import assistant_storage as storage, assistant_tasks as tasks
from core.routes import assistant_v2


@pytest.fixture(params=['schema2', 'embedded', 'unified', 'tasks'])
def notes_library(request, tmp_path, monkeypatch):
    root = tmp_path / 'assistant'
    monkeypatch.setenv('LAB_ASSISTANT_HOME', str(root))
    db.initialize(root)
    migration.migrate(root, dry_run=False)
    if request.param != 'schema2':
        documents.migrate(root, dry_run=False)
    if request.param in {'unified', 'tasks'}:
        storage.migrate(root, dry_run=False)
    if request.param == 'tasks':
        tasks.migrate(root, dry_run=False)
    owner = records.create(root, 'note', 'Root café', identifier='root', tldr='Root summary',
                           body='Root body\n', custom={'nested': ['keep']})
    parent = {'type': 'note', 'id': owner.stem}
    child = records.create(root, 'note', 'Child A', identifier='child-a', parent=parent,
                           tldr='Child summary', body='Child body\n')
    records.create(root, 'note', 'Child B', identifier='child-b', parent=parent)
    records.create(root, 'note', 'Grandchild', identifier='grandchild',
                   parent={'type': 'note', 'id': 'child-a'})
    for note_type in ('plain', 'thread', 'subtab', 'meeting', 'series'):
        records.create(root, 'note', note_type.title(), identifier=note_type, note_type=note_type)
    records.create(root, 'task', 'Task', identifier='task')
    records.create(root, 'project', 'Project', identifier='project')
    return root, owner, child


def original_notes(root):
    # Differential oracle: the previously shipped notes expression, including
    # split-file children and its traversal/order/field conversion semantics.
    return [{**row, 'search_text': ' '.join(
        str(child.get(field) or '')
        for child in [row, *records.descendants(list(records.records(root)), row)]
        for field in ('title', 'tldr', 'owner'))}
        for row in records.records(root, 'notes')
        if not row.get('embedded') and row.get('note_type') in {'plain', 'thread', 'subtab'}]


def test_notes_share_one_snapshot_and_preserve_full_rows(notes_library, monkeypatch):
    root, _, _ = notes_library
    expected = original_notes(root)
    original = records.records
    reads = []

    def observed(folder, collection=None):
        reads.append((folder, collection))
        yield from original(folder, collection)

    monkeypatch.setattr(records, 'records', observed)
    actual = list(assistant_v2.plain_note_rows(root))
    assert actual == expected
    assert reads == [(root, None)]
    owner = next(row for row in actual if row['id'] == 'root')
    assert owner['search_text'] == 'Root café Root summary  Child A Child summary  Child B   Grandchild  '
    assert owner['body'] == 'Root body\n' and owner['custom'] == {'nested': ['keep']}
    assert {row['id'] for row in actual} >= {'root', 'plain', 'thread', 'subtab'}
    assert not {row['id'] for row in actual} & {'meeting', 'series', 'task', 'project'}
    assert ('child-a' in {row['id'] for row in actual}) is not documents.enabled(root)


def test_notes_refresh_edits_additions_deletions_and_nested_values(notes_library):
    root, owner, child = notes_library
    first = list(assistant_v2.plain_note_rows(root))
    next(row for row in first if row['id'] == 'root')['custom']['nested'].append('caller-only')
    metadata, body = records.read_document(child)
    records.write_document(child, {**metadata, 'title': 'Edited child'}, body + 'Fresh body\n')
    added = records.create(root, 'note', 'New note', identifier='new-note')
    actual = list(assistant_v2.plain_note_rows(root))
    assert actual == original_notes(root)
    row = next(row for row in actual if row['id'] == 'root')
    assert 'Edited child' in row['search_text'] and 'Child A' not in row['search_text']
    assert row['custom'] == {'nested': ['keep']}
    assert any(row['id'] == 'new-note' for row in actual)
    added.unlink()
    assert list(assistant_v2.plain_note_rows(root)) == original_notes(root)
    assert not any(row['id'] == 'new-note' for row in assistant_v2.plain_note_rows(root))


def test_notes_keep_path_validation(notes_library, tmp_path):
    root, owner, _ = notes_library
    list(assistant_v2.plain_note_rows(root))
    outside = tmp_path / 'outside.md'
    outside.write_bytes(owner.read_bytes())
    owner.unlink()
    owner.symlink_to(outside)
    with pytest.raises(ValueError):
        list(assistant_v2.plain_note_rows(root))


def test_route_retains_the_complete_note_listing(client, notes_library, monkeypatch):
    root, _, child = notes_library
    response = client.get('/api/assistant')
    assert response.status_code == 200, response.text
    assert response.json()['notes'] == original_notes(root)
    with monkeypatch.context() as original:
        original.setattr(assistant_v2, 'plain_note_rows', original_notes)
        baseline = client.get('/api/assistant')
    assert baseline.status_code == 200 and response.json() == baseline.json()
    metadata, body = records.read_document(child)
    records.write_document(child, {**metadata, 'title': 'Fresh route child'}, body)
    response = client.get('/api/assistant')
    assert response.status_code == 200, response.text
    assert response.json()['notes'] == original_notes(root)
    assert 'Fresh route child' in next(row for row in response.json()['notes'] if row['id'] == 'root')['search_text']
