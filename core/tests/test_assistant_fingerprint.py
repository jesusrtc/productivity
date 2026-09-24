"""One root boundary per scan; every source still gets fresh path/stat checks."""
from pathlib import Path
import os

import pytest

from lab import assistant_documents as documents, assistant_records as records
from lab import assistant_storage as storage
from .test_assistant_shared_snapshot import mixed_library


def original_fingerprint(root):
    files = sorted(path for folder in storage.folders(root) for path in (root/folder).glob('*.md'))
    signature = []
    for source in [*files, root/'.assistant/workspaces.json', root/'.assistant/manifest.json']:
        records.safe(root, source)
        if source.exists():
            stat = source.stat()
            signature.append((source.relative_to(root).as_posix(), stat.st_mtime_ns, stat.st_ctime_ns, stat.st_size))
    return files, signature


def outcome(fn):
    try:
        return fn()
    except (ValueError, OSError, RuntimeError) as exc:
        return type(exc), str(exc)


def make_root(tmp_path, unified=False):
    root = tmp_path/'root café'
    root.mkdir()
    records.write_json(root/'.assistant/manifest.json', {'schema':2,'document_format':documents.FORMAT,
                        **({'storage_layout':storage.LAYOUT} if unified else {})})
    records.write_json(root/'.assistant/workspaces.json', {'workspaces':[]})
    for folder in storage.folders(root):
        (root/folder).mkdir()
    return root


@pytest.mark.parametrize('unified', [False, True])
def test_fingerprint_preserves_order_and_fresh_file_metadata(tmp_path, unified):
    root = make_root(tmp_path, unified)
    folder = root/('documents' if unified else 'notes')
    for name in ['b.md', 'a.md', '.hidden.md', 'not-a-note.txt']:
        (folder/name).write_text(name)
    (root/'projects/project.md').write_text('Project')
    assert documents._fingerprint(root) == original_fingerprint(root)
    before = documents._fingerprint(root)[1]
    target = folder/'a.md'
    old = target.stat()
    target.write_text('Changed body with a new size')
    os.utime(target, ns=(old.st_atime_ns, old.st_mtime_ns))
    assert documents._fingerprint(root) == original_fingerprint(root)
    assert documents._fingerprint(root)[1] != before
    target.rename(folder/'renamed.md')
    (folder/'b.md').unlink()
    (folder/'new.md').write_text('new')
    records.write_json(root/'.assistant/workspaces.json', {'workspaces':[{'id':'new','name':'New'}]})
    assert documents._fingerprint(root) == original_fingerprint(root)
    (root/'.assistant/workspaces.json').unlink()
    assert documents._fingerprint(root) == original_fingerprint(root)


@pytest.mark.parametrize('reference', [
    'notes/plain.md', 'notes/missing.md', 'notes/plain.md#tab=subtab', 'notes/link.md',
    'notes/dangling.md', 'notes/loop.md', 'linked/plain.md', 'notes/../plain.md',
    '../outside.md', '/outside.md', 'notes/plain.md/child', '',
])
def test_shared_root_keeps_standalone_path_results_and_errors(tmp_path, reference):
    root = make_root(tmp_path)
    (root/'notes/plain.md').write_text('inside')
    outside = tmp_path/'outside.md'; outside.write_text('outside')
    (root/'notes/link.md').symlink_to(outside)
    (root/'notes/dangling.md').symlink_to(tmp_path/'missing')
    (root/'notes/loop.md').symlink_to('loop.md')
    (root/'linked').symlink_to(root/'notes', target_is_directory=True)
    expected = outcome(lambda: records.safe(root, reference))
    assert outcome(lambda: records.safe(root, reference, resolved_root=root.resolve())) == expected


