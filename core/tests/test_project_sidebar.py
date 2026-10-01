import json
import subprocess
import time

import pytest


def test_registered_worktrees_expose_project_buttons_and_distinct_names(client, monorepo, seed_workspace):
    workspace_file = seed_workspace('large-projects') / 'workspace.json'
    metadata = json.loads(workspace_file.read_text())
    metadata['worktrees'] = [
        {'mp': name, 'repo': str(monorepo / 'repositories' / name),
         'dir': str(monorepo / 'trees' / name / 'large-projects'), 'branch': 'feature'}
        for name in ('linux', 'llvm-project')
    ]
    workspace_file.write_text(json.dumps(metadata))
    for name in ('linux', 'llvm-project'):
        (monorepo / 'trees' / name / 'large-projects').mkdir(parents=True)
    response = client.get('/api/repos')
    assert response.status_code == 200
    workspace = next(row for row in response.json() if row['name'] == 'large-projects')
    assert [row['name'] for row in workspace['repos']] == ['linux', 'llvm-project']
    assert workspace['projects'] == [
        {'path': str(monorepo / 'repositories' / name), 'label': name,
         'worktreeFolder': str(monorepo / 'trees' / name)}
        for name in ('linux', 'llvm-project')
    ]


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
    # The total diff omits a branch edit reverted locally to the base.
    from core.routes.diff import _sidebar_git_recent_files
    (root / 'src/committed.txt').write_text('base\n')
    total = _sidebar_git_recent_files(str(root), 'local-main')
    assert set(total['files']) == {'src/staged.txt', 'src/unstaged.txt', 'new.txt'}
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


@pytest.mark.parametrize('scope', ['main', 'project', 'linked-worktree', 'subfolder'])
def test_local_main_includes_edits_after_the_uncommitted_snapshot(client, monorepo, scope):
    source = monorepo / 'project'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    (source / 'src').mkdir()
    for name in ('branch.txt', 'reverted.txt', 'staged.txt', 'unstaged.txt'):
        (source / 'src' / name).write_text('base\n')
    git(source, 'add', '.')
    git(source, 'commit', '-m', 'Base')
    root = source
    if scope == 'linked-worktree':
        root = monorepo / 'feature-tree'
        git(source, 'worktree', 'add', '-b', 'feature', str(root))
    elif scope != 'main':
        git(source, 'checkout', '-b', 'feature')
    if scope != 'main':
        for name in ('branch.txt', 'reverted.txt'):
            (root / 'src' / name).write_text('branch\n')
        git(root, 'commit', '-am', 'Branch edits')
    selected = root / 'src' if scope == 'subfolder' else root

    # Prime the other filter before making new edits. It remains a valid,
    # young snapshot, but must not restrict a new local-main collection.
    previous = ready(client._inner, '/api/sidebar-recent-files',
                     repo=str(selected), mode='uncommitted', cached=True)
    assert previous['files'] == []
    (root / 'src/staged.txt').write_text('index\n')
    (root / 'src/new.txt').write_text('staged addition\n')
    git(root, 'add', 'src/staged.txt', 'src/new.txt')
    (root / 'src/unstaged.txt').write_text('worktree\n')
    (root / 'src/reverted.txt').write_text('base\n')
    (root / 'src/untracked.txt').write_text('untracked\n')

    response = ready(client._inner, '/api/sidebar-recent-files',
                     repo=str(selected), mode='local-main', cached=True)
    prefix = '' if scope == 'subfolder' else 'src/'
    expected = {prefix + name for name in ('staged.txt', 'unstaged.txt', 'new.txt')}
    if scope != 'main':
        expected.add(prefix + 'branch.txt')
    assert set(response['files']) == expected
    assert {row['path'] for row in response['entries']} == expected
    assert response['base_ref'] == 'main'
    direct = client.get('/api/sidebar-recent-files', params={'repo': str(selected), 'mode': 'local-main'})
    assert direct.status_code == 200
    assert set(direct.json()['files']) == expected


