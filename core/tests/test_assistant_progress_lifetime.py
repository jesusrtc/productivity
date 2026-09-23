"""Completed progress calculations release their trees without cyclic GC."""
from copy import deepcopy
import gc
import weakref

import pytest

from lab import assistant_records as records, assistant_tasks as tasks


class Row(dict):
    """A normal record with weak-reference support for lifetime assertions."""


class Rows(list):
    pass


@pytest.fixture
def automatic_gc_disabled():
    enabled = gc.isenabled()
    gc.disable()
    try:
        yield
    finally:
        if enabled:
            gc.enable()


def task_tree():
    return [
        Row(id='root', title='Root', parent_id=None, status='not_started',
            status_override='in_progress'),
        Row(id='done', title='Done', parent_id='root', status='done'),
        Row(id='pending', title='Pending', parent_id='root', status='not_started'),
        Row(id='blocked', title='Blocked', parent_id=None, status='blocked'),
    ]


@pytest.mark.parametrize('document_tasks', [False, True])
def test_progress_releases_input_records_with_result_alive(automatic_gc_disabled, document_tasks):
    rows = [Row(type='note', id='root', parent=None),
            Row(type='task', id='child', parent={'type': 'note', 'id': 'root'}, status='completed')]
    if document_tasks:
        rows[0].update(task_format=tasks.FORMAT, tasks=task_tree())
    refs = [weakref.ref(row) for row in rows]
    before = deepcopy(rows)
    result = records.progress_map(rows)
    assert rows == before
    assert result[('note', 'root')]['status'] == ('blocked' if document_tasks else 'done')
    del rows
    assert all(ref() is None for ref in refs), 'Progress retained its completed input tree'


def test_normalize_releases_copied_tasks_after_caller_releases_result(automatic_gc_disabled):
    source = task_tree()
    before = deepcopy(source)
    normalized = tasks.normalize(source)
    assert source == before
    assert [row['status'] for row in normalized] == ['in_progress', 'done', 'not_started', 'blocked']
    assert all(copy is not original for copy, original in zip(normalized, source))
    refs = [weakref.ref(row) for row in normalized]
    del normalized
    assert all(ref() is None for ref in refs), 'Normalization retained its completed copies'
    assert source == before


@pytest.mark.parametrize('empty', [False, True])
def test_summary_releases_normalized_list_and_tasks(automatic_gc_disabled, monkeypatch, empty):
    normalize = tasks.normalize
    refs = []

    def observe(items):
        normalized = Rows(normalize(items))
        refs.append(weakref.ref(normalized))
        refs.extend(weakref.ref(row) for row in normalized)
        return normalized

    monkeypatch.setattr(tasks, 'normalize', observe)
    source = [] if empty else task_tree()
    before = deepcopy(source)
    result = tasks.summary(source)
    expected = dict(status='blocked', automatic_status='blocked', tracked=True, derived=True,
                    completed=1, total=3, pending=2, wip=1, blocked=1)
    if empty:
        expected = dict(status=None, automatic_status=None, tracked=False, derived=False,
                        completed=0, total=0, pending=0, wip=0, blocked=0)
    assert result == expected and source == before
    assert all(ref() is None for ref in refs), 'Summary retained its normalized tasks'
