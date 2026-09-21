import json
from pathlib import Path

import pytest
from click.testing import CliRunner
from lab import assistant as db, assistant_records as records, assistant_documents as documents, assistant_storage as storage
from lab.cli import main
from .test_assistant_documents import seed


def test_unified_migration_preserves_bytes_aliases_and_new_writes(tmp_path, monkeypatch):
    root, task, child, tab, note = seed(tmp_path)
    documents.migrate(root, dry_run=False)
    project = records.create(root, 'project', 'Business', identifier='business')
    (root/'notes/attachment.txt').write_text('Attachment')
    before = list(records.records(root))
    original = {row['path']:(root/row['path']).read_bytes() for row in before if not row.get('parent')}
    policy = (root/'AGENTS.md').read_bytes()
    manifest = (root/'.assistant/manifest.json').read_bytes()
    plan = storage.migrate(root)
    assert plan['documents'] == 2 and plan['subtabs'] == 2
    assert not (root/'documents').exists()
    assert manifest == (root/'.assistant/manifest.json').read_bytes()
    result = storage.migrate(root, dry_run=False)
    for old, new in result['moves'].items():
        assert not (root/old).exists()
        assert (root/new).read_bytes() == original[old]
        assert (Path(result['backup'])/old).read_bytes() == original[old]
    assert (root/'AGENTS.md').read_bytes() == policy
    assert project.read_bytes() == original['projects/business.md']
    assert (root/'notes/attachment.txt').read_text() == 'Attachment'
    assert not (root/'tasks').exists()
    for row in before:
        for ref in (row['path'], row['id'], *(row.get('aliases') or [])):
            resolved, metadata, body = records.resolve(root, ref)
            assert metadata['id'] == row['id'] and body == row['body']
    db.initialize(root)
    assert not (root/'tasks').exists()
    for kind in ('task','note'):
        created = records.create(root, kind, 'New ' + kind)
        assert created.parent == root/'documents'
    records.create_subtab(root,'Extra',parent={'type':'note','id':note.stem})
    assert storage.migrate(root, dry_run=False)['changed'] is False
    assert records.verify(root)['valid']
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    runner = CliRunner()
    result = runner.invoke(main,['assistant','migrate','--documents','--dry-run'])
    assert result.exit_code == 0 and json.loads(result.output)['changed'] is False
    result = runner.invoke(main,['assistant','migrate','--documents','--embedded'])
    assert result.exit_code != 0
    assert runner.invoke(main,['migrations','assistant-documents']).exit_code == 0


def test_unified_migration_rolls_back_failed_verification(tmp_path, monkeypatch):
    root,*_ = seed(tmp_path)
    documents.migrate(root,dry_run=False)
    originals = {p.relative_to(root):p.read_bytes() for folder in ('tasks','notes','projects') for p in (root/folder).glob('*.md')}
    manifest = (root/'.assistant/manifest.json').read_bytes()
    real = documents.snapshot
    failed = False
    def fail_once(*args, **kwargs):
        nonlocal failed
        if storage.enabled(root) and not failed:
            failed = True
            raise ValueError('simulated verification failure')
        return real(*args, **kwargs)
    monkeypatch.setattr(documents,'snapshot',fail_once)
    with pytest.raises(ValueError, match='simulated'):
        storage.migrate(root,dry_run=False)
    assert failed and not (root/'documents').exists()
    assert (root/'.assistant/manifest.json').read_bytes() == manifest
    assert all((root/path).read_bytes() == data for path,data in originals.items())
    assert records.verify(root)['valid']
    assert any(json.loads(p.read_text())['state']=='rolled_back' for p in (root/'.assistant/migrations').glob('documents-*.json'))


@pytest.mark.parametrize('collision', ['file', 'symlink', 'id'])
def test_unified_migration_rejects_conflicting_destinations(tmp_path, collision):
    root,task,*_ = seed(tmp_path)
    documents.migrate(root,dry_run=False)
    if collision == 'symlink':
        (root/'documents').symlink_to(root/'notes',target_is_directory=True)
    elif collision == 'file':
        (root/'documents').mkdir()
        (root/'documents/unknown.md').write_text('Must survive')
    else:
        meta,body,tabs = documents.unpack(task.read_bytes())
        meta['type'] = 'note';meta['id'] = task.stem
        # A root-only task/note ID collision is valid in the older typed format.
        records.atomic_bytes(root/'notes'/task.name, documents.pack(meta,body,[]))
    with pytest.raises(ValueError):
        storage.migrate(root,dry_run=False)
    assert task.is_file() and not storage.enabled(root)


@pytest.mark.parametrize('value', ['javascript:alert(1)', 'file:///tmp/doc', '//example.com', 'https://user:secret@example.com', 'https://', 'https://example.com:bad', 'https://example.com/ a', 'https://example.com/\nnext', True, {}])
def test_external_url_validation(value, tmp_path):
    root,*_,note = seed(tmp_path)
    documents.migrate(root,dry_run=False)
    with pytest.raises(ValueError, match='External document'):
        records.update(root,note.stem,'external_url',value)
    assert 'external_url' not in records.resolve(root,note.stem)[1]


def test_external_url_cli_and_subtabs(tmp_path,monkeypatch):
    root,task,child,tab,note = seed(tmp_path)
    documents.migrate(root,dry_run=False)
    storage.migrate(root,dry_run=False)
    monkeypatch.setenv('LAB_ASSISTANT_HOME',str(root))
    before = {row['id']:row['body'] for row in records.records(root)}
    runner = CliRunner()
    url = 'https://docs.google.com/document/d/example/edit#heading=h.example'
    for group,identifier in [('document',note.stem),('subtab',tab.stem)]:
        result = runner.invoke(main,['assistant',group,'set',identifier,'external_url',url])
        assert result.exit_code == 0,result.output
        assert records.resolve(root,identifier)[1]['external_url'] == url
    assert not records.resolve(root,task.stem)[1].get('external_url')
    assert before == {row['id']:row['body'] for row in records.records(root)}
    with pytest.raises(ValueError,match='changed elsewhere'):
        records.update(root,note.stem,'external_url',None,expected=None)
    assert runner.invoke(main,['assistant','document','set',note.stem,'external_url','null']).exit_code == 0
    assert records.resolve(root,note.stem)[1]['external_url'] is None


def test_unified_storage_rejects_unknown_identity_type(tmp_path):
    root,*_,note = seed(tmp_path)
    documents.migrate(root,dry_run=False)
    storage.migrate(root,dry_run=False)
    path = records.resolve(root,note.stem)[0]
    metadata,body,tabs = documents.unpack(path.read_bytes())
    metadata['type'] = 'document'
    path.write_bytes(documents.pack(metadata,body,tabs))
    with pytest.raises(ValueError,match='Invalid document identity'):
        records.verify(root)
