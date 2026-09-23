#!/usr/bin/env python3
"""Measure complete repository-list HTTP responses in a disposable vault.

Retain the first request and every subsequent sample. Use the normal server
lifespan, authentication and watcher. Twenty repos include an empty repository
and detached HEAD; hidden/non-repo entries must stay excluded. Each response
checks all stable metadata and ordering, then a final mutation verifies fresh
branch/commit data. This is endpoint timing, not browser or display latency.
Use --clients 2 for independent HTTP clients released together each round.
"""
import argparse
import contextlib
import json
import os
import socket
import subprocess
import sys
import tempfile
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path


def verify_rows(actual, expected):
    relative = []
    for row in actual:
        if row['last']:
            relative.append(row['last'].pop('when'))
    assert actual == expected, (actual, expected)
    committed = sum(bool(row['last']) for row in expected)
    assert len(relative) == committed and all(isinstance(value, str) and value for value in relative)
    return len(actual)


CHECKOUT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='Prefix for HTTP/server JSON reports')
parser.add_argument('--repos', type=int, default=20)
parser.add_argument('--samples', type=int, default=20)
parser.add_argument('--clients', type=int, default=1, help='Concurrent clients per round')
args = parser.parse_args()
if args.repos < 1 or args.samples < 1 or not 1 <= args.clients <= 8:
    parser.error('Use positive repositories/samples and between one and eight clients')
PREFIX = args.output
PREFIX.parent.mkdir(parents=True, exist_ok=True)
if any(Path(str(PREFIX) + suffix).exists() for suffix in ('-http.json', '-server.json')):
    parser.error('Refusing to replace existing reports')
