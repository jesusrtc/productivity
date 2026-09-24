import subprocess
import time


def git(root, *args):
    return subprocess.check_output(['git', '-C', str(root), '-c', 'user.name=Test',
                                   '-c', 'user.email=test@example.invalid',
                                   '-c', 'commit.gpgsign=false', *args], text=True).strip()


def ready(client, url, **params):
    deadline = time.monotonic() + 5
    while True:
        response = client.get(url, params=params)
        if response.status_code != 202:
            assert response.status_code == 200, response.text
            return response.json()
        assert time.monotonic() < deadline
        time.sleep(.01)


def test_project_directory_is_shallow_and_recent_includes_index_and_worktree(client, monorepo):
    root = monorepo / 'project'
    root.mkdir()
    git(root, 'init', '-b', 'main')
    (root / 'src').mkdir()
    for name in ('committed.txt', 'staged.txt', 'unstaged.txt'):
        (root / 'src' / name).write_text('base\n')
    git(root, 'add', '.')
    git(root, 'commit', '-m', 'Base')
    git(root, 'checkout', '-b', 'feature')
    (root / 'src/committed.txt').write_text('branch\n')
    git(root, 'commit', '-am', 'Branch edit')
    (root / 'src/staged.txt').write_text('index\n')
    (root / 'new.txt').write_text('staged addition\n')
    git(root, 'add', 'src/staged.txt', 'new.txt')
    (root / 'src/unstaged.txt').write_text('worktree\n')
    (root / 'untracked.txt').write_text('not recent\n')
    (root / '.hidden').write_text('hidden')
    data = ready(client._inner, '/api/sidebar-directory', path=str(root))
    assert {row['path'] for row in data['entries']} == {'src', 'new.txt', 'untracked.txt'}
    assert next(row for row in data['entries'] if row['path'] == 'src')['type'] == 'dir'
    uncommitted = ready(client._inner, '/api/sidebar-recent-files', repo=str(root), mode='uncommitted', cached=True)
    assert set(uncommitted['files']) == {'src/staged.txt', 'src/unstaged.txt', 'new.txt'}
    main = ready(client._inner, '/api/sidebar-recent-files', repo=str(root), mode='local-main', cached=True)
    assert set(main['files']) == {'src/committed.txt', 'src/staged.txt', 'src/unstaged.txt', 'new.txt'}
    assert {row['path'] for row in main['entries']} == set(main['files'])
    # The narrowed comparison must be the final base-to-working-tree diff,
    # not a union that falsely includes a branch edit reverted locally.
    from core.routes.diff import _sidebar_git_recent_files
    (root / 'src/committed.txt').write_text('base\n')
    changed = _sidebar_git_recent_files(str(root), 'uncommitted')['files']
    narrowed = _sidebar_git_recent_files(str(root), 'local-main', changed)
    assert narrowed == _sidebar_git_recent_files(str(root), 'local-main')
    assert 'src/committed.txt' not in narrowed['files']
    nested = ready(client._inner, '/api/sidebar-directory', path=str(root), directory='src')
    assert len(nested['entries']) == 3
    history = ready(client._inner, '/api/workspace-entry/history', path=str(root), file='.',
                    phase='commits', limit=20, since=int(time.time()) - 60*86400, cached=True)
    assert history['commits'][0]['message'] == 'Branch edit'
    assert history['revision'] == git(root, 'rev-parse', 'HEAD')
    outside = monorepo.parent / 'private'
    outside.mkdir()
    (root / 'escape').symlink_to(outside, target_is_directory=True)
    assert client._inner.get('/api/sidebar-directory', params={'path':str(root), 'directory':'escape'}).status_code == 400
    assert client._inner.get('/api/sidebar-directory', params={'path':str(outside)}).status_code == 403
