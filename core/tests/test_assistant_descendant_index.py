"""Indexed walks preserve the original order, row identity and errors."""
from copy import deepcopy
import random

import pytest

from lab import assistant_records as records
from .test_assistant_shared_snapshot import mixed_library


def original_descendants(rows, record, **_):
    found, frontier, seen = [], [records.key(record)], {records.key(record)}
    while frontier:
        parent = frontier.pop()
        for row in rows:
            if records.parent_key(row) == parent:
                identity = records.key(row)
                if identity in seen:
                    raise ValueError('Document parent cycle')
                seen.add(identity)
                frontier.append(identity)
                found.append(row)
    return found


def row(identifier, parent=None, kind='note'):
    return {'type': kind, 'id': identifier, 'parent': parent, 'title': str(identifier)}


def parent(identifier, kind='note'):
    return {'type': kind, 'id': identifier}


def outcome(fn, rows, current, **kwargs):
    try:
        return fn(rows, current, **kwargs)
    except (ValueError, TypeError, KeyError, AttributeError) as exc:
        return type(exc), str(exc)


@pytest.mark.parametrize('seed', range(12))
def test_indexed_forests_match_original_walks(seed):
    rng = random.Random(seed)
    rows = []
    for number in range(80):
        ancestor = rng.choice(rows) if rows and rng.random() < .85 else None
        rows.append(row(str(number), parent(ancestor['id'], ancestor['type']) if ancestor else None,
                        kind=rng.choice(['task', 'note'])))
    rng.shuffle(rows)
    before = deepcopy(rows)
    index = records.children_index(rows)
    for current in rows:
        expected = original_descendants(rows, current)
        actual = records.descendants(rows, current, by_parent=index)
        assert actual == expected
        assert all(a is b for a, b in zip(actual, expected))
    assert rows == before


def test_sibling_batches_and_reverse_frontier_order_are_preserved():
    rows = [row('root'), row('c', parent('root')), row('b', parent('root')),
            row('d', parent('b')), row('e', parent('c')), row('f', parent('b'))]
    actual = records.descendants(rows, rows[0], by_parent=records.children_index(rows))
    assert [item['id'] for item in actual] == ['c', 'b', 'd', 'f', 'e']


@pytest.mark.parametrize('rows,current', [
    ([], row('outside')),
    ([row('child', parent('outside'))], row('outside')),
    ([row('root', parent('root'))], row('root')),
    ([row('root', parent('child')), row('child', parent('root'))], row('root')),
    ([row('a', parent('root')), row('a', parent('root'))], row('root')),
    ([row('a', parent('root')), row('b', parent('root')), row('same', parent('a')), row('same', parent('b'))], row('root')),
    ([row('root'), row('other', parent('other'))], row('root')),
    ([row('root'), row('other', parent('missing'))], row('root')),
    ([row('root'), row('bad', {'type': 'note', 'id': []})], row('root')),
    ([row('root'), row('bad', {'type': {}, 'id': 'root'})], row('root')),
    ([row('root'), {'type': 'note', 'parent': parent('root')}], row('root')),
    ([row('root')], row([])),
    ([row('root'), None], row('root')),
], ids=['empty', 'external-root', 'self-cycle', 'parent-cycle', 'duplicate-child',
        'duplicate-across-branches', 'unreachable-cycle', 'unreachable-orphan',
        'unhashable-parent-id', 'unhashable-parent-type', 'missing-child-id',
        'unhashable-root-id', 'non-record'])
def test_errors_and_unrelated_invalid_records_match(rows, current):
    index = records.children_index(rows)
    assert outcome(records.descendants, rows, current, by_parent=index) == outcome(original_descendants, rows, current)


def test_index_is_local_and_empty_index_is_not_a_scan(monkeypatch):
    root, child = row('root'), row('child', parent('root'))
    rows = [root, child]
    assert records.descendants(rows, root, by_parent=records.children_index(rows)) == [child]
    child['parent'] = parent('elsewhere')
    assert records.descendants(rows, root, by_parent=records.children_index(rows)) == []

    def unexpected(_):
        pytest.fail('An explicitly supplied empty index scanned the records')

    monkeypatch.setattr(records, 'parent_key', unexpected)
    assert records.descendants(rows, root, by_parent={}) == []


def test_repeated_walks_do_not_recheck_every_record_parent(monkeypatch):
    roots = [row(str(number)) for number in range(500)]
    children = [row('child-' + str(number), parent(str(number))) for number in range(100)]
    rows = roots + children
    calls = 0
    original = records.parent_key

    def counted(value):
        nonlocal calls
        calls += 1
        return original(value)

    monkeypatch.setattr(records, 'parent_key', counted)
    index = records.children_index(rows)
    for number, current in enumerate(roots):
        assert records.descendants(rows, current, by_parent=index) == ([children[number]] if number < 100 else [])
    assert calls <= 2 * len(rows), 'Repeated walks became full-library scans again'


def test_complete_response_matches_scan_based_traversal(client, mixed_library, monkeypatch):
    root, _, _ = mixed_library
    current = client.get('/api/assistant')
    assert current.status_code == 200, current.text
    with monkeypatch.context() as control:
        control.setattr(records, 'descendants', original_descendants)
        baseline = client.get('/api/assistant')
    assert baseline.status_code == 200 and current.json() == baseline.json()
    assert records.verify(root)['valid'] if records.enabled(root) else True
