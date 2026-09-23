#!/usr/bin/env python3
"""Time complete authenticated Assistant HTTP reads in a disposable vault.

Keep every request, including first use, and verify all notes and documents.
The fixture uses the normal watcher/lifespan and modern Assistant migrations.
No request is sent before the first sample. A final Markdown edit must appear
in the next response. This is endpoint timing, not browser/display latency.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import threading
import time


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True, help='HTTP/server JSON prefix')
parser.add_argument('--notes', type=int, default=100)
parser.add_argument('--samples', type=int, default=20)
parser.add_argument('--trace-snapshots', action='store_true', help='Diagnostic whole-snapshot timing; repeat without tracing')
parser.add_argument('--trace-projections', action='store_true', help='Diagnostic whole-snapshot and progress-map timing; nested phases are not additive')
args = parser.parse_args()
if args.notes < 2 or args.samples < 1:
    parser.error('Use at least two notes and one sample')
prefix = args.output
prefix.parent.mkdir(parents=True, exist_ok=True)
if any(Path(str(prefix) + suffix).exists() for suffix in ('-http.json', '-server.json')):
    parser.error('Refusing to replace existing reports')
checkout = Path(__file__).resolve().parents[2]
source_paths = [str(checkout / 'core/src'), str(checkout / 'core/cli/src')]
sys.path[:0] = source_paths
os.environ['PYTHONPATH'] = os.pathsep.join(source_paths)
report = {'samples': [], 'notes': args.notes, 'budgetMs': 200, 'serverStopped': False}
with tempfile.TemporaryDirectory(prefix='lab-assistant-latency-') as folder:
    base = Path(folder).resolve()
    root, framework, assistant_root = base / 'vault', base / 'framework', base / 'assistant'
    (framework / 'core/cli/src/lab').mkdir(parents=True)
    (framework / 'Makefile').touch()
    os.environ.update({
        'LAB_HOME': str(base / 'config'), 'LAB_VAULT': str(root), 'LAB_ROOT': str(root),
        'LAB_FRAMEWORK_ROOT': str(framework), 'LAB_ASSISTANT_HOME': str(assistant_root),
        'LAB_ENV_FILE': str(base / 'no.env'), 'LAB_TMUX_PREFIX': base.name + '-',
        'LAB_WATCHER_OBSERVER': 'polling',
        'PATH': str(Path(sys.executable).parent) + ':' + os.environ['PATH'],
    })
    for key in ('LAB_WORKSPACE', 'LAB_SERVER_SUPERVISOR', 'LAB_DOCUMENT_TERMINALS_SUPERVISOR'):
        os.environ.pop(key, None)
    subprocess.run([sys.executable, '-m', 'lab', 'init', str(root), '--name', 'Assistant fixture',
                    '--no-example', '--no-git'], check=True, stdout=subprocess.DEVNULL)
    from assistant_fixture import seed_assistant, verify_assistant
    expected = seed_assistant(assistant_root, args.notes)
    import httpx
    import uvicorn
    from core import auth
    from core.main import create_app
    from lab import assistant_records as records, assistant_documents as documents
    from server_timings import ServerTimings
    cookie = auth.issue_session(auth.get_user('admin'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    os.environ['LAB_PORT'] = str(sock.getsockname()[1])
    timings = ServerTimings(create_app(), correlate_requests=True)
    timings.instrument_handler('/api/assistant')
    if args.trace_snapshots or args.trace_projections:
        timings.trace_function(documents, 'snapshot')
    if args.trace_projections:
        timings.trace_function(records, 'progress_map')
    server = uvicorn.Server(uvicorn.Config(timings, access_log=False, log_level='warning',
                                         timeout_graceful_shutdown=5, ws_per_message_deflate=False))

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
            time.sleep(.01)
        with httpx.Client(base_url=url, timeout=60, cookies={auth.SESSION_COOKIE: cookie}) as client:
            for number in range(args.samples + 1):
                fresh = number == args.samples
                if fresh:
                    source = assistant_root / expected['notes'][0]['path']
                    metadata, body = records.read_document(source)
                    metadata['title'] = 'Fresh external edit café'
                    # A real Markdown write, without touching the snapshot cache.
                    records.write_document(source, metadata, body + 'Fresh body.\n')
                    expected['notes'][0]['title'] = expected['documents'][0]['title'] = metadata['title']
                    expected['notes'][0]['body'] += 'Fresh body.\n'
                    expected['notes'][0]['search_text'] = expected['notes'][0]['search_text'].replace('Fixture note 0000 café', metadata['title'], 1)
                measurement = {'sample': number + 1, 'startEpoch': time.time() * 1000, 'fresh': fresh}
                report['samples'].append(measurement)
                started = time.perf_counter()
                try:
                    response = client.get('/api/assistant')
                finally:
                    measurement['ms'] = (time.perf_counter() - started) * 1000
                measurement['status'] = response.status_code
                response.raise_for_status()
                actual = response.json()
                measurement['rowsVerified'] = verify_assistant(actual, expected)
                measurement['responseSha256'] = hashlib.sha256(response.content).hexdigest()
                if number and not fresh:
                    assert measurement['responseSha256'] == report['samples'][0]['responseSha256']
                if fresh:
                    assert 'Fresh body.' in actual['documents'][0]['search_text']
                measurement['verified'] = True
    except Exception as exc:
        report['error'] = repr(exc)
        raise
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
        report['serverStopped'] = not thread.is_alive()
        Path(str(prefix) + '-server.json').write_text(json.dumps(timings.report(), indent=2) + '\n')
        Path(str(prefix) + '-http.json').write_text(json.dumps(report, indent=2) + '\n')
        if thread.is_alive():
            raise RuntimeError('Fixture server still running')
report['fixtureRemoved'] = not base.exists()
Path(str(prefix) + '-http.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report))
raise SystemExit(int(any(row['ms'] >= 200 for row in report['samples'])))