COUNT = args.repos
source_paths = [str(CHECKOUT / 'core/src'), str(CHECKOUT / 'core/cli/src'), str(CHECKOUT / 'scripts/perf')]
sys.path[:0] = source_paths
os.environ['PYTHONPATH'] = os.pathsep.join(source_paths)
result = {
    'samples': [], 'concurrency': [], 'repoCount': COUNT,
    'clients': args.clients, 'rounds': args.samples,
    'budgetMs': 200, 'serverStopped': False,
}
with tempfile.TemporaryDirectory(prefix='lab-code-search-list-') as folder:
    base = Path(folder).resolve()
    root = base / 'vault'
    framework = base / 'framework'
    (framework / 'core/cli/src/lab').mkdir(parents=True)
    (framework / 'Makefile').touch()
    os.environ.update({
        'LAB_HOME': str(base / 'config'), 'LAB_VAULT': str(root), 'LAB_ROOT': str(root),
        'LAB_FRAMEWORK_ROOT': str(framework), 'LAB_ASSISTANT_HOME': str(base / 'assistant'),
        'LAB_ENV_FILE': str(base / 'no.env'), 'LAB_TMUX_PREFIX': base.name + '-',
        'LAB_WATCHER_OBSERVER': 'polling',
        'PATH': str(Path(sys.executable).parent) + ':' + os.environ['PATH'],
    })
    for key in ('LAB_WORKSPACE', 'LAB_SERVER_SUPERVISOR', 'LAB_DOCUMENT_TERMINALS_SUPERVISOR'):
        os.environ.pop(key, None)
    subprocess.run([
        sys.executable, '-m', 'lab', 'init', str(root), '--name', 'Code search fixture',
        '--no-example', '--no-git',
    ], check=True, stdout=subprocess.DEVNULL)
    repos = root / 'repositories'
    repos.mkdir(exist_ok=True)
    expected = []

    def git(path, *args):
        return subprocess.check_output([
            'git', '-C', str(path), '-c', 'core.hooksPath=/dev/null',
            '-c', 'commit.gpgsign=false', '-c', 'core.fsmonitor=false',
            '-c', 'user.name=Lab fixture', '-c', 'user.email=lab-latency@example.invalid', *args,
        ], text=True, stderr=subprocess.DEVNULL).strip()

    for i in range(COUNT):
        name = ('Alpha' if i % 2 == 0 else 'beta') + f'-{i:02d}'
        repo = repos / name
        repo.mkdir()
        git(repo, 'init', '--quiet', '-b', f'fixture-{i}')
        if i != 1:
            subject = f'Fixture {i} café\tcontinued'
            git(repo, 'commit', '--quiet', '--allow-empty', '-m', subject)
            last = {
                'sha': git(repo, 'rev-parse', '--short', 'HEAD'), 'who': 'Lab fixture',
                'email': 'lab-latency@example.invalid',
                'when_iso': git(repo, 'log', '-1', '--format=%aI'), 'subj': subject,
            }
            if i == 2:
                git(repo, 'checkout', '--quiet', '--detach')
        else:
            last = {}
        expected.append({'name': name, 'branch': 'HEAD' if i in (1, 2) else f'fixture-{i}', 'last': last})
    (repos / 'notes').mkdir()
    (repos / '.hidden').mkdir()
    git(repos / '.hidden', 'init', '--quiet')
    expected.sort(key=lambda row: row['name'].lower())
    import httpx
    import uvicorn
    from core import auth
    from core.main import create_app
    from server_timings import ServerTimings
    cookie = auth.issue_session(auth.get_user('admin'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    os.environ['LAB_PORT'] = str(sock.getsockname()[1])
    app = create_app()
    timings = ServerTimings(app, correlate_requests=True)
    timings.instrument_handler('/api/code-search/repos')
    server = uvicorn.Server(uvicorn.Config(
        timings, access_log=False, log_level='warning', timeout_graceful_shutdown=5,
        ws_per_message_deflate=False,
    ))

    def run():
        with contextlib.redirect_stdout(sys.stderr):
            server.run(sockets=[sock])

    thread = threading.Thread(target=run)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Fixture server failed')
            time.sleep(0.01)
        with contextlib.ExitStack() as clients_scope:
            clients = [clients_scope.enter_context(httpx.Client(
                base_url=url, timeout=30, cookies={auth.SESSION_COOKIE: cookie},
            )) for _ in range(args.clients)]
            workers = clients_scope.enter_context(ThreadPoolExecutor(max_workers=args.clients))
            barrier = threading.Barrier(args.clients)

            def read_catalog(client_index, sample):
                barrier.wait(timeout=10)
                started_epoch = time.time() * 1000
                started = time.perf_counter()
                try:
                    response = clients[client_index].get('/api/code-search/repos')
                except Exception as exc:
                    return {
                        'sample': sample + 1, 'client': client_index + 1,
                        'startEpoch': started_epoch, 'startMonotonicMs': started * 1000,
                        'ms': (time.perf_counter() - started) * 1000, 'error': repr(exc),
                    }, None
                return {
                    'sample': sample + 1, 'client': client_index + 1,
                    'startEpoch': started_epoch, 'startMonotonicMs': started * 1000,
                    'ms': (time.perf_counter() - started) * 1000,
                    'status': response.status_code,
                }, response

            for sample in range(args.samples):
                if args.clients == 1:
                    completed = [read_catalog(0, sample)]
                else:
                    futures = [workers.submit(read_catalog, index, sample) for index in range(args.clients)]
                    completed = [future.result(timeout=35) for future in futures]
                result['samples'].extend(measurement for measurement, _ in completed)
                if args.clients > 1:
                    starts = [measurement['startMonotonicMs'] for measurement, _ in completed]
                    overlap = min(measurement['startMonotonicMs'] + measurement['ms']
                                  for measurement, _ in completed) - max(starts)
                    result['concurrency'].append({
                        'sample': sample + 1, 'startSkewMs': max(starts) - min(starts),
                        'overlapMs': overlap,
                    })
                    assert overlap > 0, 'HTTP requests did not overlap'
                for measurement, response in completed:
                    if response is None:
                        raise RuntimeError(measurement['error'])
                    response.raise_for_status()
                    measurement['rowsVerified'] = verify_rows(response.json(), expected)
                time.sleep(0.025)
            # Keep all rows fresh: mutate one repo and check every returned row.
            changed = repos / expected[0]['name']
            git(changed, 'checkout', '--quiet', '-b', 'fresh-fixture')
            git(changed, 'commit', '--quiet', '--allow-empty', '-m', 'Fresh fixture result')
            expected[0]['branch'] = 'fresh-fixture'
            expected[0]['last'].update({
                'sha': git(changed, 'rev-parse', '--short', 'HEAD'),
                'when_iso': git(changed, 'log', '-1', '--format=%aI'),
                'subj': 'Fresh fixture result',
            })
            started = time.perf_counter()
            response = clients[0].get('/api/code-search/repos')
            ms = (time.perf_counter() - started) * 1000
            result['freshRead'] = {'ms': ms, 'status': response.status_code}
            response.raise_for_status()
            result['freshRead']['rowsVerified'] = verify_rows(response.json(), expected)
            result['freshRead']['verified'] = True
    except Exception as exc:
        result['error'] = repr(exc)
        raise
    finally:
        server.should_exit = True
        thread.join(15)
        result['serverStopped'] = not thread.is_alive()
        if thread.is_alive():
            raise RuntimeError('Fixture server still running')
        Path(str(PREFIX) + '-server.json').write_text(json.dumps({
            **timings.report(), 'serverStopped': not thread.is_alive(),
        }, indent=2) + '\n')
        Path(str(PREFIX) + '-http.json').write_text(json.dumps(result, indent=2) + '\n')
result['fixtureRemoved'] = not base.exists()
Path(str(PREFIX) + '-http.json').write_text(json.dumps(result, indent=2) + '\n')
print(json.dumps(result))
missed = any(row['ms'] >= 200 for row in result['samples']) or result['freshRead']['ms'] >= 200
raise SystemExit(int(missed))
