"""Automatic task retention uses isolated files, fake clocks and private tmux."""
from contextlib import contextmanager, nullcontext
from copy import deepcopy
from types import SimpleNamespace
import shutil
import subprocess
import uuid

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from core import task_terminal_cleanup as cleanup
from lab import objectives
from .test_assistant_document_tasks import legacy_tasks, owned_tasks  # noqa: F401

NOW = 2_000_000_000
REAL_RUN = subprocess.run


@pytest.fixture
def state(monorepo, seed_workspace, monkeypatch):
    seed_workspace()
    data = objectives.mutate(monorepo, 'demo', {'type': 'create', 'name': 'Retention'})
    oid = data['objectives'][0]['id']
    clock, meta, listing, calls, disabled = [NOW], {}, [], [], []
    monkeypatch.setattr(cleanup.time, 'time', lambda: clock[0])
    monkeypatch.setattr(cleanup.reviewed, '_roots', lambda root: [{'id': 'fixture', 'path': monorepo}])
    monkeypatch.setattr(cleanup.term, '_tmux_list', lambda *a, **kw: deepcopy(listing))
    monkeypatch.setattr(cleanup.term, '_load_meta', lambda root: deepcopy(meta))
    monkeypatch.setattr(cleanup.term, '_save_meta', lambda root, data: (meta.clear(), meta.update(deepcopy(data))))
    monkeypatch.setattr(cleanup.reviewed, '_disable_autospawn', lambda root, ws: disabled.append(ws))
    monkeypatch.setattr(cleanup.term, '_invalidate_workspace_term_caches', lambda: None)
    monkeypatch.setattr(cleanup.tmux_sockets, 'state_lock', nullcontext)
    monkeypatch.setattr(cleanup.fsguard, 'guarded', lambda root, fn, *a: fn(*a))
    monkeypatch.setattr(cleanup.auth, 'require_admin', lambda request: None)

    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='', stderr='')
    monkeypatch.setattr(cleanup.subprocess, 'run', run)

    def change(task, status):
        return objectives.mutate(monorepo, 'demo', {'type': 'task-update', 'objective_id': oid,
                                                  'task_id': task, 'status': status})

    def add(name, status='in_progress', parent=None, task=True, **extra):
        saved = {'name': name, 'session_id': 'id-' + name, 'kind': 'terminal'}
        if parent:
            saved['parent_terminal'] = parent
        cleanup.term._upsert_workspace_session(monorepo, 'demo', saved)
        saved = cleanup.term._workspace_session_by_name(monorepo, 'demo')[name]
        task_id = None
        if task:
            result = objectives.mutate(monorepo, 'demo', {'type': 'task', 'objective_id': oid, 'title': name})
            task_id = result['objectives'][0]['tasks'][-1]['id']
            objectives.mutate(monorepo, 'demo', {'type': 'terminal', 'objective_id': oid,
                                               'task_id': task_id, 'session_id': saved['session_id']})
            change(task_id, status)
        live = {'name': 'lab-' + name, 'tmux_socket': 'retention-private', 'tmux_id': '$' + str(len(listing)),
                'created': NOW - 86400, 'pane_pid': len(listing) + 100, 'attached': True, 'activity': NOW}
        live.update(extra)
        meta[live['name']] = {'workspace_id': 'demo', 'logical_name': name}
        listing.append(live)
        return task_id

    app = FastAPI()
    app.include_router(cleanup.router)
    app.state.index_cache = SimpleNamespace(root=monorepo)
    with TestClient(app) as client:
        yield SimpleNamespace(root=monorepo, oid=oid, clock=clock, meta=meta, listing=listing,
                              calls=calls, disabled=disabled, add=add, change=change, client=client)


@pytest.mark.parametrize('status,seconds', [('done', 3600), ('wont_do', 3600), ('todo', 3600), ('paused', 3*86400)])
def test_retention_boundary_and_persistent_first_observation(state, status, seconds):
    task = state.add('expired')
    state.change(task, status)
    assert cleanup.reconcile(state.root)['killed'] == []
    state.clock[0] += seconds - 1
    assert cleanup.reconcile(state.root)['killed'] == []
    # A fresh worker reads the persisted clock, rather than restarting it.
    state.clock[0] += 1
    result = cleanup.reconcile(state.root)
    assert [r['logical_name'] for r in result['killed']] == ['expired']
    assert result['errors'] == []
    assert cleanup.term._load_workspace(state.root, 'demo')['sessions'][0]['task_terminal_retired_at']
    assert state.disabled == ['demo']
    # Attached / recently producing output is deliberately not an idle veto.
    command = state.calls[-1]
    assert command[command.index('-t') + 1] == '=lab-expired:'
    assert '#{session_attached}' not in str(command)
    assert '#{session_id}' in str(command) and '#{session_created}' in str(command) and '#{pane_pid}' in str(command)


