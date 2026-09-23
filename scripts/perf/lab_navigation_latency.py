#!/usr/bin/env python3
"""Measure native Lab actions using an isolated, CLI-created Lab vault.

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
parser.add_argument('--pending-notebooks', type=int, default=0,
                    help='Mark this many extra notebooks per workspace pending (tracker only; no cell execution)')
parser.add_argument('--git-changes', type=int, default=0, help='Commit fixture workspaces, then modify this many extra files in each (no user repositories)')
parser.add_argument('--app-revision', help='Compare lab-app.js from a local git revision')
parser.add_argument('--css-revision', help='Compare lab-shell.css from a local git revision')
parser.add_argument('--markdown-revision', help='Compare markdown-content.js from a local git revision')
parser.add_argument('--navigation-refresh-delay', type=int, help='Controlled overlap experiment: trigger a background refresh 1–1000 ms after each explicit workspace navigation (normal polling retained)')
parser.add_argument('--typing', action='store_true', help='Measure real CDP input on an owned echo terminal, quiet and with sidebar refreshes')
parser.add_argument('--typing-updates', action='store_true', help='Also change fixture documents during the loaded typing phase')
parser.add_argument('--typing-output', action='store_true', help='Type during a scrolling-output TUI workload in both phases (requires --typing and --server-timings)')
parser.add_argument('--typing-detaches', action='store_true', help='Also attach/detach another owned terminal during loaded typing')
parser.add_argument('--resize', action='store_true', help='Also measure native sidebar drags after navigation (not with --typing)')
parser.add_argument('--create', action='store_true', help='Measure native workspace creation through the + picker, using disposable fixture workspaces')
parser.add_argument('--settings', action='store_true', help='Measure settings open, scoped model/sidebar saves and close with native clicks')
parser.add_argument('--pins', action='store_true', help='Measure native Pin and Unpin clicks through persisted metadata and sidebar redraw')
parser.add_argument('--terminal-tabs', action='store_true', help='Measure native terminal tab clicks across retained panes and cache eviction')
parser.add_argument('--terminal-create', action='store_true', help='Measure native New/Terminal clicks through first rendered output of an owned configured echo shell')
parser.add_argument('--quick-files', action='store_true', help='Measure Command+K, filtering, selection, file opening and Escape with native keys')
parser.add_argument('--document-edit', action='store_true', help='Measure document editor open, save, cancel and close in alternating fixture workspaces')
parser.add_argument('--document-typing', action='store_true', help='Also measure native editor keys, Enter and Tab before Save/Cancel (requires --document-edit; IME setup remains separate)')
parser.add_argument('--document-history', action='store_true', help='Also verify browser Back/Forward, exact saved content and unchanged history entries (requires --document-edit)')
parser.add_argument('--assistant', action='store_true', help='Measure Assistant entry, All and Starred views through full native rendering')
parser.add_argument('--assistant-notes', type=int, default=100, help='Notes in the owned Assistant fixture (at least 2)')
parser.add_argument('--assistant-refresh-delay', type=int, help='Controlled overlap: invoke an Assistant background refresh 1–1000 ms after each entry; normal polling remains enabled')
parser.add_argument('--notebook-view', action='store_true', help='Measure notebook opening, code visibility and output folding with native clicks (does not execute cells)')
parser.add_argument('--notebook-cells', type=int, default=200, help='Cells per notebook-view fixture (default: 200)')
parser.add_argument('--notebook-typing', action='store_true', help='Measure native notebook keys, visible highlighting and draft restoration (requires --notebook-view; does not execute cells)')
parser.add_argument('--notebook-code-lines', type=int, default=0, help='Extra Python source lines in the first code cell of each notebook (0–2000; requires --notebook-view)')
parser.add_argument('--document-sections', type=int, default=30, help='Markdown sections per fixture document (default: 30)')
parser.add_argument('--document-edit-input', choices=['replace', 'append'], default='replace', help='Replace the whole editor value or append only each revision (both use CDP insertText; default: replace)')
parser.add_argument('--server-timings', type=Path, help='Write isolated ASGI and terminal-handler timings to a JSON sidecar')
parser.add_argument('--trace-sessions', action='store_true', help='Also time terminal discovery/metadata functions (requires --server-timings)')
parser.add_argument('--trace-files', action='store_true', help='Also time file-list handlers, guarded scans, pending lookups and response serialization (requires --server-timings)')
parser.add_argument('--trace-terminal', action='store_true', help='Time owned WebSocket/PTY operations without payloads, plus producer CPU for output typing (requires --typing, --terminal-tabs or --terminal-create, and --server-timings)')
parser.add_argument('--trace-gc', action='store_true', help='Observe server garbage-collection pauses without changing runtime policy (requires --server-timings)')
parser.add_argument('--trace-watchers', action='store_true', help='Time complete watcher snapshots/diffs, watch refreshes and index rebuilds without changing their policy (requires --server-timings)')
parser.add_argument('--trace-file-scans', action='store_true', help='Time file handlers, guarded workers and serialization without per-notebook tracing (requires --server-timings)')
parser.add_argument('--websocket-deflate', action='store_true', help='Diagnostic comparison only: enable WebSocket compression (production disables it)')
args = parser.parse_args()
if args.assistant and any((args.typing,args.resize,args.create,args.settings,args.pins,args.terminal_tabs,args.terminal_create,args.quick_files,args.document_edit,args.notebook_view,args.pending_notebooks,args.navigation_refresh_delay)):
    parser.error('--assistant measures a separate workflow and cannot be combined with other workflows')
if args.assistant_notes < 2:
    parser.error('--assistant-notes must be at least 2')
if args.assistant_refresh_delay is not None and (not args.assistant or not 1 <= args.assistant_refresh_delay <= 1000):
    parser.error('--assistant-refresh-delay requires --assistant and a delay of 1–1000 ms')
if args.samples < 2:
    parser.error('--samples must be at least 2')
if args.terminal_create and any((args.typing,args.resize,args.create,args.settings,args.pins,args.terminal_tabs,args.quick_files,args.document_edit,args.notebook_view)):
    parser.error('--terminal-create measures a separate workflow and cannot be combined with other workflows')
if args.typing and args.samples < 20:
    parser.error('--typing requires at least 20 samples per phase')
if args.typing_updates and not args.typing:
    parser.error('--typing-updates requires --typing')
if args.typing_output and (not args.typing or not args.server_timings):
    parser.error('--typing-output requires --typing and --server-timings')
if args.typing_detaches and not args.typing:
    parser.error('--typing-detaches requires --typing')
if args.resize and args.typing:
    parser.error('--resize measures navigation gestures and cannot be combined with --typing')
if args.create and (args.typing or args.resize):
    parser.error('--create measures a separate workflow and cannot be combined with --typing or --resize')
if args.settings and (args.typing or args.resize or args.create):
    parser.error('--settings measures a separate workflow and cannot be combined with --typing, --resize or --create')
if args.pins and (args.typing or args.resize or args.create or args.settings):
    parser.error('--pins measures a separate workflow and cannot be combined with --typing, --resize, --create or --settings')
if args.terminal_tabs and (args.typing or args.resize or args.create or args.settings or args.pins):
    parser.error('--terminal-tabs measures a separate workflow and cannot be combined with --typing, --resize, --create, --settings or --pins')
if args.quick_files and (args.typing or args.resize or args.create or args.settings or args.pins or args.terminal_tabs):
    parser.error('--quick-files measures a separate workflow and cannot be combined with other workflows')
if args.document_edit and (args.typing or args.resize or args.create or args.settings or args.pins or args.terminal_tabs or args.quick_files):
    parser.error('--document-edit measures a separate workflow and cannot be combined with other workflows')
if args.document_sections < 1:
    parser.error('--document-sections must be positive')
if args.document_edit_input != 'replace' and not args.document_edit:
    parser.error('--document-edit-input requires --document-edit')
if args.document_typing and not args.document_edit:
    parser.error('--document-typing requires --document-edit')
if args.document_history and not args.document_edit:
    parser.error('--document-history requires --document-edit')
if args.notebook_view and any((args.typing,args.resize,args.create,args.settings,args.pins,args.terminal_tabs,args.quick_files,args.document_edit)):
    parser.error('--notebook-view measures a separate workflow and cannot be combined with other workflows')
if args.notebook_cells < 2 or args.notebook_cells > 2000:
    parser.error('--notebook-cells must be between 2 and 2000')
if args.notebook_typing and not args.notebook_view:
    parser.error('--notebook-typing requires --notebook-view')
if not 0 <= args.notebook_code_lines <= 2000:
    parser.error('--notebook-code-lines must be between 0 and 2000')
if args.notebook_code_lines and not args.notebook_view:
    parser.error('--notebook-code-lines requires --notebook-view')
if args.navigation_refresh_delay is not None:
    if not 1 <= args.navigation_refresh_delay <= 1000:
        parser.error('--navigation-refresh-delay must be between 1 and 1000 ms')
    if any((args.typing,args.resize,args.create,args.settings,args.pins,args.terminal_tabs,args.terminal_create,args.quick_files,args.document_edit,args.notebook_view)):
        parser.error('--navigation-refresh-delay requires the standalone navigation workflow')
if args.trace_sessions and not args.server_timings:
    parser.error('--trace-sessions requires --server-timings')
if args.trace_terminal and (not (args.typing or args.terminal_tabs or args.terminal_create) or not args.server_timings):
    parser.error('--trace-terminal requires --typing, --terminal-tabs or --terminal-create, and --server-timings')
if args.trace_files and not args.server_timings:
    parser.error('--trace-files requires --server-timings')
if args.trace_gc and not args.server_timings:
    parser.error('--trace-gc requires --server-timings')
if args.trace_watchers and not args.server_timings:
    parser.error('--trace-watchers requires --server-timings')
if args.trace_file_scans and not args.server_timings:
    parser.error('--trace-file-scans requires --server-timings')
if args.extra_files < 0:
    parser.error('--extra-files must be nonnegative')
if args.git_changes < 0 or args.git_changes > args.extra_files:
    parser.error('--git-changes must be between zero and --extra-files')
extra_file_types = [extension.strip().lower() for extension in args.extra_file_types.split(',')]
if not all(re.fullmatch(r'[a-z0-9]{1,16}', extension) for extension in extra_file_types):
    parser.error('--extra-file-types must contain simple filename extensions')
notebook_count = sum(extra_file_types[number % len(extra_file_types)] == 'ipynb' for number in range(args.extra_files))
if not 0 <= args.pending_notebooks <= notebook_count:
    parser.error('--pending-notebooks must fit the extra ipynb files in each workspace')
if args.pending_notebooks and any((args.typing, args.resize, args.create, args.settings,
        args.pins, args.terminal_tabs, args.terminal_create, args.quick_files,
        args.document_edit, args.notebook_view)):
    parser.error('--pending-notebooks requires the standalone navigation workflow')
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
    assistant_fixture = None
    if args.assistant:
        from assistant_fixture import seed_assistant
        assistant_fixture = seed_assistant(base / 'assistant', args.assistant_notes)
        (base / 'assistant-expected.json').write_text(json.dumps(assistant_fixture))
    pending_notebooks = []
    for name in ('alpha', 'beta'):
        lab('workspace', 'new', name, '--name', name.title(), '--desc', name + ' fixture')
        for number in (1, 2):
            (root / 'workspaces' / name / 'docs' / f'review-{number}.md').write_text(
                f'# {name.title()} review {number}\n\n' + '\n\n'.join(
                    f'## Section {i}\n\nFixture paragraph with **formatting** and `code`.'
                    for i in range(args.document_sections)))
        if args.notebook_view:
            notebook = root / 'workspaces' / name / 'notebooks' / 'review.ipynb'
            notebook.parent.mkdir(exist_ok=True)
            cells = []
            for number in range(args.notebook_cells):
                cell = {'id': f'{name}-cell-{number}', 'metadata': {}}
                if number % 2 == 0:
                    cell.update(cell_type='markdown', source=f'## {name.title()} cell {number}\n\nFixture **formatted** paragraph {number}.')
                else:
                    output = ''.join(f'{name} output {number} line {line}\n' for line in range(20))
                    cell.update(cell_type='code', source=f'print({output!r}, end="")', execution_count=number,
                                outputs=[{'output_type': 'stream', 'name': 'stdout', 'text': output}])
                    if number == 1:
                        cell['source'] += ''.join(
                            f'\nvalue_{line} = sum(range({line + 1}))  # fixture calculation'
                            for line in range(args.notebook_code_lines))
                cells.append(cell)
            notebook.write_text(json.dumps({'nbformat': 4, 'nbformat_minor': 5, 'metadata': {
                'kernelspec': {'name': 'python3', 'display_name': 'Python 3', 'language': 'python'}}, 'cells': cells}))
        pending_count = 0
        for number in range(args.extra_files):
            folder = root / 'workspaces' / name / 'notes'
            if args.extra_file_layout == 'folders':
                folder /= f'batch-{number // 100:03}'
            folder.mkdir(exist_ok=True)
            extension = extra_file_types[number % len(extra_file_types)]
            extra_file = folder / f'entry-{number:05}.{extension}'
            extra_file.write_text(f'# Fixture note {number}\n\nSmall document.\n')
            if extension == 'ipynb' and pending_count < args.pending_notebooks:
                pending_notebooks.append(extra_file)
                pending_count += 1
        if args.git_changes:
            workspace = root / 'workspaces' / name
            def git(*arguments):
                subprocess.run(['git', '-C', str(workspace), '-c', 'core.hooksPath=/dev/null',
                                '-c', 'commit.gpgsign=false', '-c', 'core.fsmonitor=false',
                                '-c', 'user.name=Lab latency fixture',
                                '-c', 'user.email=lab-latency@example.invalid', *arguments],
                               check=True, capture_output=True)
            git('init', '--quiet')
            git('add', '--force', '--all')
            git('commit', '--quiet', '-m', 'Owned latency fixture')
            for number in range(args.git_changes):
                folder = workspace / 'notes'
                if args.extra_file_layout == 'folders':
                    folder /= f'batch-{number // 100:03}'
                extension = extra_file_types[number % len(extra_file_types)]
                (folder / f'entry-{number:05}.{extension}').write_text(f'# Changed fixture note {number}\n\nUpdated document.\n')
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
    if args.css_revision:
        from starlette.responses import Response
        from starlette.routing import Route
        css_source = subprocess.check_output(['git', 'show',
            args.css_revision + ':core/src/core/static/css/lab-shell.css'], cwd=checkout)
        async def baseline_css(request):
            return Response(css_source, media_type='text/css')
        app.router.routes.insert(0, Route('/static/css/lab-shell.css', baseline_css))
    if args.markdown_revision:
        from starlette.responses import Response
        from starlette.routing import Route
        markdown_source = subprocess.check_output(['git', 'show',
            args.markdown_revision + ':core/src/core/static/js/lib/markdown-content.js'], cwd=checkout)
        async def baseline_markdown(request):
            return Response(markdown_source, media_type='application/javascript')
        app.router.routes.insert(0, Route('/static/js/lib/markdown-content.js', baseline_markdown))
    timings = None
    instrumentation = contextlib.ExitStack()
    if args.server_timings:
        from server_timings import ServerTimings
        timings = ServerTimings(app, correlate_requests=True, trace_terminal=args.trace_terminal)
        timings.instrument_sessions()
        if args.assistant:
            timings.instrument_handler('/api/assistant')
        if args.trace_gc:
            instrumentation.enter_context(timings.trace_garbage_collection())
        if args.trace_watchers:
            instrumentation.enter_context(timings.trace_watchers())
        if args.create:
            from core.routes import mutation
            timings.instrument_handler('/api/workspaces')
            timings.trace_function(mutation, '_run_lab')
        if args.trace_terminal:
            from core.routes import term
            instrumentation.enter_context(timings.trace_terminal_io(term))
            if args.terminal_tabs or args.terminal_create:
                timings.trace_function(term, '_tmux_find_session_socket')
                timings.trace_function(term, '_term_ws_context')
                timings.trace_function(term, '_tmux_has_session')
                timings.trace_function(term, '_tmux_available')
                timings.trace_function(term.tmux_sockets, 'socket_names')
        if args.trace_files or args.trace_file_scans:
            from core import fsguard
            from fastapi import routing
            timings.instrument_handler('/api/workspace-files')
            timings.instrument_handler('/api/workspace-mtime')
            timings.trace_function(fsguard, 'guarded')
            timings.trace_function(fsguard, '_run_tracked')
            if args.trace_files:
                from core.routes import nb_exec
                timings.trace_function(nb_exec, 'is_path_pending')
            timings.trace_function(routing, 'serialize_response')
        if args.trace_sessions:
            from core.routes import term
            for name in ('_tmux_list', '_load_meta', '_known_vaults', '_sync_meta',
                         '_get_workspace_sessions', '_enrich_session_details',
                         '_workspace_session_by_name', '_home_session_rows',
                         '_sessions_for_root'):
                timings.trace_function(term, name)
            if args.terminal_create:
                for name in ('_configure_tmux_wheel_scrolling', '_save_meta', '_upsert_workspace_session'):
                    timings.trace_function(term, name)
                if not args.trace_terminal:
                    timings.trace_function(term, '_tmux_find_session_socket')
    server = uvicorn.Server(uvicorn.Config(timings or app, access_log=False, log_level='warning',
        timeout_graceful_shutdown=5, ws_per_message_deflate=args.websocket_deflate))
    def run_server():
        # Lifespan prints fixture URLs; leave stdout as machine-readable results.
        with contextlib.redirect_stdout(sys.stderr):
            server.run(sockets=[sock])
    thread = threading.Thread(target=run_server)
    thread.start()
    creation_report = None
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
        create_scopes = [f'latency-workspace-{i + 1:03}' for i in range(args.samples)] if args.create else []
        for scope in ('alpha', 'beta', '__self__', '__assistant__', *create_scopes):
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
        terminal_context = contextlib.nullcontext([])
        if args.terminal_tabs or args.typing_detaches:
            from terminal_tab_fixture import terminal_tab_fixture
            terminal_context = terminal_tab_fixture(url, cookie, root / 'workspaces/alpha', count=6 if args.terminal_tabs else 1)
        creation_context = contextlib.nullcontext(None)
        if args.terminal_create:
            from terminal_creation_fixture import terminal_creation_fixture
            creation_context = terminal_creation_fixture(url, cookie, root / 'workspaces/alpha')
        with terminal_context as terminal_tabs, creation_context as creation_report, contextlib.ExitStack() as pending_context:
            from core.routes import nb_exec
            for notebook in pending_notebooks:
                nb_exec._mark_running(notebook)
                pending_context.callback(nb_exec._mark_done, notebook)
            result = subprocess.run(
                command,
                env={**os.environ, 'LAB_PROBE_COOKIE': cookie,
                     'LAB_PERF_TERMINAL_TABS': json.dumps(terminal_tabs),
                     'LAB_PERF_TERMINAL_CREATE': json.dumps(creation_report),
                     'LAB_PERF_TYPING_DETACH': json.dumps(terminal_tabs[0] if args.typing_detaches else None),
                     'LAB_PERF_EXTRA_FILES': str(args.extra_files),
                     'LAB_PERF_PENDING_NOTEBOOKS': json.dumps([
                         str(notebook.relative_to(root / 'workspaces')) for notebook in pending_notebooks]),
                     'LAB_PERF_NAVIGATION_REFRESH_DELAY': str(args.navigation_refresh_delay or ''),
                     'LAB_PERF_EXTRA_FILE_TYPES': ','.join(extra_file_types),
                     'LAB_PERF_GIT_CHANGES': str(args.git_changes),
                     'LAB_PERF_TYPING_UPDATES': str(int(args.typing_updates)),
                     'LAB_PERF_OUTPUT_REPORT': str(base / 'output-load.json') if args.typing_output else '',
                     'LAB_PERF_WS_DEFLATE': str(int(args.websocket_deflate)),
                     'LAB_PERF_ECHO_TRACE': str(base / 'echo-timings.json') if args.trace_terminal and args.typing and not args.typing_output else '',
                     'LAB_PERF_OUTPUT_INPUT_TRACE': str(int(args.trace_terminal and args.typing_output)),
                     'LAB_PERF_SIDEBAR_RESIZE': str(int(args.resize)),
                     'LAB_PERF_CREATE_WORKSPACES': str(int(args.create)),
                     'LAB_PERF_SETTINGS': str(int(args.settings)),
                     'LAB_PERF_PINS': str(int(args.pins)),
                     'LAB_PERF_QUICK_FILES': str(int(args.quick_files)),
                     'LAB_PERF_DOCUMENT_EDIT': str(int(args.document_edit)),
                     'LAB_PERF_DOCUMENT_TYPING': str(int(args.document_typing)),
                     'LAB_PERF_DOCUMENT_HISTORY': str(int(args.document_history)),
                     'LAB_PERF_ASSISTANT_FILE': str(base / 'assistant-expected.json') if assistant_fixture else '',
                     'LAB_PERF_ASSISTANT_REFRESH_DELAY': str(args.assistant_refresh_delay or ''),
                     'LAB_PERF_NOTEBOOK_VIEW': str(int(args.notebook_view)),
                     'LAB_PERF_NOTEBOOK_TYPING': str(int(args.notebook_typing)),
                     'LAB_PERF_NOTEBOOK_CODE_LINES': str(args.notebook_code_lines),
                     'LAB_PERF_DOCUMENT_SECTIONS': str(args.document_sections),
                     'LAB_PERF_DOCUMENT_EDIT_INPUT': args.document_edit_input,
                     'LAB_PERF_EXTRA_FILE_LAYOUT': args.extra_file_layout},
                timeout=max(120, args.samples * 26))
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
        instrumentation.close()
        pending_cleaned = True
        if pending_notebooks:
            from core.routes import nb_exec
            with nb_exec._pending_guard:
                pending_cleaned = all(str(path.resolve()) not in nb_exec._pending_paths
                                      and str(path.resolve()) not in nb_exec._pending_leases
                                      for path in pending_notebooks)
        if timings:
            args.server_timings.parent.mkdir(parents=True, exist_ok=True)
            report = {**timings.report(), 'serverStopped': not thread.is_alive(),
                      'websocketDeflate': args.websocket_deflate}
            if pending_notebooks:
                report['pendingNotebooks'] = {'perWorkspace': args.pending_notebooks,
                    'executesCells': False, 'cleaned': pending_cleaned}
            if args.trace_terminal and (base / 'echo-timings.json').exists():
                report['echo'] = json.loads((base / 'echo-timings.json').read_text())
            if args.typing_output:
                report['outputLoad'] = json.loads((base / 'output-load.json').read_text()) if (base / 'output-load.json').exists() else None
            if args.terminal_create:
                report['terminalCreation'] = creation_report
            args.server_timings.write_text(json.dumps(report, indent=2) + '\n')
        if not pending_cleaned:
            raise RuntimeError('Owned pending notebook markers survived cleanup')
    if thread.is_alive():
        raise RuntimeError('Fixture server did not stop')
    raise SystemExit(result.returncode)
