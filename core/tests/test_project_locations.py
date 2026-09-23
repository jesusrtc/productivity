"""Project discovery and shared locations with real directories and Git worktrees."""
import subprocess

from lab import projects, settings


def test_project_defaults_validation_and_no_folder_creation(client, monorepo, tmp_path):
    config = client.get('/api/settings/global').json()
    assert config['projectsFolder'] == '~/src'
    assert config['worktreesFolder'] == '~/src/.worktrees'
    destination = tmp_path / 'not-created'
    response = client.post('/api/settings/global', json={'projectsFolder': str(destination)})
    assert response.status_code == 200
    assert not destination.exists()
    for patch in [{'projectsFolder': ''}, {'worktreesFolder': 'relative'},
                  {'projectLocations': [{'path': '/ok', 'worktreeFolder': 42}]}]:
        assert client.post('/api/settings/global', json=patch).status_code == 400
    assert settings.load(monorepo)['projectsFolder'] == str(destination)
    catalog = client.get('/api/projects').json()
    assert catalog['projects'] == [] and 'does not exist' in catalog['warning']


def test_catalog_lists_direct_folders_and_custom_projects(client, monorepo, tmp_path):
    source = tmp_path / 'src'
    for name in ['lab', 'ordinary', '.hidden', 'trees', 'ordinary/nested']:
        (source / name).mkdir(parents=True, exist_ok=True)
    (source / 'readme.md').write_text('not a project')
    extra = tmp_path / 'custom project'
    extra.mkdir()
    settings.update_global(monorepo, {'projectsFolder': str(source), 'worktreesFolder': str(source / 'trees'),
        'projectLocations': [{'path': str(extra), 'worktreeFolder': str(tmp_path / 'custom trees')},
                             {'path': str(tmp_path / 'offline')}]})
    data = client.get('/api/projects').json()
    assert [row['name'] for row in data['projects']] == ['custom project', 'lab', 'offline', 'ordinary']
    rows = {row['name']: row for row in data['projects']}
    assert rows['lab']['worktreeFolder'] == str(source / 'trees' / 'lab')
    assert rows['custom project']['worktreeFolder'] == str(tmp_path / 'custom trees')
    assert rows['offline']['available'] is False
    (source / 'new project').mkdir()
    assert 'new project' in [row['name'] for row in client.get('/api/projects').json()['projects']]


def test_register_expands_home_and_relative_paths_atomically(client, monorepo, tmp_path, monkeypatch):
    monkeypatch.setenv('HOME', str(tmp_path))
    custom = tmp_path / 'custom'
    custom.mkdir()
    response = client.post('/api/projects/register', json={'base': str(tmp_path), 'projects': [
        {'path': '~/custom', 'worktreeFolder': '../trees/custom'}, {'path': 'custom'}]})
    assert response.status_code == 200, response.text
    assert {row['path'] for row in response.json()['projects']} == {str(custom)}
    expected = [{'path': str(custom), 'worktreeFolder': str(tmp_path / 'trees/custom')}]
    assert settings.load(monorepo)['projectLocations'] == expected
    # Adding an existing custom project in another workspace inherits its
    # configured parent instead of silently clearing it.
    assert client.post('/api/projects/register', json={'projects': [{'path': str(custom)}]}).status_code == 200
    assert settings.load(monorepo)['projectLocations'] == expected
    before = settings.client_settings_file().read_bytes()
    result = client.post('/api/projects/register', json={'projects': [
        {'path': str(custom), 'worktreeFolder': '/elsewhere'}, {'path': '/does-not-exist/lab-test'}]})
    assert result.status_code == 400
    assert settings.client_settings_file().read_bytes() == before
    settings.update_global(monorepo, {'worktreesFolder': '~/changed'})
    assert projects.worktree_folder(settings.load(monorepo), custom) == tmp_path / 'trees/custom'
    settings.update_global(monorepo, {'projectLocations': [{'path': str(custom)}]})
    assert projects.worktree_folder(settings.load(monorepo), custom) == tmp_path / 'changed/custom'


def test_project_locations_require_admin(client, monorepo, tmp_path):
    from .test_auth_routes import _create_user, _login
    from lab import paths
    from core.routes.diff import _git_status_dir_allowed
    custom = tmp_path / 'private-project'
    custom.mkdir()
    settings.update_global(monorepo, {'projectLocations': [{'path': str(custom)}]})
    assert not _git_status_dir_allowed(custom, monorepo)
    assert _git_status_dir_allowed(custom, monorepo, include_projects=True)
    paths.register_vault(monorepo, name='Main', active=True)
    assert _create_user(client, 'reader', 'test-secret', vaults=['main']).status_code == 200
    client.post('/api/auth/logout')
    _login(client, 'reader', 'test-secret')
    assert client.get('/api/projects').status_code == 403
    assert client.post('/api/projects/register', json={'projects': []}).status_code == 403
    assert client.post('/api/settings', json={'projectsFolder': '/'}).status_code == 403
    assert client.get('/api/git-status', params={'vault': 'main', 'repo': str(custom)}).status_code == 400


def test_worktrees_outside_vault_follow_shared_and_custom_locations(client, monorepo, tmp_path):
    source = tmp_path / 'src'
    repo = source / 'lab'
    repo.mkdir(parents=True)
    subprocess.run(['git', 'init', '-q', str(repo)], check=True)
    subprocess.run(['git', '-C', str(repo), '-c', 'user.name=Test', '-c', 'user.email=test@example.com',
                    'commit', '-qm', 'Initial', '--allow-empty'], check=True)
    parent = tmp_path / 'trees/lab'
    parent.mkdir(parents=True)
    subprocess.run(['git', '-C', str(repo), 'worktree', 'add', '-qb', 'new-feature-branch', str(parent / 'new-feature-branch')], check=True)
    preview = client.get('/api/sidebar-worktrees', params={'repo': str(repo), 'path': str(parent), 'preview': True})
    assert preview.status_code == 200 and len(preview.json()['folders']) == 1
    assert not settings.client_settings_file().exists()
    settings.update_global(monorepo, {'projectsFolder': str(source), 'worktreesFolder': str(tmp_path / 'trees')})
    response = client.get('/api/sidebar-worktrees', params={'repo': str(repo), 'path': str(parent)})
    assert response.status_code == 200, response.text
    assert response.json()['folders'][0]['path'] == str(parent / 'new-feature-branch')
    assert client.get('/api/git-status', params={'repo': str(repo)}).status_code == 200
    missing = client.get('/api/sidebar-worktrees', params={'repo': str(repo), 'path': str(tmp_path / 'empty'), 'optional': True})
    assert missing.status_code == 200 and missing.json()['folders'] == []
    # Custom project and worktree overrides remain usable outside both roots.
    settings.update_global(monorepo, {'projectsFolder': str(tmp_path / 'other'), 'worktreesFolder': str(tmp_path / 'other-trees'),
        'projectLocations': [{'path': str(repo), 'worktreeFolder': str(parent)}]})
    assert client.get('/api/sidebar-worktrees', params={'repo': str(repo), 'path': str(parent)}).status_code == 200
