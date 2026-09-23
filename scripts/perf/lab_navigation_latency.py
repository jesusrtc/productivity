#!/usr/bin/env python3
"""Measure workspace/document clicks using an isolated, CLI-created Lab vault.

Uses the normal server lifespan and UI polling, a fresh Chrome profile, and
fixture preferences that disable automatic agent creation. Never starts or
stops the user's server or changes their registry/workspace state. Chrome and
Node with built-in WebSocket support are required. Every sample is retained;
there is no warm-up exclusion. The first click runs as soon as tabs appear.
"""
import argparse
import contextlib
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time
from pathlib import Path
import urllib.request
from urllib.parse import quote

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--samples', type=int, default=20, help='Samples per action (at least 2)')
parser.add_argument('--extra-files', type=int, default=0, help='Additional files in each workspace')
parser.add_argument('--extra-file-types', default='md', help='Comma-separated extensions for extra files, e.g. md,py,json,sql')
parser.add_argument('--extra-file-layout', choices=['folders', 'flat'], default='folders')
parser.add_argument('--app-revision', help='Compare lab-app.js from a local git revision')
parser.add_argument('--typing', action='store_true', help='Measure real CDP input on an owned echo terminal, quiet and with sidebar refreshes')
parser.add_argument('--typing-updates', action='store_true', help='Also change fixture documents during the loaded typing phase')
args = parser.parse_args()
if args.samples < 2:
    parser.error('--samples must be at least 2')
if args.typing and args.samples < 20:
    parser.error('--typing requires at least 20 samples per phase')
if args.typing_updates and not args.typing:
    parser.error('--typing-updates requires --typing')
if args.extra_files < 0:
    parser.error('--extra-files must be nonnegative')
extra_file_types = [extension.strip().lower() for extension in args.extra_file_types.split(',')]
if not all(re.fullmatch(r'[a-z0-9]{1,16}', extension) for extension in extra_file_types):
    parser.error('--extra-file-types must contain simple filename extensions')
