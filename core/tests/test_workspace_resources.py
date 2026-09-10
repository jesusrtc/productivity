from types import SimpleNamespace

from core import notebook_kernel
from core.routes import servers, term
from lab import paths


def test_resources_count_live_processes_only_in_selected_vault(client, monorepo, tmp_path, monkeypatch):
    other = tmp_path / 'other'
    (other / 'content').mkdir(parents=True)
    paths.register_vault(monorepo, name='Main', active=True)
    paths.register_vault(other, name='Other', active=False)
    calls = []

    def terminals(root, workspace_id, *, include_agent_details):
        calls.append((root, workspace_id, include_agent_details))
        return [
            {'name': 'shell', 'workspace_id': 'same'},
            {'name': 'agent', 'workspace_id': 'same'},
            {'name': 'web', 'workspace_id': 'same'},
            {'name': 'home', 'workspace_id': '__self__'},
        ]

    monkeypatch.setattr(term, '_sessions_for_root', terminals)
    monkeypatch.setattr(servers, 'list_servers', lambda request: {'servers': [
        {'vault': 'other', 'workspace_id': 'same', 'session_name': 'web', 'status': 'unhealthy'},
        {'vault': 'other', 'workspace_id': 'external', 'session_name': 'unused', 'status': 'external'},
        {'vault': 'other', 'workspace_id': 'stopped', 'session_name': 'dead', 'status': 'stopped'},
        {'vault': 'productivity', 'workspace_id': 'same', 'session_name': 'elsewhere', 'status': 'running'},
    ]})
    monkeypatch.setattr(notebook_kernel, 'live_notebook_paths', lambda root: [
        'workspaces/same/notebooks/one.ipynb', 'workspaces/same/two.ipynb',
        'workspaces/same-extra/three.ipynb', 'repositories/demo.ipynb',
    ])
    response = client.get('/api/vaults/resources?vault=other')
    assert response.status_code == 200, response.text
    assert response.json() == {'vault': 'other', 'workspaces': {
        'same': {'terminals': 2, 'servers': 1, 'kernels': 2},
        'external': {'terminals': 0, 'servers': 1, 'kernels': 0},
        'same-extra': {'terminals': 0, 'servers': 0, 'kernels': 1},
    }}
    assert calls == [(other.resolve(), None, False)]
    assert paths.active_vault() == monorepo.resolve()
    assert client.get('/api/vaults/resources?vault=missing').status_code in (403, 404)


def test_live_notebook_paths_ignores_unstarted_dead_and_other_vault_kernels(tmp_path, monkeypatch):
    root = tmp_path / 'vault'
    def session(alive):
        manager = None if alive is None else SimpleNamespace(is_alive=lambda: alive)
        return SimpleNamespace(process=SimpleNamespace(manager=manager))
    monkeypatch.setattr(notebook_kernel, '_sessions', {
        (str(root), 'workspaces/demo/live.ipynb'): session(True),
        (str(root), 'workspaces/demo/dead.ipynb'): session(False),
        (str(root), 'workspaces/demo/unstarted.ipynb'): session(None),
        (str(tmp_path / 'elsewhere'), 'workspaces/demo/live.ipynb'): session(True),
    })
    assert notebook_kernel.live_notebook_paths(root) == ['workspaces/demo/live.ipynb']
