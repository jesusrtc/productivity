"""Migration tests use literal pre-rename documents, not renamed fixtures."""
import json
from pathlib import Path

from click.testing import CliRunner

from lab import assistant, index, naming, paths
from lab.cli import main


def test_old_registry_and_env_resolve_without_changing_identity(tmp_path, monkeypatch):
    home = tmp_path / 'home'
    home.mkdir()
    old_root = tmp_path / 'local'
    old_root.mkdir()
    monkeypatch.setenv('LAB_HOME', str(home))
    (home / 'workspaces.toml').write_text(f'active = "local"\n[[workspaces]]\nid = "local"\nname = "Local"\npath = "{old_root}"\n')
    assert paths.read_vault_registry()['vaults'][0]['id'] == 'local'
    assert paths.active_vault() == old_root
    monkeypatch.setenv('LAB_WORKSPACE', str(old_root))
    assert paths.find_vault_root() == old_root
    monkeypatch.setenv('LAB_VAULT', str(tmp_path / 'ssd'))
    assert paths.find_vault_root() == tmp_path / 'ssd'
    paths.register_vault(old_root, name='Local')
    assert (home / 'vaults.toml').is_file()
    assert len(paths.read_vault_registry()['vaults']) == 1


def test_old_work_area_remains_readable_and_mutable(monorepo, monkeypatch):
    (monorepo / 'workspaces').rmdir()
    old = monorepo / 'projects' / 'demo'
    old.mkdir(parents=True)
    metadata = {'id': 'demo', 'name': 'Demo', 'description': '', 'status': 'active', 'tags': [], 'labels': [], 'created': '2026-09-09', 'updated': '2026-09-09'}
    (old / 'project.json').write_text(json.dumps(metadata))
    (old / 'tasks.json').write_text('{"next_id": 1, "tasks": []}')
    assert paths.workspace_dir(monorepo, 'demo') == old
    result = CliRunner().invoke(main, ['workspace', 'set', 'demo', 'name', 'Renamed'])
    assert result.exit_code == 0, result.output
    assert json.loads((old / 'project.json').read_text())['name'] == 'Renamed'
    rows = index.build_index(monorepo)['workspaces']
    assert rows[0]['path'] == 'projects/demo'
    assert rows[0]['id'] == 'demo'


def test_legacy_terminal_fields_preserve_commands_paths_and_ids():
    old = {'tmux-name': {'project_id': 'demo', 'workspace': 'local', 'cwd': '/old/projects/demo', 'label': 'workspace project review'}}
    expected = {'tmux-name': {'workspace_id': 'demo', 'vault': 'local', 'cwd': '/old/projects/demo', 'label': 'workspace project review'}}
    assert naming.runtime_metadata(old) == expected
    assert naming.runtime_metadata(expected) == expected
    assert naming.runtime_metadata({'x': {'project_id': '__workspace__'}})['x']['workspace_id'] == '__vault__'


def test_assistant_legacy_mapping_and_tasks(tmp_path):
    folder = tmp_path / 'projects' / 'demo'
    (folder / 'tasks').mkdir(parents=True)
    (folder / 'project.md').write_text('---\nid: "demo"\nworkspace: "local"\nworkspace_path: "/data/local"\nproject_path: "/data/local/projects/demo"\n---\nContext\n')
    (folder / 'tasks' / 'task.md').write_text('---\nid: "task"\nproject: "demo"\ntitle: "Keep project text"\nstatus: "ready"\n---\nBody\n')
    row = list(assistant.iter_workspaces(tmp_path))[0]
    assert row['vault'] == 'local'
    assert row['workspace_path'] == '/data/local/projects/demo'
    tasks = list(assistant.iter_tasks(tmp_path))
    assert tasks[0]['workspace'] == 'demo'
    assert tasks[0]['title'] == 'Keep project text'


def test_legacy_notebook_path_from_inside_a_workspace(tmp_path, monkeypatch):
    from lab.commands.notebook import _notebook_path
    folder = tmp_path / 'projects' / 'demo'
    folder.mkdir(parents=True)
    monkeypatch.chdir(folder)
    assert _notebook_path(tmp_path, 'projects/demo/a.ipynb') == 'projects/demo/a.ipynb'
