"""File history uses the same configured external roots as the sidebar."""
import subprocess

import pytest
from lab import paths, settings


@pytest.mark.parametrize('location', ['project', 'worktree', 'custom-project', 'custom-worktree'])
def test_external_project_history_and_explorer(client, monorepo, tmp_path, location):
    source = tmp_path / 'src'
    trees = tmp_path / 'worktrees'
    repo = (tmp_path / 'custom' if location.startswith('custom') else source) / 'lab'
    repo.mkdir(parents=True)
    file = 'checkpoint-frontend/logs/checkpoint-frontend.log'
    (repo / file).parent.mkdir(parents=True)
    (repo / file).write_text('committed log\n')
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), 'add', '.'], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                    'commit', '-qm', 'Add log'], check=True)
    parent = (tmp_path / 'custom-trees' if location == 'custom-worktree' else trees) / 'lab'
    root = repo
    if location.endswith('worktree'):
        parent.mkdir(parents=True)
        root = parent / 'feature'
        subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-qb', 'feature', str(root)], check=True)
    config = {'projectsFolder': str(source), 'worktreesFolder': str(trees)}
    if location.startswith('custom'):
        config['projectLocations'] = [{'path': str(repo), 'worktreeFolder': str(parent)}]
    settings.update_global(monorepo, config)
    (root / file).write_text('working log\n')

    response = client.get('/api/workspace-entry/history', params={'path': str(root), 'file': file})
    assert response.status_code == 200, response.text
    commits = response.json()['commits']
    assert [row['message'] for row in commits] == ['Uncommitted changes', 'Add log']
    for revision in commits:
        diff = client.get('/api/workspace-entry/history-diff', params={
            'path': str(root), 'file': file, 'sha': revision['sha']})
        assert diff.status_code == 200, diff.text
        assert diff.json()['selected_file'] == file
        assert diff.json()['files'][0]['filename'] == file
        assert diff.json()['files'][0]['additions'] == 1

    # The same root check also serves patch previews and file context actions.
    (root / 'change.diff').write_text('diff --git a/note.txt b/note.txt\n--- a/note.txt\n+++ b/note.txt\n@@ -1 +1 @@\n-old\n+new\n')
    assert client.get('/api/workspace-diff-file', params={'path': str(root), 'file': 'change.diff'}).status_code == 200
    assert client.post('/api/workspace-entry', json={'path': str(root), 'name': 'draft.txt'}).status_code == 200
    assert client.patch('/api/workspace-entry', json={'path': str(root), 'entry': 'draft.txt', 'new_name': 'renamed.txt'}).status_code == 200
    assert client.request('DELETE', '/api/workspace-entry', json={'path': str(root), 'entry': 'renamed.txt'}).status_code == 200


def test_external_explorer_keeps_path_and_vault_boundaries(client, monorepo, tmp_path):
    from .test_auth_routes import _create_user, _login

    project = tmp_path / 'src/lab'
    unrelated = tmp_path / 'unrelated'
    project.mkdir(parents=True)
    unrelated.mkdir()
    (unrelated / 'private.txt').write_text('private')
    (project / 'escape').symlink_to(unrelated, target_is_directory=True)
    settings.update_global(monorepo, {'projectsFolder': str(project.parent)})
    for root, file, status in [(unrelated, 'private.txt', 403),
                               (project, '../../unrelated/private.txt', 400),
                               (project, 'escape/private.txt', 400),
                               (project / 'escape', 'private.txt', 403)]:
        response = client.get('/api/workspace-entry/history', params={'path': str(root), 'file': file})
        assert response.status_code == status, response.text
    paths.register_vault(monorepo, name='Main', active=True)
    assert _create_user(client, 'reader', 'test-secret', vaults=['main']).status_code == 200
    client.post('/api/auth/logout')
    _login(client, 'reader', 'test-secret')
    response = client.get('/api/workspace-entry/history', params={
        'vault': 'main', 'path': str(project), 'file': 'note.txt'})
    assert response.status_code == 403, response.text
    response = client.post('/api/workspace-entry?vault=main', json={'path': str(project), 'name': 'blocked.txt'})
    assert response.status_code == 403 and not (project / 'blocked.txt').exists()
