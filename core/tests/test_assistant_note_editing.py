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
    assert response.json()['progress']['status'] is None
    assert response.json()['progress']['tracked'] is False
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
    for path in ['../AGENTS.md', str(raw.relative_to(root))]:
        assert save(client, path, '', 'Bad write').status_code == 400
    assert save(client, 'tasks/'+task.name, '', 'Stale task draft').status_code == 409
    assert raw.read_text() == 'Immutable original'
    assert records.verify(root)['valid']


def test_note_save_requires_admin(client, note_data):
    root, note, _, _, _ = note_data
    client.cookies.clear()
    response = save(client, str(note.relative_to(root)), documents.read(note)[1], 'Unauthorized')
    assert response.status_code in {401, 403}


def test_saved_versions_survive_reopen_and_restore_only_selected_tab(client, note_data):
    root, note, child, sibling, _ = note_data
    reference = str(child.relative_to(root))
    original_main = documents.read(note)[1]
    records.update(root, reference, 'owner', 'Preserved owner')
    records.update_body(root, str(sibling.relative_to(root)), 'Untouched sibling', expected='')
    assert save(client, reference, '', 'First edit').status_code == 200
    assert save(client, reference, 'First edit', 'Second edit').status_code == 200
    # History is read again from disk, independent of the editor or browser.
    versions = client.get('/api/assistant/content/history', params={'path':reference}).json()['versions']
    assert [row['preview'] for row in versions] == ['First edit', '']
    response = client.post('/api/assistant/content/revert', json={'path':reference, 'expected':'Second edit', 'revision_id':versions[-1]['id']})
    assert response.status_code == 200, response.text
    assert response.json()['body'] == ''
    assert response.json()['metadata']['owner'] == 'Preserved owner'
    assert documents.read(note)[1] == original_main
    assert documents.read(sibling)[1] == 'Untouched sibling'
    assert client.get('/api/assistant/content/history', params={'path':reference}).json()['versions'][0]['preview'] == 'Second edit'
    assert records.verify(root)['valid']


def test_history_cannot_restore_another_tab_or_overwrite_external_edit(client, note_data):
    root, note, child, sibling, _ = note_data
    reference = str(child.relative_to(root))
    assert save(client, reference, '', 'First edit').status_code == 200
    version = client.get('/api/assistant/content/history', params={'path':reference}).json()['versions'][0]
    records.update_body(root, reference, 'External edit', expected='First edit')
    snapshot = note.read_bytes()
    assert client.post('/api/assistant/content/revert', json={'path':reference, 'expected':'First edit', 'revision_id':version['id']}).status_code == 409
    assert client.post('/api/assistant/content/revert', json={'path':str(sibling.relative_to(root)), 'expected':'', 'revision_id':version['id']}).status_code == 400
    assert note.read_bytes() == snapshot
    assert client.get('/api/assistant/content/history', params={'path':'../AGENTS.md'}).status_code == 400


def test_content_history_is_bounded_and_skips_noop_saves(client, note_data):
    from lab import assistant_content_history as history
    root, _, child, _, _ = note_data
    reference = str(child.relative_to(root))
    for number in range(history.LIMIT + 3):
        records.update_body(root, reference, str(number), expected='' if number == 0 else str(number - 1))
    versions = history.versions(root, reference)
    assert len(versions) == history.LIMIT
    records.update_body(root, reference, str(history.LIMIT + 2), expected=str(history.LIMIT + 2))
    assert history.versions(root, reference) == versions
    client.cookies.clear()
    assert client.get('/api/assistant/content/history', params={'path':reference}).status_code in {401, 403}
    assert client.post('/api/assistant/content/revert', json={'path':reference, 'expected':'', 'revision_id':versions[0]['id']}).status_code in {401, 403}
