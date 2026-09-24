"""Large histories expose local work without scanning or generating patches."""
import os
import subprocess
import time

import pytest

from core.routes import diff


def git(root, *args, date=None):
    env = dict(os.environ)
    if date:
        env.update(GIT_AUTHOR_DATE=date, GIT_COMMITTER_DATE=date)
    return subprocess.run(
        ['git', '-C', str(root), *args], capture_output=True, text=True,
        check=True, env=env,
    ).stdout.strip()


def init_repo(root):
    git(root, 'init')
    git(root, 'config', 'user.name', 'History Test')
    git(root, 'config', 'user.email', 'history@example.test')


def test_local_history_never_waits_for_log_or_builds_patches(client, monorepo, monkeypatch):
    init_repo(monorepo)
    source = monorepo / 'note.txt'
    source.write_text('initial\n')
    git(monorepo, 'add', 'note.txt')
    git(monorepo, 'commit', '-m', 'initial')
    source.write_text('staged\n')
    git(monorepo, 'add', 'note.txt')
    source.write_text('unstaged\n')
    (monorepo / 'empty.txt').touch()
    real_run = subprocess.run

    def no_history_or_patch(args, **kwargs):
        if args[0] == 'git':
            assert not any(arg in args for arg in ('log', 'diff', 'show')), args
        return real_run(args, **kwargs)

    monkeypatch.setattr(diff.subprocess, 'run', no_history_or_patch)
    for file, states in [('note.txt', ['staged', 'unstaged']), ('empty.txt', ['untracked'])]:
        response = client.get('/api/workspace-entry/history', params={
            'path': str(monorepo), 'file': file, 'phase': 'working-tree',
        })
        assert response.status_code == 200, response.text
        assert response.json()['commits'][0]['sha'] == 'WORKTREE'
        assert response.json()['commits'][0]['states'] == states


def test_recent_pages_expand_across_rename_and_keep_original_head(client, monorepo, monkeypatch):
    init_repo(monorepo)
    source = monorepo / 'old-name.txt'
    source.write_text('original\n')
    git(monorepo, 'add', source.name)
    git(monorepo, 'commit', '-m', 'old original', date='2020-01-01T12:00:00Z')
    source.write_text('original\nsecond line\n')
    git(monorepo, 'commit', '-am', 'old edit', date='2020-01-02T12:00:00Z')
    git(monorepo, 'mv', source.name, 'renamed.txt')
    git(monorepo, 'commit', '-m', 'rename')
    source = monorepo / 'renamed.txt'
    for index in range(23):
        source.write_text(source.read_text() + f'change {index}\n')
        git(monorepo, 'commit', '-am', f'recent {index}')
    expected = git(monorepo, 'log', '--format=%H', '--follow', '--', source.name).splitlines()
    params = {'path': str(monorepo), 'file': source.name, 'phase': 'commits',
              'limit': 20, 'since': int(time.time()) - 60 * 86400}
    # Commit-only pages must not check status or read a worktree patch.
    monkeypatch.setattr(diff, '_entry_worktree_states', lambda *_: pytest.fail('unexpected local scan'))
    response = client.get('/api/workspace-entry/history', params=params)
    assert response.status_code == 200, response.text
    first = response.json()
    assert len(first['commits']) == 20
    assert first['has_more'] and first['can_load_older']
    assert [item['sha'] for item in first['commits']] == expected[:20]
    source.write_text(source.read_text() + 'new commit while browsing\n')
    git(monorepo, 'commit', '-am', 'new HEAD')
    params.update(offset=first['next_offset'], revision=first['revision'])
    second = client.get('/api/workspace-entry/history', params=params).json()
    assert len(second['commits']) == 4
    assert not second['has_more'] and second['can_load_older']
    params.update(offset=second['next_offset'], since=0)
    third = client.get('/api/workspace-entry/history', params=params).json()
    assert [item['message'] for item in third['commits']] == ['old edit', 'old original']
    assert not third['has_more'] and not third['can_load_older']
    assert [item['sha'] for page in [first, second, third] for item in page['commits']] == expected
    # Repository/folder history supports the same pages without --follow.
    repo = client.get('/api/workspace-entry/history', params={**params, 'file': '.', 'offset': 0}).json()
    assert [item['sha'] for item in repo['commits']] == expected[:20]


def test_recent_empty_window_and_unborn_repository(client, monorepo):
    init_repo(monorepo)
    source = monorepo / 'new.txt'
    source.touch()
    params = {'path': str(monorepo), 'file': source.name, 'limit': 20,
              'since': int(time.time()) - 60 * 86400}
    unborn = client.get('/api/workspace-entry/history', params=params).json()
    assert unborn['commits'][0]['states'] == ['untracked']
    assert not unborn['can_load_older'] and not unborn['has_more']
    git(monorepo, 'add', source.name)
    git(monorepo, 'commit', '-m', 'old only', date='2020-01-01T12:00:00Z')
    recent = client.get('/api/workspace-entry/history', params=params).json()
    assert recent['commits'] == []
    assert recent['can_load_older'] and not recent['has_more']
    older = client.get('/api/workspace-entry/history', params={**params, 'since': 0, 'revision': recent['revision']}).json()
    assert older['commits'][0]['message'] == 'old only'
    for invalid in [{'offset': -1}, {'since': -1}, {'revision': '--all'}, {'phase': 'bad'}]:
        assert client.get('/api/workspace-entry/history', params={**params, **invalid}).status_code == 400


def test_status_rename_skips_source_path_record(client, monorepo):
    # Keep background vault logs/index writes outside the Git fixture.
    repo = monorepo / "rename-repo"
    repo.mkdir()
    init_repo(repo)
    # A source path that looks like a status record must never be parsed as one.
    (repo / ' M fake.txt').write_text('content\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'initial')
    git(repo, 'mv', ' M fake.txt', 'renamed.txt')
    response = client.get('/api/workspace-entry/history', params={
        'path': str(repo), 'file': '.', 'phase': 'working-tree',
    })
    assert response.json()['commits'][0]['states'] == ['staged']
