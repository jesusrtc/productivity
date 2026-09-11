"""Folder renames preserve workspace and terminal identity."""
import json
import subprocess
import uuid
from pathlib import Path

import pytest

from lab import paths, storage, workspace_identity
from .test_term_routes import isolated_prefix


def test_rename_moves_folder_and_preserves_live_session(client, monorepo, seed_workspace, isolated_prefix, monkeypatch):
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    old = seed_workspace('demo')
    (old / 'notes' / 'keep.md').write_text('keep this')
    scope = {'root': str(old), 'base_root': str(old), 'project_root': str(old), 'label': 'Root', 'config_scope': str(old)}
    created = client.post('/api/term/sessions', json={
        'workspace_id': 'demo', 'kind': 'terminal', 'linked_scope': scope,
    })
    assert created.status_code == 200, created.text
    session = created.json()
    assert session['name'] == 'neurona-' + uuid.UUID(session['session_id']).hex
    ui = paths.ui_state_file(monorepo)
    storage.write_json(ui, {'tab_order': [str(old)], 'terminal_autospawn_disabled': ['demo']})
    result = client.post('/api/workspaces/demo/rename', json={'name': 'New Named Workspace'})
    assert result.status_code == 200, result.text
    new = monorepo / 'workspaces' / 'new-named-workspace'
    assert result.json()['id'] == 'demo'
    assert result.json()['path'] == str(new)
    assert not old.exists()
    assert (new / 'notes' / 'keep.md').read_text() == 'keep this'
    assert paths.workspace_dir(monorepo, 'demo') == new
    assert paths.find_workspace_id_from_pwd(monorepo, new / 'notes') == 'demo'
    assert storage.read_json(ui)['tab_order'] == [str(new)]
    rows = client.get('/api/term/sessions?workspace_id=demo').json()
    assert len(rows) == 1
    assert rows[0]['name'] == session['name']
    assert rows[0]['session_id'] == session['session_id']
    assert rows[0]['cwd'] == str(new)
    assert rows[0]['linked_scope']['root'] == str(new)
    reopened = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    assert reopened['already_running']
    assert reopened['name'] == session['name']
    # Runtime and folder indexes can be lost without losing the saved tabs.
    paths.sessions_file(monorepo).unlink()
    (paths.vault_state_dir(monorepo) / 'workspace-locations.json').unlink()
    (paths.vault_state_dir(monorepo) / 'session-index.json').unlink()
    recovered = client.get('/api/term/sessions?workspace_id=demo').json()
    assert len(recovered) == 1
    assert recovered[0]['session_id'] == session['session_id']
    assert recovered[0]['name'] == session['name']
    catalog = client.get('/api/repos').json()
    row = next(row for row in catalog if row['name'] == 'demo')
    assert row['path'] == str(new)
    assert row['display_name'] == 'New Named Workspace'


def test_rename_only_selected_vault_and_rejects_collisions(client, monorepo, seed_workspace, tmp_path):
    original = seed_workspace('demo')
    other = tmp_path / 'other'
    target = other / 'workspaces' / 'demo'
    target.mkdir(parents=True)
    (other / 'content').mkdir()
    storage.write_json(target / 'workspace.json', storage.read_json(original / 'workspace.json'))
    paths.write_vault_registry({'active': 'main', 'vaults': [
        {'id': 'main', 'name': 'Main', 'path': str(monorepo)}, {'id': 'other', 'name': 'Other', 'path': str(other)},
    ]})
    (target.parent / 'occupied').mkdir()
    rejected = client.post('/api/workspaces/demo/rename?vault=other', json={'name': 'Occupied'})
    assert rejected.status_code == 400
    assert target.is_dir()
    result = client.post('/api/workspaces/demo/rename?vault=other', json={'name': 'Renamed'})
    assert result.status_code == 200, result.text
    assert original.is_dir()
    assert (target.parent / 'renamed').is_dir()
    assert paths.read_vault_registry()['active'] == 'main'


def test_rename_rolls_back_metadata_when_a_write_fails(monorepo, seed_workspace, monkeypatch):
    old = seed_workspace('demo')
    before = (old / 'workspace.json').read_bytes()
    write = storage.write_json
    def fail(path, data):
        if path.name == 'workspace-locations.json':
            raise OSError('fixture write failure')
        return write(path, data)
    monkeypatch.setattr(storage, 'write_json', fail)
    with pytest.raises(OSError, match='fixture write failure'):
        workspace_identity.rename_workspace(monorepo, 'demo', 'Changed')
    assert old.is_dir()
    assert (old / 'workspace.json').read_bytes() == before
    assert not (old.parent / 'changed').exists()