@pytest.mark.parametrize('scope', [
    'main', 'feature', 'other-branch', 'worktree-main', 'worktree-feature',
    'worktree-other-branch', 'worktree-detached', 'subfolder-feature',
    'subfolder-worktree',
])
def test_recent_git_filters_distinguish_all_three_file_groups(client, monorepo, scope):
    source = monorepo / 'comparison-project'
    source.mkdir()
    git(source, 'init', '-b', 'main')
    (source / 'src').mkdir()
    base_files = {
        'both-staged.txt', 'both-unstaged.txt', 'uncomm-staged.txt',
        'uncomm-unstaged.txt', 'committed-only.txt', 'unchanged.txt',
    }
    for name in base_files:
        (source / 'src' / name).write_text('main\n')
    (source / '.gitignore').write_text('ignored.txt\n')
    git(source, 'add', '.')
    git(source, 'commit', '-m', 'Local main baseline')
    on_main = scope in {'main', 'worktree-main'}
    branch = 'other-branch' if 'other-branch' in scope else 'feature'
    root = source
    if 'worktree' in scope:
        root = monorepo / 'comparison-tree'
        if on_main:
            git(source, 'checkout', '-b', 'source-checkout')
            git(source, 'worktree', 'add', str(root), 'main')
        else:
            git(source, 'worktree', 'add', '-b', branch, str(root))
    elif not on_main:
        git(source, 'checkout', '-b', branch)
    if not on_main:
        for name in base_files - {'unchanged.txt'}:
            (root / 'src' / name).write_text('branch commit\n')
        for name in ('committed-added.txt', 'both-branch-added.txt'):
            (root / 'src' / name).write_text('branch addition\n')
        git(root, 'add', 'src')
        git(root, 'commit', '-m', 'Changes not merged into local main')
        assert git(root, 'rev-parse', 'HEAD') != git(root, 'rev-parse', 'main')
        if scope == 'worktree-detached':
            git(root, 'checkout', '--detach')
        # These reversions differ from HEAD, but equal local main exactly.
        for name in ('uncomm-staged.txt', 'uncomm-unstaged.txt'):
            (root / 'src' / name).write_text('main\n')
        git(root, 'add', 'src/uncomm-staged.txt')
        (root / 'src/both-branch-added.txt').write_text('edited branch addition\n')
    (root / 'src/both-staged.txt').write_text('staged edit\n')
    (root / 'src/both-unstaged.txt').write_text('unstaged edit\n')
    (root / 'src/both-added.txt').write_text('staged new file\n')
    git(root, 'add', 'src/both-staged.txt', 'src/both-added.txt')
    for name in ('untracked.txt', 'ignored.txt'):
        (root / 'src' / name).write_text('excluded\n')
    if root != source:
        # A dirty primary checkout must not leak into the selected worktree.
        (source / 'src/unchanged.txt').write_text('only in the source checkout\n')

    selected = root / 'src' if scope.startswith('subfolder-') else root
    prefix = '' if scope.startswith('subfolder-') else 'src/'
    both = {prefix + name for name in ('both-staged.txt', 'both-unstaged.txt', 'both-added.txt')}
    uncommitted_only = set()
    main_only = set()
    if not on_main:
        both.add(prefix + 'both-branch-added.txt')
        uncommitted_only = {prefix + name for name in ('uncomm-staged.txt', 'uncomm-unstaged.txt')}
        main_only = {prefix + name for name in ('committed-only.txt', 'committed-added.txt')}

    for cached in (False, True):
        responses = {
            mode: ready(client._inner, '/api/sidebar-recent-files',
                        repo=str(selected), mode=mode, cached=cached)
            for mode in ('uncommitted', 'local-main')
        }
        uncommitted = set(responses['uncommitted']['files'])
        local_main = set(responses['local-main']['files'])
        assert uncommitted & local_main == both
        assert uncommitted - local_main == uncommitted_only
        assert local_main - uncommitted == main_only
        assert uncommitted == both | uncommitted_only
        assert local_main == both | main_only
        assert all(response['available'] for response in responses.values())
        assert responses['local-main']['base_ref'] == 'main'
        if cached:
            for response in responses.values():
                assert {row['path'] for row in response['entries']} == set(response['files'])
