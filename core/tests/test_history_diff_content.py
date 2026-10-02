"""History previews tolerate repository encodings and bound content before parsing."""
import pytest

from core.routes import diff
from .test_history_pagination import git, init_repo


def test_history_diff_handles_non_utf8_and_binary_companions(client, monorepo):
    repo = monorepo / 'encoding-repo'
    repo.mkdir()
    init_repo(repo)
    (repo / 'note.txt').write_text('selected\n')
    (repo / 'legacy.txt').write_bytes(b'legacy \xc0 content\n')
    (repo / 'image.bin').write_bytes(b'\0\xc0\xff\x01')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'Mixed encodings')
    sha = git(repo, 'rev-parse', 'HEAD')

    for revision in [sha, 'WORKTREE']:
        if revision == 'WORKTREE':
            (repo / 'note.txt').write_text('changed\n')
            (repo / 'legacy.txt').write_bytes(b'changed \xc0 content\n')
            (repo / 'new.txt').write_bytes(b'untracked \xff text\n')
        response = client.get('/api/workspace-entry/history-diff', params={
            'path': str(repo), 'file': 'note.txt', 'sha': revision,
        })
        assert response.status_code == 200, response.text
        files = response.json()['files']
        assert files[0]['filename'] == 'note.txt'
        legacy = next(file for file in files if file['filename'] == 'legacy.txt')
        assert any('\ufffd' in line['content'] for hunk in legacy['hunks'] for line in hunk['lines'])
        if revision == sha:
            assert next(file for file in files if file['filename'] == 'image.bin')['hunks'] == []
        else:
            assert 'new.txt' in response.json()['changed_files']


@pytest.mark.parametrize('revision', ['commit', 'WORKTREE', 'untracked'])
def test_history_diff_rejects_oversized_bytes_before_decoding_or_parsing(client, monorepo, monkeypatch, revision):
    repo = monorepo / 'large-repo'
    repo.mkdir()
    init_repo(repo)
    (repo / 'note.txt').write_text('small\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'Initial')
    # No NUL: Git treats even invalid UTF-8 as text. The bad byte used to
    # cause a UnicodeDecodeError before the route could inspect the output.
    target = repo / ('new.txt' if revision == 'untracked' else 'note.txt')
    target.write_bytes(b'x' * (diff._ENTRY_DIFF_MAX_BYTES + 1) + b'\xc0\n')
    sha = 'WORKTREE'
    if revision == 'commit':
        git(repo, 'add', '.')
        git(repo, 'commit', '-m', 'Large text')
        sha = git(repo, 'rev-parse', 'HEAD')
    monkeypatch.setattr(diff, 'parse_unified_diff', lambda *_: pytest.fail('Oversized patches must never reach the parser'))
    response = client.get('/api/workspace-entry/history-diff', params={
        'path': str(repo), 'file': 'note.txt', 'sha': sha,
    })
    assert response.status_code == 413, response.text
    assert 'too large to render' in response.json()['detail']


def test_worktree_history_caps_aggregate_untracked_content(client, monorepo, monkeypatch):
    repo = monorepo / 'aggregate-repo'
    repo.mkdir()
    init_repo(repo)
    (repo / 'note.txt').write_text('initial\n')
    git(repo, 'add', '.')
    git(repo, 'commit', '-m', 'Initial')
    for name in ['one.txt', 'two.txt']:
        (repo / name).write_text('x' * 500 + '\n')
    monkeypatch.setattr(diff, '_ENTRY_DIFF_MAX_BYTES', 1000)
    response = client.get('/api/workspace-entry/history-diff', params={
        'path': str(repo), 'file': 'note.txt', 'sha': 'WORKTREE',
    })
    assert response.status_code == 413, response.text
