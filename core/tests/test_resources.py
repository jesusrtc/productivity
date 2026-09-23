"""Process ownership, PID reuse and explicit signals at the resource boundary."""
import os
import subprocess
import sys
import time
from types import SimpleNamespace

import psutil
import pytest
from fastapi import HTTPException

from core import resource_monitor as resources


@pytest.fixture
def monitor(monkeypatch):
    monkeypatch.setattr(resources, '_pane_roots', lambda: ({}, []))
    monkeypatch.setattr(resources.notebook_kernel, 'resource_processes', lambda: {})
    return resources.Monitor()


def test_ownership_uses_ancestry_and_lab_panes_never_python_names(monitor, monkeypatch):
    me = os.getpid()
    def row(pid, ppid, name='python', created=1):
        return {'pid': pid, 'ppid': ppid, 'name': name, 'create_time': created}
    table = {me: row(me, 1), 11: row(11, me), 12: row(12, 11),
             21: row(21, 1), 22: row(22, 21, 'jupyter'), 99: row(99, 1, 'jupyter'),
             31: row(31, me, 'tmux: server'), 32: row(32, 31)}
    monkeypatch.setattr(resources, '_process_table', lambda: table)
    monkeypatch.setattr(resources, '_pane_roots', lambda: ({21: {'kind': 'Terminal', 'scope': 'lab-pane'}}, []))
    selected, _ = monitor._discover()
    assert set(selected) == {me, 11, 12, 21, 22, 31}
    assert selected[22]['scope'] == 'lab-pane'
    # An already verified detached child stays visible, but not a recycled PID.
    table[12]['ppid'] = 1
    table[11] = row(11, 1, created=2)
    selected, _ = monitor._discover()
    assert 12 in selected and 11 not in selected and 99 not in selected


def test_stop_rejects_unrelated_reused_and_protected_processes(monitor, monkeypatch):
    now = psutil.Process().create_time()
    with pytest.raises(HTTPException) as error:
        monitor.stop(os.getpid(), now, True)
    assert error.value.status_code == 403
    for pid, created in [(os.getpid(), now - 1), (99999999, 1)]:
        with pytest.raises(HTTPException) as error:
            monitor.stop(pid, created, False)
        assert error.value.status_code == 409


@pytest.mark.parametrize('force', [False, True])
def test_signals_only_the_selected_test_child(monitor, force):
    children = [subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']) for _ in range(2)]
    try:
        target, sibling = children
        created = psutil.Process(target.pid).create_time()
        response = monitor.stop(target.pid, created, force)
        assert response['signal'] == ('SIGKILL' if force else 'SIGTERM')
        assert target.wait(timeout=3) < 0
        assert sibling.poll() is None
    finally:
        for child in children:
            if child.poll() is None:
                child.kill()
            child.wait(timeout=3)


def test_snapshot_has_host_usage_samples_cpu_and_shares_cache(monitor, monkeypatch):
    first = monitor.snapshot()
    assert first['host']['memory_total'] > 0
    assert first['host']['cpu_percent'] is None
    assert any(p['pid'] == os.getpid() and p['protected'] for p in first['processes'])
    assert monitor.snapshot() is first
    before = time.monotonic()
    monkeypatch.setattr(resources.time, 'monotonic', lambda: before + 3)
    second = monitor.snapshot()
    assert all(p['cpu_percent'] is not None for p in second['processes'] if p['pid'] == os.getpid())
    assert all('cmdline' not in row for row in second['processes'])


def test_pane_discovery_uses_all_panes_and_filters_unrelated_names(monkeypatch):
    calls = []
    monkeypatch.setattr(resources.tmux_sockets, 'generations', lambda: [{'name': 'default'}])
    def run(command, **kwargs):
        calls.append(command)
        return SimpleNamespace(returncode=0, stdout='10|neurona-home-a\n11|personal-shell\n12|lab-old\n', stderr='')
    monkeypatch.setattr(resources.subprocess, 'run', run)
    roots, warnings = resources._pane_roots()
    assert set(roots) == {10, 12}
    assert not warnings
    assert 'list-panes' in calls[0] and '-a' in calls[0]


def test_resource_routes_require_admin_and_validate_actions(client, monkeypatch):
    # No real process signal is issued by this route test.
    calls = []
    monkeypatch.setattr(resources.Monitor, 'stop', lambda *args: calls.append(args) or {'signal': 'SIGTERM'})
    monkeypatch.setattr(resources.Monitor, 'snapshot', lambda self: {'processes': [], 'host': {}})
    assert client.get('/api/resources').status_code == 200
    assert client.post('/api/resources/stop', json={'pid': 100, 'created': 1, 'action': 'kill-all'}).status_code == 422
    assert not calls
    assert client.post('/api/resources/scans', json={'paused': True}).json()['paused']
    assert not client.post('/api/resources/scans', json={'paused': False}).json()['paused']
    assert client.post('/api/admin/users', json={'username': 'viewer', 'name': 'Viewer', 'role': 'user', 'password': 'test', 'vaults': []}).status_code == 200
    client.post('/api/auth/logout')
    assert client.get('/api/resources').status_code == 401
    client.post('/api/auth/login', json={'username': 'viewer', 'password': 'test'})
    assert client.get('/api/resources').status_code in (403, 404)
    assert client.post('/api/resources/stop', json={'pid': 100, 'created': 1}).status_code in (403, 404)
    assert client.post('/api/resources/scans', json={'paused': True}).status_code in (403, 404)
    assert not calls
