"""Exercise pre-rename data through the new public contract."""
import json

from core import auth, vault_config
from core.notebook_runtime import workspace_for_notebook
from core.routes import term
from core.server_config import read_server_config


def test_old_vault_config_reads_and_updates_to_canonical_file(tmp_path):
    old = {'version': 1, 'project': {'features': ['files']}, 'display': {'color': '#123456'}}
    (tmp_path / 'workspace.json').write_text(json.dumps(old))
    loaded = vault_config.load_vault_config(tmp_path)
    assert loaded['valid']
    assert loaded['config']['workspace']['features'] == ['files']
    vault_config.update_appearance(tmp_path, 'Local', '#abcdef')
    assert (tmp_path / 'vault.json').is_file()
    updated = vault_config.load_vault_config(tmp_path)['config']
    assert updated['workspace']['features'] == ['files']
    assert updated['name'] == 'Local'
    assert json.loads((tmp_path / 'workspace.json').read_text()) == old


def test_existing_account_keeps_exact_vault_grants():
    data = {'version': auth.STORE_VERSION, 'secret': 'preserve-secret', 'users': [
        {'username': 'reviewer', 'name': 'Reviewer', 'role': 'user', 'password_sha256': 'existing-hash', 'workspaces': ['local'], 'disabled': False},
    ]}
    normalized, changed = auth._normalize_store(data)
    row = next(row for row in normalized['users'] if row['username'] == 'reviewer')
    assert changed
    assert row['vaults'] == ['local']
    assert row['password_sha256'] == 'existing-hash'
    assert 'workspaces' not in row
    assert auth.can_access_vault(row, 'local')
    assert not auth.can_access_vault(row, 'ssd')


def test_legacy_workspace_discovery_api_and_notebook(client, monorepo):
    (monorepo / 'workspaces').rmdir()
    folder = monorepo / 'projects' / 'demo'
    (folder / 'notebooks').mkdir(parents=True)
    (folder / 'project.json').write_text(json.dumps({'id': 'demo', 'name': 'Demo', 'status': 'active', 'description': '', 'tags': [], 'labels': [], 'created': '2026-09-09', 'updated': '2026-09-09'}))
    (folder / 'tasks.json').write_text('{"tasks": [], "next_id": 1}')
    response = client.get('/api/workspaces/demo')
    assert response.status_code == 200, response.text
    assert response.json()['id'] == 'demo'
    assert workspace_for_notebook(monorepo, 'projects/demo/notebooks/a.ipynb') == ('demo', folder)
    listing = client.get('/api/vaults/workspaces')
    assert listing.status_code == 200
    rows = listing.json()['vaults'][0]['workspace_rows']
    assert rows[0]['path'] == str(folder)


def test_old_bookmark_redirects_both_names_together(client, monorepo):
    response = client.get('/?project=%2Fdata%2Fprojects%2Fdemo&workspace=ssd', follow_redirects=False)
    assert response.status_code == 307
    location = response.headers['location']
    assert 'workspace=%2Fdata%2Fprojects%2Fdemo' in location
    assert 'vault=ssd' in location
    assert 'project=' not in location


def test_existing_proxy_metadata_and_vault_terminal_are_preserved(tmp_path, monkeypatch):
    folder = tmp_path / 'projects' / 'demo'
    folder.mkdir(parents=True)
    (folder / 'project.json').write_text(json.dumps({'proxies': [{'name': 'web', 'port': 8123}]}))
    servers, source = read_server_config(folder)
    assert servers[0]['port'] == 8123
    assert source == 'project.json'
    monkeypatch.setenv('LAB_TMUX_PREFIX', 'lab-')
    row = term._reconstruct_meta_entry(tmp_path, 'lab-__workspace__-terminal')
    assert row['workspace_id'] == '__vault__'
    assert row['cwd'] == str(tmp_path)


def test_legacy_assistant_document_and_shared_file_links(tmp_path):
    from core.routes.assistant import _safe_task_path
    from core.routes.cerebro import _resolve_cerebro_path
    folder = tmp_path / 'projects' / 'demo' / 'tasks'
    folder.mkdir(parents=True)
    task = folder / 'one.md'
    task.write_text('A task')
    assert _safe_task_path(tmp_path, 'projects/demo/tasks/one.md') == task
    assert _resolve_cerebro_path(tmp_path, 'workspaces/demo/tasks/one.md') == task


def test_config_api_exposes_the_existing_source_filename(client, monorepo):
    (monorepo / 'workspace.json').write_text('{"version": 1, "project": {"features": []}}')
    response = client.get('/api/vault/config')
    assert response.status_code == 200
    assert response.json()['source'] == 'workspace.json'
    assert response.json()['config']['workspace']['features'] == []


def test_repository_discovery_honors_the_legacy_vault_environment(tmp_path, monkeypatch):
    from core.diff_parser import _monorepo_root
    monkeypatch.delenv('LAB_VAULT', raising=False)
    monkeypatch.setenv('LAB_WORKSPACE', str(tmp_path))
    assert _monorepo_root() == tmp_path