def test_rename_repairs_nested_git_worktrees(monorepo, seed_workspace, tmp_path):
    old = seed_workspace('demo')
    repo = tmp_path / 'repo'
    def git(*args):
        return subprocess.run(['git', *map(str,args)], check=True, capture_output=True, text=True).stdout
    git('init', repo)
    git('-C', repo, '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '--allow-empty', '-m', 'init')
    worktree = old / 'worktrees' / 'feature'
    git('-C', repo, 'worktree', 'add', '-b', 'feature', worktree)
    moved = workspace_identity.rename_workspace(monorepo, 'demo', 'Changed')
    new_worktree = Path(moved['path']) / 'worktrees' / 'feature'
    assert git('-C', new_worktree, 'rev-parse', '--show-toplevel').strip() == str(new_worktree)
    listing = git('-C', repo, 'worktree', 'list', '--porcelain')
    assert str(new_worktree) in listing
    assert str(worktree) not in listing


def test_rename_waits_for_notebook_file_writes(client, monorepo, seed_workspace):
    from core.routes.nb_exec import _mark_running, _mark_done
    old = seed_workspace('demo')
    target = old / 'notebooks' / 'demo.ipynb'
    _mark_running(target)
    try:
        result = client.post('/api/workspaces/demo/rename', json={'name': 'Changed'})
        assert result.status_code == 400
        assert old.is_dir()
    finally:
        _mark_done(target)
    result = client.post('/api/workspaces/demo/rename', json={'name': 'Changed'})
    assert result.status_code == 200, result.text


def test_rename_preserves_idle_notebook_kernel_and_variables(client, monorepo, seed_workspace):
    import sys
    old = seed_workspace('demo')
    rel = 'workspaces/demo/notebooks/analysis.ipynb'
    saved = client.put('/api/nb/runtime', json={'path': rel, 'spec': {
        'version': 1, 'mode': 'local', 'kind': 'existing', 'python': sys.executable,
        'working_dir': '.', 'packages': [], 'imports': [],
    }})
    assert saved.status_code == 200, saved.text
    built = client.post('/api/nb/runtime/build', json={'path': rel})
    assert built.status_code == 200, built.text
    first = client.post('/api/nb/exec', json={'path': rel, 'code': 'shared_value = 40'})
    assert first.status_code == 200, first.text
    before = client.get('/api/nb/session', params={'path': rel}).json()
    moved = client.post('/api/workspaces/demo/rename', json={'name': 'Changed'})
    assert moved.status_code == 200, moved.text
    next_rel = 'workspaces/changed/notebooks/analysis.ipynb'
    after = client.get('/api/nb/session', params={'path': next_rel}).json()
    assert after['session'] == before['session']
    second = client.post('/api/nb/exec', json={'path': next_rel, 'code': 'import os\nprint(shared_value + 2, os.getcwd())'})
    assert second.status_code == 200, second.text
    output = '\n'.join(row.get('content', '') for row in second.json()['cell']['outputs'])
    assert '42 ' + str(old.parent / 'changed') in output
    assert not old.exists()


def test_legacy_session_survives_repeated_moves_and_reopens_with_same_uuid(
    client, monorepo, seed_workspace, isolated_prefix, monkeypatch,
):
    from core.routes import term
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    old = seed_workspace('demo')
    data = storage.read_json(old / 'workspace.json')
    resume_id = str(uuid.uuid4())
    data['sessions'] = [{'name': 'terminal', 'kind': 'terminal', 'label': 'My terminal',
                         'agent_session_id': resume_id}]
    storage.write_json(old / 'workspace.json', data)
    legacy_name = term._legacy_current_tmux_name_for('demo', 'terminal', monorepo)
    subprocess.run(['tmux', 'new-session', '-d', '-s', legacy_name, '-c', str(old), 'bash'], check=True)
    storage.write_json(paths.sessions_file(monorepo), {legacy_name: {
        'workspace_id': 'demo', 'logical_name': 'terminal', 'kind': 'terminal',
        'cwd': str(old), 'created_at': 1,
    }})
    for display_name in ('First Move', 'Second Move'):
        moved = client.post('/api/workspaces/demo/rename', json={'name': display_name})
        assert moved.status_code == 200, moved.text
        attached = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal', 'name': 'terminal'})
        assert attached.status_code == 200, attached.text
        body = attached.json()
        assert body['name'] == legacy_name
        assert body['already_running']
        assert body['label'] == 'My terminal'
        assert body['cwd'] == moved.json()['path']
    stable_uuid = body['session_id']
    closed = client.delete('/api/term/sessions/' + legacy_name)
    assert closed.status_code == 200, closed.text
    recreated = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal', 'name': 'terminal'})
    assert recreated.status_code == 200, recreated.text
    assert recreated.json()['name'] == 'neurona-' + uuid.UUID(stable_uuid).hex
    assert recreated.json()['session_id'] == stable_uuid
    saved = storage.read_json(paths.workspace_file(monorepo, 'demo'))['sessions']
    assert len(saved) == 1
    assert saved[0]['label'] == 'My terminal'
    assert saved[0]['agent_session_id'] == resume_id
    assert len(client.get('/api/term/sessions?workspace_id=demo').json()) == 1


def test_stale_notebook_write_after_second_rename_cannot_recreate_old_folder(monorepo, seed_workspace):
    from core.routes.nb_exec import _mark_running
    from fastapi import HTTPException
    seed_workspace('demo')
    first = workspace_identity.rename_workspace(monorepo, 'demo', 'First Move')
    workspace_identity.rename_workspace(monorepo, 'demo', 'Second Move')
    with pytest.raises(HTTPException) as exc:
        _mark_running(Path(first['path']) / 'notebooks' / 'demo.ipynb', workspace_id='demo')
    assert exc.value.status_code == 409
    assert not Path(first['path']).exists()


def test_folder_move_keeps_real_tmux_process_and_working_directory(monorepo, seed_workspace):
    import shutil
    import tempfile
    import time
    binary = shutil.which('tmux')
    if not binary:
        pytest.skip('tmux is not installed')
    old = seed_workspace('demo')
    identity = workspace_identity.session_identity(monorepo, 'demo', 'shell')
    name = 'neurona-' + uuid.UUID(identity['session_id']).hex
    # An explicit, short, disposable socket keeps the user's servers untouched.
    with tempfile.TemporaryDirectory(prefix='lab-move-', dir='/tmp') as socket_dir:
        socket = str(Path(socket_dir) / 'tmux.sock')
        def tmux(*args, check=True):
            return subprocess.run([binary, '-S', socket, '-f', '/dev/null', *args],
                                  capture_output=True, text=True, timeout=10, check=check)
        try:
            tmux('new-session', '-d', '-s', name, '-c', str(old), '/bin/sh')
            pid = tmux('display-message', '-p', '-t', name, '#{pane_pid}').stdout.strip()
            moved = workspace_identity.rename_workspace(monorepo, 'demo', 'New Name')
            assert tmux('display-message', '-p', '-t', name, '#{pane_pid}').stdout.strip() == pid
            tmux('send-keys', '-t', name, 'pwd -P', 'Enter')
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline:
                captured = tmux('capture-pane', '-p', '-J', '-t', name).stdout
                if moved['path'] in captured:
                    break
                time.sleep(0.05)
            assert moved['path'] in captured
            assert workspace_identity.session_owner(monorepo, name) == ('demo', 'shell')
            assert not old.exists()
        finally:
            tmux('kill-server', check=False)


def test_delete_after_rename_removes_sessions_and_does_not_reuse_uuid(
    client, monorepo, seed_workspace, isolated_prefix, monkeypatch,
):
    monkeypatch.delenv('LAB_TMUX_PREFIX', raising=False)
    old = seed_workspace('demo')
    survivor = seed_workspace('keep')
    session = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'}).json()
    moved = client.post('/api/workspaces/demo/rename', json={'name': 'Moved'})
    assert moved.status_code == 200, moved.text
    stale = client.request('DELETE', '/api/workspaces/demo?vault=productivity',
                           json={'path': str(old), 'confirmed': True})
    assert stale.status_code == 409
    removed = client.request('DELETE', '/api/workspaces/demo?vault=productivity',
                             json={'path': moved.json()['path'], 'confirmed': True})
    assert removed.status_code == 200, removed.text
    assert session['name'] in removed.json()['killed']
    assert not Path(moved.json()['path']).exists()
    assert survivor.is_dir()
    assert client.get('/api/term/sessions?workspace_id=demo').json() == []
    created = client.post('/api/workspaces', json={'name': 'demo'})
    assert created.status_code == 200, created.text
    replacement = client.post('/api/term/sessions', json={'workspace_id': 'demo', 'kind': 'terminal'})
    assert replacement.status_code == 200, replacement.text
    assert replacement.json()['session_id'] != session['session_id']
    assert replacement.json()['name'] != session['name']
