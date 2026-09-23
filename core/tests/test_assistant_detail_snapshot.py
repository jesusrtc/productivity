"""A detail request shares its validated library, but still reads current files."""
from copy import deepcopy
import hashlib

import pytest

from lab import assistant as db, assistant_records as records, assistant_tasks as tasks
from .test_assistant_shared_snapshot import mixed_library


def outcome(call):
    try:
        return call()
    except (ValueError, OSError, KeyError, TypeError) as error:
        return type(error), str(error)


def test_complete_details_match_independent_resolution_reads(client, mixed_library, monkeypatch):
    root, task, layout = mixed_library
    rows = list(records.records(root)) if layout != 'legacy' else []
    references = [task, '../outside.md', 'missing'] + [row['path'] for row in rows]
    original_read, original_resolve = records.records, records.resolve
    reads = []

    def observed(*args, **kwargs):
        reads.append((args, kwargs))
        yield from original_read(*args, **kwargs)

    def independent(folder, reference, collection=None, *, record_rows=None):
        # Consume the request's lazy snapshot, then resolve independently. This
        # controls for shared data without changing response shaping or files.
        if record_rows is not None:
            tuple(record_rows)
        return original_resolve(folder, reference, collection)

    for reference in references:
        reads.clear()
        with monkeypatch.context() as tracing:
            tracing.setattr(records, 'records', observed)
            response = client.get('/api/assistant/note', params={'path':reference})
        if reference == '../outside.md':
            assert not reads
        else:
            assert len(reads) == 1
        with monkeypatch.context() as control:
            control.setattr(records, 'resolve', independent)
            baseline = client.get('/api/assistant/note', params={'path':reference})
        assert response.status_code == baseline.status_code
        assert response.json() == baseline.json()
    if layout == 'legacy':
        source, _, _ = db.find_task(root, task)
        assert client.get('/api/assistant/task', params={'path':source.relative_to(root).as_posix()}).status_code == 200
    else:
        assert records.verify(root)['valid']


def test_supplied_records_keep_resolution_results_filters_and_errors(mixed_library):
    root, task, layout = mixed_library
    rows = list(records.records(root)) if layout != 'legacy' else []
    before = deepcopy(rows)
    references = [task, 'missing', '../outside.md', '/outside.md']
    for row in rows:
        references.extend([row['id'], row['path'], *(row.get('aliases') or [])])
    for collection in (None, '', 'documents', 'tasks', 'subtasks', 'notes', 'projects', 'meetings', 'meeting-series', 'invalid'):
        for reference in references:
            assert outcome(lambda: records.resolve(root, reference, collection, record_rows=iter(rows))) == outcome(
                lambda: records.resolve(root, reference, collection))
    assert rows == before


@pytest.mark.parametrize('reference', ['../outside.md', '/outside.md', 'notes/../../outside.md'])
def test_invalid_reference_is_rejected_before_consuming_records(tmp_path, reference):
    def unexpected():
        pytest.fail('Invalid reference consumed the record snapshot')
        yield
    with pytest.raises(ValueError, match='Invalid Assistant reference'):
        records.resolve(tmp_path, reference, 'documents', record_rows=unexpected())


def test_empty_supplied_records_do_not_read_again(mixed_library, monkeypatch):
    root, task, _ = mixed_library
    def unexpected(*args, **kwargs):
        pytest.fail('Explicitly supplied records caused another library read')
    monkeypatch.setattr(records, 'records', unexpected)
    with pytest.raises(ValueError, match='not found or reference is ambiguous'):
        records.resolve(root, task, 'documents', record_rows=[])


def test_resolved_sources_and_next_requests_remain_fresh(client, mixed_library):
    root, task, layout = mixed_library
    if layout == 'legacy':
        assert client.get('/api/assistant/note', params={'path':task}).status_code == 400
        return
    rows = list(records.records(root))
    source, metadata, body = records.resolve(root, task, 'documents', record_rows=rows)
    first = client.get('/api/assistant/note', params={'path':task})
    assert first.status_code == 200
    metadata['title'] = 'Fresh detail title'
    body += 'Fresh detail body.\n'
    if metadata.get('task_format') == tasks.FORMAT:
        metadata['tasks'][0]['title'] = 'Fresh owned task'
    records.write_document(source, metadata, body)
    # Reference matching may use existing rows; body/metadata still come from
    # the actual current source, including the independent task revision read.
    assert records.resolve(root, task, 'documents', record_rows=rows) == (source, metadata, body)
    if layout == 'tasks':
        view = tasks.view(root, task, record_rows=rows)
        assert view['tasks'][0]['title'] == 'Fresh owned task'
        assert view['revision'] == hashlib.sha256(source.read_bytes()).hexdigest()
    second = client.get('/api/assistant/note', params={'path':task})
    assert second.status_code == 200
    assert second.json()['metadata']['title'] == 'Fresh detail title'
    assert second.json()['body'] == body
    assert second.json()['tree']['title'] == 'Fresh detail title'
    assert second.json()['tree']['tab_revision'] != first.json()['tree']['tab_revision']


def test_supplied_records_do_not_skip_fresh_source_path_checks(mixed_library, tmp_path):
    root, task, layout = mixed_library
    if layout == 'legacy':
        return
    rows = list(records.records(root))
    source, _, _ = records.resolve(root, task, 'documents', record_rows=rows)
    outside = tmp_path/'outside.md'
    outside.write_bytes(source.read_bytes())
    source.unlink()
    source.symlink_to(outside)
    with pytest.raises(ValueError, match='symlinks'):
        records.resolve(root, task, 'documents', record_rows=rows)
