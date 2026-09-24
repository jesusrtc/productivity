#!/usr/bin/env python3
"""Benchmark the six real shallow checkouts and full linked worktrees.

Requires disposable clones under --root (never use personal checkouts).
Sets up fixture commits/edits only in these clones. All samples, including
cold misses, are retained. CLI creates the isolated vault/workspace metadata.
"""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import threading
import time

REPOS = ['linux', 'llvm-project', 'kubernetes', 'cpython', 'rust', 'git']


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--browser', action='store_true')
    parser.add_argument('--clear-cache', action='store_true', help='Remove only this disposable fixture cache before starting')
    args = parser.parse_args()
    root = args.root.resolve()
    checkout = Path(__file__).resolve().parents[2]
    os.environ.update(LAB_HOME=str(root.parent / 'lab-large-benchmark-config'), LAB_VAULT=str(root),
                      LAB_ENV_FILE=str(root.parent / 'no-benchmark-env'), LAB_ROOT=str(root),
                      LAB_ASSISTANT_HOME=str(root / '.lab/benchmark-assistant'),
                      LAB_SERVER_SUPERVISOR='0', LAB_DOCUMENT_TERMINALS_SUPERVISOR='0')
    os.environ.pop('LAB_WORKSPACE', None)

    def lab(*arguments):
        subprocess.run([sys.executable, '-m', 'lab', *arguments], check=True, stdout=subprocess.DEVNULL)

    if not (root / 'lab.toml').exists():
        lab('init', str(root), '--name', 'Large repository benchmark', '--no-example', '--no-git')
    if not (root / 'workspaces/sidebar-benchmark').exists():
        lab('workspace', 'new', 'sidebar-benchmark')

    def git(repo, *arguments):
        return subprocess.check_output(['git', '-C', str(repo), '-c', 'core.hooksPath=/dev/null',
            '-c', 'commit.gpgsign=false', '-c', 'user.name=Lab Benchmark',
            '-c', 'user.email=benchmark@example.invalid', *arguments], stderr=subprocess.DEVNULL).decode().strip()

    fixtures = []
    for name in REPOS:
        repo = root / name
        if not (repo / 'lab-benchmark-committed.txt').exists():
            git(repo, 'checkout', '-b', 'lab-sidebar-benchmark')
            (repo / 'lab-benchmark-unstaged.txt').write_text('base\n')
            git(repo, 'add', 'lab-benchmark-unstaged.txt')
            git(repo, 'commit', '-m', 'Lab benchmark base')
            git(repo, 'update-ref', 'refs/heads/main', git(repo, 'rev-parse', 'HEAD'))
            (repo / 'lab-benchmark-committed.txt').write_text('branch change\n')
            git(repo, 'add', 'lab-benchmark-committed.txt')
            git(repo, 'commit', '-m', 'Lab benchmark branch change')
        worktree = root / '.worktrees' / name
        if not worktree.exists():
            git(repo, 'worktree', 'add', '--detach', str(worktree), 'HEAD')
        for path in (repo, worktree):
            (path / 'lab-benchmark-unstaged.txt').write_text('unstaged edit\n')
            (path / 'lab-benchmark-staged.txt').write_text('staged addition\n')
            git(path, 'add', 'lab-benchmark-staged.txt')
        fixtures.append({'name': name, 'path': str(repo), 'worktree': str(worktree),
                         'head': git(repo, 'rev-parse', 'HEAD~2'),
                         'tracked': len(git(repo, 'ls-files', '-z').split('\0')) - 1})
        print('Fixture ready:', name, flush=True)

    import httpx
    import uvicorn
    from core.main import create_app
    from core import auth
    if args.clear_cache:
        (root / '.lab/cache/sidebar-v1.sqlite3').unlink(missing_ok=True)
    app = create_app()
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    os.environ['LAB_PORT'] = str(sock.getsockname()[1])
    server = uvicorn.Server(uvicorn.Config(app, log_level='error', access_log=False,
                                         ws_per_message_deflate=False))
    thread = threading.Thread(target=lambda: server.run(sockets=[sock]))
    thread.start()
    deadline = time.monotonic() + 20
    while not server.started:
        assert time.monotonic() < deadline
        time.sleep(.01)
    cookie = auth.issue_session(auth.get_user('admin'))
    results = {'fixtures': fixtures, 'samples': [], 'shallow_depth': 25, 'empty_cache_at_start':args.clear_cache}
    try:
        if args.browser:
            env = {**os.environ, 'LAB_PROBE_COOKIE': cookie,
                   'LAB_PROJECT_FIXTURES': json.dumps(fixtures), 'LAB_BENCHMARK_ROOT': str(root)}
            process = subprocess.run(['node', str(checkout / 'scripts/perf/large_project_sidebar.mjs'),
                                      url, str(args.output.with_suffix('.browser.json'))], env=env)
            assert process.returncode == 0, 'Browser benchmark failed'
        with httpx.Client(base_url=url, cookies={auth.SESSION_COOKIE: cookie}, timeout=30) as client:
            for fixture in fixtures:
                for kind in ('path', 'worktree'):
                    repo = fixture[kind]
                    queries = [('/api/sidebar-directory', {'path': repo}, 'directory'),
                               ('/api/sidebar-recent-files', {'repo':repo, 'mode':'uncommitted','cached':'true'}, 'uncommitted'),
                               ('/api/sidebar-recent-files', {'repo':repo, 'mode':'local-main','cached':'true'}, 'local-main'),
                               ('/api/workspace-entry/history', {'path':repo, 'file':'.', 'phase':'commits',
                                'limit':20, 'since':int(time.time()) - 60*86400, 'cached':'true'}, 'history')]
                    for route, params, action in queries:
                        for sample in range(10):
                            start = time.perf_counter()
                            statuses = []
                            while True:
                                response = client.get(route, params=params)
                                statuses.append(response.status_code)
                                response.raise_for_status()
                                if response.status_code != 202:
                                    break
                                assert time.perf_counter() - start < 30
                                time.sleep(.15)
                            ms = (time.perf_counter() - start) * 1000
                            data = response.json()
                            if action in ('uncommitted', 'local-main'):
                                expected = {'lab-benchmark-staged.txt', 'lab-benchmark-unstaged.txt'}
                                if action == 'local-main': expected.add('lab-benchmark-committed.txt')
                                assert expected <= set(data['files']), (fixture['name'], action, data)
                            if action == 'history':
                                assert data['commits'][0]['message'] == 'Lab benchmark branch change'
                            results['samples'].append({'repo':fixture['name'], 'kind':kind, 'action':action,
                                                       'sample':sample, 'ms':round(ms,2), 'statuses':statuses})
                    print('Measured:', fixture['name'], kind, flush=True)
        results['sqlite_bytes'] = (root / '.lab/cache/sidebar-v1.sqlite3').stat().st_size
    finally:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(results, indent=2) + '\n')
        server.should_exit = True
        thread.join(timeout=10)


if __name__ == '__main__':
    main()
