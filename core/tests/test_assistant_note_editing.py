"""Note content saves preserve the embedded document and reject stale drafts."""
import pytest

from lab import assistant_records as records, assistant_documents as documents, assistant_migration as migration
from .test_assistant_routes import _seed


@pytest.fixture()
def note_data(monkeypatch, tmp_path, monorepo):
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)
    note = records.create(root, 'note', 'Editable note', body='# Original\n\nFirst paragraph.\n', custom={'keep': True})
    child = records.create_subtab(root, 'Child', parent={'type':'note', 'id':note.stem})
    sibling = records.create_subtab(root, 'Sibling', parent={'type':'note', 'id':note.stem})
    return root, note, child, sibling, task


def save(client, path, before, after):
    return client.put('/api/assistant/content', json={'path':path, 'expected':before, 'body':after})


def test_save_note_preserves_tabs_and_unknown_metadata(client, note_data):
    root, note, child, sibling, _ = note_data
    reference = str(note.relative_to(root))
    before = client.get('/api/assistant/note', params={'path':reference}).json()
    after = '# Edited\n\nText with **formatting**.\n\n<details><summary>More</summary>\n\nKeep this.\n\n</details>\n'
    response = save(client, reference, before['body'], after)
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail['body'] == after
    assert detail['metadata']['id'] == before['metadata']['id']
    assert detail['metadata']['created'] == before['metadata']['created']
    assert detail['metadata']['custom'] == {'keep': True}
    assert len(detail['tree']['children']) == 2
    assert records.verify(root)['valid']
    assert documents.read(child)[1] == documents.read(sibling)[1] == ''
    snapshot = note.read_bytes()
    assert save(client, reference, after, after).status_code == 200
    assert note.read_bytes() == snapshot  # no-op doesn't rewrite metadata


def test_subtab_save_preserves_fresh_siblings_and_properties(client, note_data):
    root, note, child, sibling, _ = note_data
    child_ref, sibling_ref = str(child.relative_to(root)), str(sibling.relative_to(root))
    original_main = documents.read(note)[1]
    records.update_body(root, sibling_ref, 'Changed by another editor', expected='')
    records.update(root, child_ref, 'owner', 'New owner')
    response = save(client, child_ref, '', 'Changed in this tab\n')
    assert response.status_code == 200, response.text
    assert response.json()['metadata']['owner'] == 'New owner'
    assert documents.read(note)[1] == original_main
    assert documents.read(sibling)[1] == 'Changed by another editor'
    assert documents.read(child)[1] == 'Changed in this tab\n'
    assert response.json()['progress']['status'] == 'not_started'
    assert records.verify(root)['valid']


def test_stale_draft_does_not_overwrite_new_content(client, note_data):
    root, note, child, _, _ = note_data
    reference = str(child.relative_to(root))
    records.update_body(root, reference, 'External change', expected='')
    snapshot = note.read_bytes()
    response = save(client, reference, '', 'My stale draft')
    assert response.status_code == 409
    assert 'changed elsewhere' in response.json()['detail']
    assert note.read_bytes() == snapshot


@pytest.mark.parametrize('malformed', ['<!-- lab:subtab fake -->\nBad', '<!-- /lab:subtab fake -->\n', 'Text\n<!-- lab:subtab fake -->\n'])
def test_reserved_markers_rejected_before_writing(client, note_data, malformed):
    root, note, child, _, _ = note_data
    before = note.read_bytes()
    for path in [note, child]:
        response = save(client, str(path.relative_to(root)), documents.read(path)[1], malformed)
        assert response.status_code == 400, response.text
        assert note.read_bytes() == before
    assert records.verify(root)['valid']


def test_empty_body_and_originals_protected(client, note_data):
    root, note, child, _, task = note_data
    reference = str(note.relative_to(root))
    response = save(client, reference, documents.read(note)[1], '')
    assert response.status_code == 200 and response.json()['body'] == ''
    raw = root/'.assistant/assets/original/raw.txt'
    raw.parent.mkdir(parents=True)
    raw.write_text('Immutable original')
    for path in ['../AGENTS.md', str(raw.relative_to(root)), 'tasks/'+task.name]:
        assert save(client, path, '', 'Bad write').status_code == 400
    assert raw.read_text() == 'Immutable original'
    assert records.verify(root)['valid']


def test_note_save_requires_admin(client, note_data):
    root, note, _, _, _ = note_data
    client.cookies.clear()
    response = save(client, str(note.relative_to(root)), documents.read(note)[1], 'Unauthorized')
    assert response.status_code in {401, 403}