@pytest.mark.parametrize('target', ['file', 'folder', 'metadata', 'dangling', 'loop'])
def test_each_fingerprint_rejects_new_symlinks(tmp_path, target):
    root = make_root(tmp_path)
    note = root/'notes/plain.md'; note.write_text('inside')
    assert documents._fingerprint(root) == original_fingerprint(root)
    outside = tmp_path/'elsewhere'; outside.mkdir()
    (outside/'plain.md').write_text('outside')
    if target == 'folder':
        note.unlink();note.parent.rmdir();note.parent.symlink_to(outside, target_is_directory=True)
    elif target == 'metadata':
        source=root/'.assistant/workspaces.json';source.unlink();source.symlink_to(outside/'plain.md')
    else:
        note.unlink()
        note.symlink_to(outside/'plain.md' if target=='file' else outside/'missing' if target=='dangling' else 'plain.md')
    actual=outcome(lambda:documents._fingerprint(root))
    assert actual == outcome(lambda:original_fingerprint(root))
    assert actual[0] is ValueError and 'symlinks' in actual[1]


def test_root_alias_is_fresh_per_scan_and_rechecks_a_moved_boundary(tmp_path):
    first=tmp_path/'first';second=tmp_path/'second'
    for base in [first,second]:
        base.mkdir();(base/'notes').mkdir();(base/'notes/plain.md').write_text(base.name)
    alias=tmp_path/'alias';alias.symlink_to(first, target_is_directory=True)
    boundary=alias.resolve()
    assert documents._fingerprint(alias) == original_fingerprint(alias)
    assert records.safe(alias, alias/'notes/plain.md', resolved_root=boundary) == alias/'notes/plain.md'
    alias.unlink();alias.symlink_to(second, target_is_directory=True)
    assert records.safe(alias, alias/'notes/plain.md', resolved_root=boundary) == records.safe(alias, alias/'notes/plain.md')
    assert documents._fingerprint(alias) == original_fingerprint(alias)
    assert records.safe(alias, alias/'notes/plain.md', resolved_root=alias.resolve()) == alias/'notes/plain.md'


def test_moved_root_fallback_still_rejects_a_target_outside_current_root(tmp_path, monkeypatch):
    root=make_root(tmp_path);source=root/'notes/plain.md';source.write_text('inside')
    original=Path.resolve
    def moved(path, *args, **kwargs):
        return tmp_path/'outside' if path==source else original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',moved)
    with pytest.raises(ValueError, match='escapes Assistant'):
        records.safe(root,source,resolved_root=tmp_path/'old-boundary')


def test_fingerprint_continues_after_root_alias_moves_during_validation(tmp_path, monkeypatch):
    first=tmp_path/'first';second=tmp_path/'second'
    for base in [first,second]:
        base.mkdir();(base/'notes').mkdir();(base/'notes/plain.md').write_text(base.name)
    alias=tmp_path/'alias';alias.symlink_to(first,target_is_directory=True)
    original=records.safe; moved=False
    def check(root, source, **kwargs):
        nonlocal moved
        if not moved:
            alias.unlink();alias.symlink_to(second,target_is_directory=True);moved=True
        return original(root,source,**kwargs)
    with monkeypatch.context() as probe:
        probe.setattr(records,'safe',check)
        actual=documents._fingerprint(alias)
    assert moved and actual==original_fingerprint(alias)


def test_root_resolution_is_shared_but_each_source_is_resolved_again(tmp_path, monkeypatch):
    root = make_root(tmp_path)
    for number in range(100):
        (root/'notes'/f'{number}.md').write_text(str(number))
    calls=[];original=Path.resolve
    def counted(path, *args, **kwargs):
        calls.append(path)
        return original(path,*args,**kwargs)
    monkeypatch.setattr(Path,'resolve',counted)
    files,_=documents._fingerprint(root)
    assert calls.count(root)==1
    assert len(calls)==len(files)+3
    assert all(calls.count(path)==1 for path in [*files,root/'.assistant/workspaces.json',root/'.assistant/manifest.json'])
    calls.clear();documents._fingerprint(root)
    assert calls.count(root)==1 and len(calls)==len(files)+3,'next scan must revalidate every source'


def test_complete_response_matches_original_fingerprint(client, mixed_library, monkeypatch):
    root,_,_=mixed_library
    current=client.get('/api/assistant')
    assert current.status_code==200,current.text
    with monkeypatch.context() as control:
        control.setattr(documents,'_fingerprint',original_fingerprint)
        baseline=client.get('/api/assistant')
    assert baseline.status_code==200 and baseline.json()==current.json()
    assert records.verify(root)['valid'] if records.enabled(root) else True