def test_reactivation_and_new_inactive_transition_reset_the_clock(state):
    task = state.add('resume')
    state.change(task, 'done')
    cleanup.reconcile(state.root)
    state.clock[0] += 3590
    state.change(task, 'in_progress')
    state.clock[0] += 20
    assert not cleanup.reconcile(state.root)['killed']
    state.change(task, 'paused')
    cleanup.reconcile(state.root)
    state.clock[0] += 3601
    assert not cleanup.reconcile(state.root)['killed']
    state.change(task, 'todo')
    state.clock[0] += 3599
    assert not cleanup.reconcile(state.root)['killed']
    state.clock[0] += 1
    assert len(cleanup.reconcile(state.root)['killed']) == 1


def test_children_inherit_but_an_own_active_task_and_unassigned_terminal_survive(state):
    task = state.add('parent')
    state.add('child', parent='parent', task=False)
    state.add('grandchild', parent='child', task=False)
    state.add('other-active-task', parent='parent')
    state.add('unassigned', task=False)
    state.change(task, 'wont_do')
    state.clock[0] += 3600
    result = cleanup.reconcile(state.root)
    assert [r['logical_name'] for r in result['killed']] == ['grandchild', 'child', 'parent']
    assert {s['name'] for s in cleanup.term._load_workspace(state.root, 'demo')['sessions'] if not s.get('task_terminal_retired_at')} == {'other-active-task', 'unassigned'}


def test_status_is_rechecked_under_lock_before_killing(state, monkeypatch):
    task = state.add('race')
    state.change(task, 'done')
    state.clock[0] += 3600
    original = cleanup.operation_lease
    @contextmanager
    def race(*args, **kwargs):
        state.change(task, 'in_progress')
        with original(*args, **kwargs):
            yield
    monkeypatch.setattr(cleanup, 'operation_lease', race)
    assert not cleanup.reconcile(state.root)['killed']
    assert not state.calls


def test_legacy_undo_task_gets_a_full_grace_and_get_is_read_only(state):
    state.add('legacy', status='todo')  # No transition timestamp on initial Todo.
    response = state.client.get('/api/term/task-cleanup')
    assert response.status_code == 200
    assert response.json()['retention_seconds']['paused'] == 259200
    assert not cleanup._journal_path(state.root).exists()
    assert not cleanup.reconcile(state.root)['killed']
    state.clock[0] += 3600
    assert len(cleanup.reconcile(state.root)['killed']) == 1


def test_repeated_status_save_preserves_timestamp(state):
    task = state.add('same')
    state.change(task, 'done')
    state.clock[0] += 2000
    result = state.change(task, 'done')
    assert result['objectives'][0]['tasks'][0]['status_changed_at'] == NOW
    state.clock[0] += 1600
    assert len(cleanup.reconcile(state.root)['killed']) == 1


def test_changed_tmux_identity_is_not_purged(state, monkeypatch):
    task = state.add('replaced')
    state.change(task, 'done')
    state.clock[0] += 3600
    monkeypatch.setattr(cleanup.subprocess, 'run', lambda *a, **kw: SimpleNamespace(returncode=0, stdout='lab-cleanup-skipped'))
    assert not cleanup.reconcile(state.root)['killed']
    assert cleanup.term._load_workspace(state.root, 'demo')['sessions']


def test_legacy_automation_children_and_explicit_detachment(state):
    first, second, detached = ['automation-' + 'a'*32 + '-' + str(n) for n in (1, 2, 3)]
    task = state.add(first)
    state.add(second, task=False)
    state.add(detached, task=False)
    cleanup.save_parents(state.root, 'demo', {detached: None})
    state.change(task, 'done')
    state.clock[0] += 3600
    assert [r['logical_name'] for r in cleanup.reconcile(state.root)['killed']] == [second, first]


def test_parent_updates_reject_cycles_without_writing(state):
    state.add('a')
    state.add('b', task=False)
    cleanup.save_parents(state.root, 'demo', {'b': 'a'})
    with pytest.raises(cleanup.HTTPException, match='cycle'):
        cleanup.save_parents(state.root, 'demo', {'a': 'b'})
    saved = {r['name']: r for r in cleanup.term._load_workspace(state.root, 'demo')['sessions']}
    assert saved['b']['parent_terminal'] == 'a' and 'parent_terminal' not in saved['a']


def test_fixed_mains_servers_and_shared_document_terminals_are_excluded(state):
    state.add('main', task=False)
    saved = cleanup.term._workspace_session_by_name(state.root, 'demo')['main']
    objectives.mutate(state.root, 'demo', {'type': 'terminal', 'objective_id': state.oid,
                                         'session_id': saved['session_id'], 'main': 'objective'})
    for name in ('server-api', 'document'):
        task = state.add(name)
        state.change(task, 'done')
    state.meta['lab-document']['document_key'] = 'shared'
    state.clock[0] += 4*86400
    assert not cleanup.reconcile(state.root)['killed']
    assert not state.calls


