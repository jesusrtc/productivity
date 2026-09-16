"""Tab revisions reflect own content, not a shared document's modification time."""
import os

import pytest

from lab import assistant_documents as documents, assistant_migration as migration, assistant_records as records
from .test_assistant_routes import _seed


@pytest.mark.parametrize('kind', ['task', 'note'])
def test_tab_revisions_isolate_content_and_metadata(client, monkeypatch, tmp_path, monorepo, kind):
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)
    parent = records.create(root, kind, 'Root', body='Main content')
    first = records.create_subtab(root, 'First', parent={'type':kind, 'id':parent.stem})
    second = records.create_subtab(root, 'Second', parent={'type':kind, 'id':parent.stem})
    def tree():
        response = client.get('/api/assistant/'+kind, params={'path':str(parent.relative_to(root))})
        assert response.status_code == 200, response.text
        return response.json()['tree']
    before = tree()
    metadata, body = documents.read(first)
    metadata['updated'] = '2026-09-17T10:00:00Z'
    documents.write(first, metadata, body+'First change')
    changed = tree()
    assert changed['updated'] != before['updated']  # root timestamp propagates
    assert changed['tab_revision'] == before['tab_revision']
    assert changed['children'][0]['tab_revision'] != before['children'][0]['tab_revision']
    assert changed['children'][1]['tab_revision'] == before['children'][1]['tab_revision']
    documents.write(first, metadata, body+'Second change')  # same timestamp
    again = tree()
    assert again['children'][0]['tab_revision'] != changed['children'][0]['tab_revision']
    assert again['children'][0]['updated'] == changed['children'][0]['updated']
    os.utime(parent, None)
    touched = tree()
    assert touched['tab_revision'] == again['tab_revision']
    assert [r['tab_revision'] for r in touched['children']] == [r['tab_revision'] for r in again['children']]
    records.update(root, str(second.relative_to(root)), 'owner', 'POC')
    updated = tree()
    assert updated['children'][1]['tab_revision'] != touched['children'][1]['tab_revision']
    assert updated['children'][0]['tab_revision'] == touched['children'][0]['tab_revision']
    assert updated['tab_revision'] == touched['tab_revision']
    assert 'tab_revision:' not in parent.read_text()