checkout = Path(__file__).resolve().parents[2]
source_paths = [str(checkout / 'core/src'), str(checkout / 'core/cli/src')]
sys.path[:0] = source_paths
os.environ['PYTHONPATH'] = os.pathsep.join(source_paths + [os.environ.get('PYTHONPATH', '')])
with tempfile.TemporaryDirectory(prefix='lab-navigation-') as folder:
    base = Path(folder).resolve()
    root = base / 'vault'
    framework = base / 'framework'
    (framework / 'core/cli/src/lab').mkdir(parents=True)
    (framework / 'Makefile').touch()
    env = {
        'LAB_HOME': str(base / 'config'), 'LAB_VAULT': str(root),
        'LAB_ROOT': str(root), 'LAB_FRAMEWORK_ROOT': str(framework),
        'LAB_ASSISTANT_HOME': str(base / 'assistant'),
        'LAB_ENV_FILE': str(base / 'no.env'),
        'LAB_TMUX_PREFIX': base.name + '-',
        'LAB_WATCHER_OBSERVER': 'polling',
        'PATH': str(Path(sys.executable).parent) + ':' + os.environ['PATH'],
    }
    os.environ.update(env)
    os.environ.pop('LAB_WORKSPACE', None)
    os.environ.pop('LAB_SERVER_SUPERVISOR', None)
    os.environ.pop('LAB_DOCUMENT_TERMINALS_SUPERVISOR', None)
    def lab(*args):
        subprocess.run([sys.executable, '-m', 'lab', *args], check=True,
                       stdout=subprocess.DEVNULL)
    lab('init', str(root), '--name', 'Navigation fixture', '--no-example', '--no-git')
    for name in ('alpha', 'beta'):
        lab('workspace', 'new', name, '--name', name.title(), '--desc', name + ' fixture')
        for number in (1, 2):
            (root / 'workspaces' / name / 'docs' / f'review-{number}.md').write_text(
                f'# {name.title()} review {number}\n\n' + '\n\n'.join(
                    f'## Section {i}\n\nFixture paragraph with **formatting** and `code`.'
                    for i in range(30)))
        for number in range(args.extra_files):
            folder = root / 'workspaces' / name / 'notes'
            if args.extra_file_layout == 'folders':
                folder /= f'batch-{number // 100:03}'
            folder.mkdir(exist_ok=True)
            extension = extra_file_types[number % len(extra_file_types)]
            (folder / f'entry-{number:05}.{extension}').write_text(f'# Fixture note {number}\n\nSmall document.\n')
    import uvicorn
    from core import auth
    from core.main import create_app
    cookie = auth.issue_session(auth.get_user('admin'))
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    url = f'http://127.0.0.1:{sock.getsockname()[1]}'
    os.environ['LAB_PORT'] = str(sock.getsockname()[1])
    app = create_app()
    if args.app_revision:
        # Swap just the source under test; routes, auth, startup, and background
        # services retain their production behavior and operate on fixture data.
        source = subprocess.check_output(['git', 'show',
            args.app_revision + ':core/src/core/static/js/lab-app.js'], cwd=checkout)
        from starlette.responses import Response
        from starlette.routing import Route
        async def baseline_source(request):
            return Response(source, media_type='application/javascript')
        app.router.routes.insert(0, Route('/static/js/lab-app.js', baseline_source))
    server = uvicorn.Server(uvicorn.Config(app, access_log=False, log_level='warning'))
    def run_server():
        # Lifespan prints fixture URLs; leave stdout as machine-readable results.
        with contextlib.redirect_stdout(sys.stderr):
            server.run(sockets=[sock])
    thread = threading.Thread(target=run_server)
    thread.start()
    try:
        deadline = time.monotonic() + 15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Fixture server failed to start')
            time.sleep(.01)
        for name in ('alpha', 'beta'):
            workspace_path = str(root / 'workspaces' / name)
            read = urllib.request.Request(url + '/api/workspace-info?path=' + quote(workspace_path),
                       headers={'Cookie': 'lab_session=' + cookie})
            with urllib.request.urlopen(read, timeout=10) as response:
                info = json.load(response)
            info['tab_open'] = True
            data = json.dumps({'path': workspace_path, 'data': info}).encode()
            request = urllib.request.Request(url + '/api/workspace-info', data=data, method='PUT',
                       headers={'Cookie': 'lab_session=' + cookie, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200
        for scope in ('alpha', 'beta', '__self__', '__assistant__'):
            data = json.dumps({'workspace_id': scope, 'enabled': False}).encode()
            request = urllib.request.Request(url + '/api/ui/term-autospawn', data=data,
                       headers={'Cookie': 'lab_session=' + cookie, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(request, timeout=10) as response:
                assert response.status == 200
        command = ([sys.executable, str(checkout / 'scripts/perf/lab_terminal_latency.py'),
                    '--browser', '--base-url', url, '--workspace', str(root / 'workspaces/alpha'),
                    '--samples', str(args.samples)] if args.typing else
                   ['node', str(checkout / 'scripts/perf/lab_navigation_latency.mjs'), url,
                    str(root / 'workspaces'), str(args.samples)])
        result = subprocess.run(command,
                                env={**os.environ, 'LAB_PROBE_COOKIE': cookie,
                                     'LAB_PERF_EXTRA_FILES': str(args.extra_files),
                                     'LAB_PERF_EXTRA_FILE_TYPES': ','.join(extra_file_types),
                                     'LAB_PERF_TYPING_UPDATES': str(int(args.typing_updates)),
                                     'LAB_PERF_EXTRA_FILE_LAYOUT': args.extra_file_layout},
                                timeout=max(120, args.samples * 26))
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
    if thread.is_alive():
        raise RuntimeError('Fixture server did not stop')
    raise SystemExit(result.returncode)
