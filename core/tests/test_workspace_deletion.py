import json
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from lab import paths


@pytest.fixture
def cleanup(monkeypatch):
    from core import notebook_kernel
    from core.routes import servers, term
    calls = []
    monkeypatch.setattr(servers, '_find_server_workspace', lambda *a: None)
    monkeypatch.setattr(notebook_kernel, 'shutdown_workspace', lambda root, p: calls.append(('notebooks', str(p))))
    monkeypatch.setattr(term, 'kill_workspace_sessions', lambda pid, request, vault: calls.append(('terminals', vault, pid)) or {'killed': ['fixture-session']})
    return calls


def remove(client, pid, path, vault='productivity', confirmed=True):
    return client.request('DELETE', f'/api/workspaces/{pid}?vault={vault}', json={'path': str(path), 'confirmed': confirmed})


def test_delete_removes_only_confirmed_workspace(client, monorepo, seed_workspace, cleanup, tmp_path):
    target = seed_workspace('alpha')
    survivor = seed_workspace('beta')
    external = tmp_path / 'external'
    external.mkdir()
    (external / 'keep.txt').write_text('keep')
    (target / 'linked').symlink_to(external, target_is_directory=True)
    (target / 'notes' / 'draft.md').write_text('temporary fixture')
    response = remove(client, 'alpha', target)
    assert response.status_code == 200, response.text
    assert not target.exists()
    assert survivor.is_dir()
    assert (external / 'keep.txt').read_text() == 'keep'
    assert cleanup == [('notebooks', str(target)), ('terminals', 'productivity', 'alpha')]
    assert response.json()['killed'] == ['fixture-session']


@pytest.mark.parametrize('confirmed', [False, None])
def test_delete_requires_confirmation(client, seed_workspace, cleanup, confirmed):
    target = seed_workspace('alpha')
    response = remove(client, 'alpha', target, confirmed=confirmed)
    assert response.status_code == 422
    assert target.is_dir()
    assert cleanup == []


def test_delete_rejects_wrong_path_missing_vault_and_pseudo(client, monorepo, seed_workspace, cleanup):
    target = seed_workspace('alpha')
    response = remove(client, 'alpha', monorepo)
    assert response.status_code == 409
    response = remove(client, 'alpha', target, vault='unknown')
    assert response.status_code == 404
    response = remove(client, '__self__', monorepo / 'content')
    assert response.status_code == 400
    response = client.request('DELETE', '/api/workspaces/alpha', json={'path': str(target), 'confirmed': True})
    assert response.status_code == 422
    assert target.is_dir()
    assert cleanup == []


def test_delete_rejects_linked_workspace_and_non_workspace(client, monorepo, seed_workspace, cleanup):
    original = seed_workspace('original')
    linked = monorepo / 'workspaces' / 'linked'
    linked.symlink_to(original, target_is_directory=True)
    response = remove(client, 'linked', linked)
    assert response.status_code == 400
    empty = monorepo / 'workspaces' / 'empty'
    empty.mkdir()
    response = remove(client, 'empty', empty)
    assert response.status_code == 404
    assert original.is_dir() and linked.is_symlink() and empty.is_dir()
    assert cleanup == []


def test_delete_targets_other_vault_without_switching(client, monorepo, seed_workspace, tmp_path, cleanup):
    same_name = seed_workspace('alpha')
    other = tmp_path / 'other'
    target = other / 'workspaces' / 'alpha'
    target.mkdir(parents=True)
    (other / 'content').mkdir()
    (target / 'workspace.json').write_text((same_name / 'workspace.json').read_text())
    paths.write_vault_registry({'active': 'main', 'vaults': [
        {'id': 'main', 'name': 'main', 'path': str(monorepo)},
        {'id': 'other', 'name': 'other', 'path': str(other)},
    ]})
    response = remove(client, 'alpha', target, vault='other')
    assert response.status_code == 200, response.text
    assert not target.exists()
    assert same_name.is_dir()
    assert paths.read_vault_registry()['active'] == 'main'
    assert cleanup[-1] == ('terminals', 'other', 'alpha')


def test_delete_aborts_if_server_cannot_stop(client, seed_workspace, cleanup, monkeypatch):
    from fastapi import HTTPException
    from core.routes import servers
    target = seed_workspace('alpha')
    monkeypatch.setattr(servers, '_find_server_workspace', lambda *a: {'has_stop': True})
    def fail(*a):
        raise HTTPException(status_code=504, detail='stop timed out')
    monkeypatch.setattr(servers, 'stop_server', fail)
    response = remove(client, 'alpha', target)
    assert response.status_code == 504
    assert target.is_dir()
    assert cleanup == []


def test_shutdown_workspace_preserves_other_kernels(tmp_path, monkeypatch):
    from core import notebook_kernel
    root = tmp_path / 'vault'
    workspace = root / 'workspaces' / 'alpha'
    target = SimpleNamespace(close_sync=Mock())
    sibling = SimpleNamespace(close_sync=Mock())
    other = SimpleNamespace(close_sync=Mock())
    sessions = {
        (str(root), 'workspaces/alpha/notebooks/a.ipynb'): target,
        (str(root), 'workspaces/alpha-other/notebooks/b.ipynb'): sibling,
        (str(tmp_path / 'other'), 'workspaces/alpha/notebooks/a.ipynb'): other,
    }
    monkeypatch.setattr(notebook_kernel, '_sessions', sessions)
    notebook_kernel.shutdown_workspace(root, workspace)
    target.close_sync.assert_called_once_with()
    sibling.close_sync.assert_not_called()
    other.close_sync.assert_not_called()
    assert len(sessions) == 2


def test_delete_denies_unassigned_vault(client, monorepo, seed_workspace, cleanup):
    target = seed_workspace('alpha')
    paths.write_vault_registry({'active': 'main', 'vaults': [
        {'id': 'main', 'name': 'main', 'path': str(monorepo)},
    ]})
    response = client.post('/api/admin/users', json={
        'username': 'limited', 'name': 'Limited', 'role': 'user',
        'password': 'fixture-password', 'vaults': [],
    })
    assert response.status_code == 200, response.text
    client.post('/api/auth/logout')
    response = client.post('/api/auth/login', json={'username': 'limited', 'password': 'fixture-password'})
    assert response.status_code == 200, response.text
    response = remove(client, 'alpha', target, vault='main')
    assert response.status_code == 404
    assert target.is_dir()
    assert cleanup == []
