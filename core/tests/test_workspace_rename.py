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