def test_unavailable_tmux_does_not_kill_or_write_a_journal(state, monkeypatch):
    task = state.add('unavailable')
    state.change(task, 'done')
    state.clock[0] += 3600
    monkeypatch.setattr(cleanup.term, '_tmux_list', lambda *a, **kw: None)
    with pytest.raises(cleanup.HTTPException):
        cleanup.reconcile(state.root)
    assert not state.calls and not cleanup._journal_path(state.root).exists()


def test_native_exact_tmux_kill_and_replaced_incarnation(state, monkeypatch):
    if not shutil.which('tmux'):
        pytest.skip('tmux unavailable')
    task = state.add('native')
    state.change(task, 'done')
    socket = 'lab-retention-' + uuid.uuid4().hex[:12]
    def tmux(*args):
        return REAL_RUN(cleanup.term._tmux_command(socket, *args), capture_output=True, text=True,
                        env=cleanup.term._tmux_child_env(), timeout=5)
    try:
        assert tmux('new-session', '-d', '-s', 'lab-native', 'sleep 120').returncode == 0
        assert tmux('new-session', '-d', '-s', 'lab-unrelated', 'sleep 120').returncode == 0
        row = state.listing[0]
        values = tmux('display-message', '-p', '-t', '=lab-native:', '#{session_id}|#{session_created}|#{pane_pid}').stdout.strip().split('|')
        row.update(tmux_socket=socket, tmux_id=values[0], created=int(values[1]), pane_pid=int(values[2]))
        monkeypatch.setattr(cleanup.subprocess, 'run', REAL_RUN)
        state.clock[0] += 3600
        assert len(cleanup.reconcile(state.root)['killed']) == 1
        assert tmux('has-session', '-t', '=lab-native').returncode != 0
        assert tmux('has-session', '-t', '=lab-unrelated').returncode == 0
        assert tmux('new-session', '-d', '-s', 'lab-native', 'sleep 120').returncode == 0
        assert not cleanup._stop(row)
        assert tmux('has-session', '-t', '=lab-native').returncode == 0
    finally:
        tmux('kill-server')


def test_assistant_task_transition_and_reactivation_use_the_configured_database(state, owned_tasks):
    from lab import assistant_tasks
    root, document, *_ = owned_tasks
    task = assistant_tasks.change(root, document.stem, {'title': 'Linked terminal'})['task_id']
    state.add('assistant', task=False)
    cleanup.term._upsert_workspace_session(state.root, 'demo', {
        'name': 'assistant', 'linked_task': {'assistant_root': str(root.resolve()),
                                          'document_id': document.stem, 'task_id': task},
    })
    assistant_tasks.change(root, document.stem, {'status': 'blocked'}, task_id=task)
    state.clock[0] += 3601
    assert not cleanup.reconcile(state.root)['killed']
    assistant_tasks.change(root, document.stem, {'status': 'in_progress'}, task_id=task)
    state.clock[0] += 3*86400
    assert not cleanup.reconcile(state.root)['killed']
    changed = assistant_tasks.change(root, document.stem, {'status': 'done'}, task_id=task)
    stamp = next(t for t in changed['tasks'] if t['id'] == task)['status_changed_at']
    state.clock[0] += 3599
    changed = assistant_tasks.change(root, document.stem, {'status': 'done'}, task_id=task)
    assert next(t for t in changed['tasks'] if t['id'] == task)['status_changed_at'] == stamp
    assert not cleanup.reconcile(state.root)['killed']
    state.clock[0] += 1
    assert [r['logical_name'] for r in cleanup.reconcile(state.root)['killed']] == ['assistant']


def test_failed_child_remains_owned_after_parent_expires_and_is_retried(state, monkeypatch):
    task = state.add('parent')
    state.add('child', parent='parent', task=False)
    state.change(task, 'done')
    state.clock[0] += 3600
    monkeypatch.setattr(cleanup, '_stop', lambda row: row['logical_name'] != 'child')
    assert [r['logical_name'] for r in cleanup.reconcile(state.root)['killed']] == ['parent']
    monkeypatch.setattr(cleanup, '_stop', lambda row: True)
    assert [r['logical_name'] for r in cleanup.reconcile(state.root)['killed']] == ['child']


def test_stale_parent_edge_cannot_cross_an_objective_assignment(state):
    task = state.add('parent')
    state.add('child', parent='parent', task=False)
    created = objectives.mutate(state.root, 'demo', {'type': 'create', 'name': 'Other'})
    oid = next(o['id'] for o in created['objectives'] if o['name'] == 'Other')
    child = cleanup.term._workspace_session_by_name(state.root, 'demo')['child']
    objectives.mutate(state.root, 'demo', {'type': 'terminal', 'objective_id': oid,
                                         'session_id': child['session_id'], 'view': 'tasks'})
    state.change(task, 'done')
    state.clock[0] += 3600
    assert [r['logical_name'] for r in cleanup.reconcile(state.root)['killed']] == ['parent']
