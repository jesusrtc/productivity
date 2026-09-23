"""Owned Assistant documents shared by HTTP and native-navigation probes."""
from pathlib import Path


def seed_assistant(root: Path, count: int):
    from lab import assistant as db, assistant_migration as migration
    from lab import assistant_records as records, assistant_documents as documents
    from lab import assistant_storage as storage, assistant_tasks as tasks

    assert count >= 2 and not root.exists(), 'Use a new disposable Assistant root'
    db.initialize(root)
    migration.migrate(root, dry_run=False)
    documents.migrate(root, dry_run=False)
    storage.migrate(root, dry_run=False)
    tasks.migrate(root, dry_run=False)
    expected = {'root': str(root), 'notes': [], 'documents': []}
    for number in range(count):
        identifier = f'fixture-note-{number:04}'
        title = f'Fixture note {number:04} café'
        body = f'Fixture body {number:04}.\n'
        source = records.create(root, 'note', title, identifier=identifier, body=body,
                                tldr=f'Fixture summary {number:04}', starred=number % 7 == 0,
                                attributes={'fixture_number': number})
        row = {'id': identifier, 'title': title, 'path': source.relative_to(root).as_posix(),
               'body': body, 'tldr': f'Fixture summary {number:04}', 'starred': number % 7 == 0,
               'created': records.read_document(source)[0]['created'],
               'attributes': {'fixture_number': number},
               'search_text': f'{title} Fixture summary {number:04} '}
        if number % 10 == 0:
            for child in range(2):
                child_title = f'Reference {number:04}-{child}'
                records.create(root, 'note', child_title,
                               identifier=f'fixture-tab-{number:04}-{child}',
                               parent={'type': 'note', 'id': identifier},
                               body=f'Child body {number:04}-{child}.\n')
                row['search_text'] += f' {child_title}  '
        expected['notes'].append(row)
        expected['documents'].append({key: value for key, value in row.items()
                                      if key not in {'body', 'search_text'}})
    # Initialization is not an API warm-up. The first request must rebuild its
    # own process-local snapshot from the files, including the generated index.
    documents._CACHE.pop(str(root), None)
    return expected


def verify_assistant(actual, expected):
    assert actual['configured'] and actual['exists'] and actual['initialized']
    assert actual['root'] == expected['root'] and actual['schema'] == 2
    assert actual['tasks'] == actual['meetings'] == actual['meeting_series'] == actual['projects'] == []
    assert actual['workspaces'] == []
    assert len(actual['notes']) == len(expected['notes'])
    assert len(actual['documents']) == len(expected['documents'])
    for actual_row, expected_row in zip(actual['notes'], expected['notes']):
        assert {key: actual_row[key] for key in expected_row} == expected_row
        assert not actual_row.get('embedded') and actual_row['type'] == 'note'
    for actual_row, expected_row in zip(actual['documents'], expected['documents']):
        assert {key: actual_row[key] for key in expected_row} == expected_row
        assert not actual_row['tracked'] and actual_row['kind'] == 'note'
        assert actual_row['task_items'] == [] and actual_row['task_summary']['total'] == 0
        assert actual_row['summary'] == expected_row['tldr']
        assert expected_row['title'] in actual_row['search_text']
    assert {row['id'] for row in actual['dashboard']['sections']} == {'priority', 'starred', 'documents'}
    return len(actual['documents'])
