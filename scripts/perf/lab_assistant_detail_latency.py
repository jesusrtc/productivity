#!/usr/bin/env python3
"""Measure complete root/subtab detail reads and fresh edits in an owned vault.

All first-use requests are retained. Normal lifecycle/watchers remain enabled.
This measures authenticated HTTP completion, not native browser/display latency.
"""
import argparse
import contextlib
import hashlib
import json
import os
from pathlib import Path
import re
import socket
import subprocess
import sys
import tempfile
import threading
import time


def task_summary(status, completed, total, blocked):
    return dict(status=status, automatic_status=status, tracked=True, derived=True,
                completed=completed, total=total, pending=total-completed, wip=0, blocked=blocked)


def verify_detail(actual, reference, source, owner_path, metadata, body, tabs):
    """Compare the full detail shape with fixture files and explicit task states."""
    assert set(actual) == {'path', 'metadata', 'body', 'document_tasks', 'workspace',
                          'progress', 'embedded', 'tldr', 'root_path', 'root_kind', 'tree', 'subtasks'}
    is_tab = '#tab=' in reference
    selected, selected_body = tabs[0] if is_tab else (metadata, body)
    selected_metadata = selected | {field:metadata.get(field) for field in ('workspace', 'project')} if is_tab else selected
    root_progress = task_summary('blocked', 1, 2, 1)
    states = [root_progress, task_summary('done', 1, 1, 0), task_summary('blocked', 0, 1, 1)]
    assert actual['path'] == reference and actual['root_path'] == owner_path
    assert actual['root_kind'] == 'note' and actual['embedded'] is is_tab
    assert actual['metadata'] == selected_metadata and actual['body'] == selected_body
    assert actual['workspace'] == {} and actual['subtasks'] == []
    assert actual['tldr'] == (selected.get('tldr') or '')
    assert actual['progress'] == states[1 if is_tab else 0]
    assert [task['status'] for task in metadata['tasks']] == ['blocked', 'done', 'blocked']
    assert actual['document_tasks'] == dict(document_id=metadata['id'], path=owner_path,
        revision=hashlib.sha256(source.read_bytes()).hexdigest(), tasks=metadata['tasks'], summary=root_progress)
    tree = actual['tree']
    nodes = [tree, *tree['children']]
    assert len(nodes) == 3 and all(node['children'] == [] for node in nodes[1:])
    revisions = {}
    for number, (node, (stored, text)) in enumerate(zip(nodes, [(metadata, body), *tabs])):
        identifier = stored['id']
        revisions[identifier] = node['tab_revision']
        assert re.fullmatch('[a-f0-9]{64}', node['tab_revision'])
        row = {**stored, **({field:metadata.get(field) for field in ('project', 'workspace', 'task_format')} if number else {}),
               'path':owner_path + ('#tab=' + identifier if number else ''),
               'document_path':owner_path, 'embedded':bool(number), 'mtime':source.stat().st_mtime}
        expected = {**row, 'kind':'note', 'task_summary':task_summary('blocked', 0, 1, 1) if not number else states[number],
                    'description':stored.get('tldr') or text.strip(), 'track_task':False, 'progress':states[number]}
        assert {key:value for key,value in node.items() if key not in {'children', 'tab_revision'}} == expected
    return revisions


parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--output', type=Path, required=True)
parser.add_argument('--notes', type=int, default=500)
parser.add_argument('--samples', type=int, default=20, help='Reads per root/subtab, plus one fresh read of each')
parser.add_argument('--trace-projections', action='store_true', help='Coarse nested timings; repeat without tracing')
args = parser.parse_args()
if args.notes < 2 or args.samples < 1:
    parser.error('Use at least two notes and one sample')
prefix = args.output
prefix.parent.mkdir(parents=True, exist_ok=True)
if any(Path(str(prefix)+suffix).exists() for suffix in ('-http.json', '-server.json')):
    parser.error('Refusing to replace reports')
checkout = Path(__file__).resolve().parents[2]
source_paths = [str(checkout/'core/src'), str(checkout/'core/cli/src')]
sys.path[:0] = source_paths
os.environ['PYTHONPATH'] = os.pathsep.join(source_paths)
report = dict(samples=[], notes=args.notes, budgetMs=200, serverStopped=False)
with tempfile.TemporaryDirectory(prefix='lab-assistant-detail-') as folder:
    base = Path(folder).resolve()
    vault, framework, root = base/'vault', base/'framework', base/'assistant'
    (framework/'core/cli/src/lab').mkdir(parents=True)
    (framework/'Makefile').touch()
    os.environ.update(LAB_HOME=str(base/'config'), LAB_VAULT=str(vault), LAB_ROOT=str(vault),
        LAB_FRAMEWORK_ROOT=str(framework), LAB_ASSISTANT_HOME=str(root), LAB_ENV_FILE=str(base/'no.env'),
        LAB_TMUX_PREFIX=base.name+'-', LAB_WATCHER_OBSERVER='polling',
        PATH=str(Path(sys.executable).parent)+':'+os.environ['PATH'])
    for key in ('LAB_WORKSPACE', 'LAB_SERVER_SUPERVISOR', 'LAB_DOCUMENT_TERMINALS_SUPERVISOR'):
        os.environ.pop(key, None)
    subprocess.run([sys.executable, '-m', 'lab', 'init', str(vault), '--name', 'Detail fixture',
                    '--no-example', '--no-git'], check=True, stdout=subprocess.DEVNULL)
    from assistant_fixture import seed_assistant
    expected = seed_assistant(root, args.notes)
    from lab import assistant_records as records, assistant_documents as documents, assistant_tasks as tasks
    owner_path = expected['notes'][0]['path']
    source = root/owner_path
    metadata, body, tabs = documents.unpack(source.read_bytes())
    parent = tasks.change(root, owner_path, {'title':'Prepare review', 'priority':'P1', 'tab_id':metadata['id']})['task_id']
    tasks.change(root, owner_path, {'title':'Read details', 'parent_id':parent, 'status':'done', 'tab_id':tabs[0][0]['id']})
    tasks.change(root, owner_path, {'title':'Write review', 'parent_id':parent, 'status':'blocked', 'tab_id':tabs[1][0]['id']})
    metadata, body, tabs = documents.unpack(source.read_bytes())
    references = [owner_path, owner_path+'#tab='+tabs[0][0]['id']]
    originals = {path:path.read_bytes() for path in (root/'documents').glob('*.md')}
    assert len(originals) == args.notes
    documents._CACHE.pop(str(root), None)
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
    timings = ServerTimings(create_app(), correlate_requests=True)
    timings.instrument_handler('/api/assistant/note')
    if args.trace_projections:
        for module, names in [(documents, ('snapshot', '_fingerprint', 'deepcopy')), (records, ('resolve', 'progress_map'))]:
            for name in names:
                timings.trace_function(module, name)
    server = uvicorn.Server(uvicorn.Config(timings, access_log=False, log_level='warning',
        timeout_graceful_shutdown=5, ws_per_message_deflate=False))
    def run():
        with contextlib.redirect_stdout(sys.stderr):
            server.run(sockets=[sock])
    thread = threading.Thread(target=run)
    thread.start()
    hashes, revisions = {}, None
    try:
        deadline = time.monotonic()+15
        while not server.started:
            if not thread.is_alive() or time.monotonic() > deadline:
                raise RuntimeError('Fixture server failed')
            time.sleep(.01)
        with httpx.Client(base_url=url, timeout=60, cookies={auth.SESSION_COOKIE:cookie}) as client:
            for number in range(args.samples+1):
                fresh = number == args.samples
                if fresh:
                    assert originals == {path:path.read_bytes() for path in originals}
                    metadata['title'] = 'Fresh external detail edit café'
                    body += 'Fresh body.\n'
                    records.write_document(source, metadata, body)
                    metadata, body, tabs = documents.unpack(source.read_bytes())
                for reference in references:
                    measurement = dict(sample=len(report['samples'])+1, path=reference,
                        kind='subtab' if '#tab=' in reference else 'root', startEpoch=time.time()*1000, fresh=fresh)
                    report['samples'].append(measurement)
                    started = time.perf_counter()
                    try:
                        response = client.get('/api/assistant/note', params={'path':reference})
                    finally:
                        measurement['ms'] = (time.perf_counter()-started)*1000
                    measurement['status'] = response.status_code
                    response.raise_for_status()
                    current = verify_detail(response.json(), reference, source, owner_path, metadata, body, tabs)
                    digest = hashlib.sha256(response.content).hexdigest()
                    if fresh:
                        assert current[metadata['id']] != revisions[metadata['id']]
                        assert all(current[tab['id']] == revisions[tab['id']] for tab,_ in tabs)
                    elif reference in hashes:
                        assert hashes[reference] == digest and current == revisions
                    else:
                        hashes[reference] = digest
                        revisions = current
                    measurement.update(verified=True, responseSha256=digest, treeNodesVerified=3, tasksVerified=3)
        assert all(path.read_bytes() == raw for path,raw in originals.items() if path != source)
        report['filesPreserved'] = args.notes-1
        report['freshEditVerified'] = True
    except Exception as exc:
        report['error'] = repr(exc)
        raise
    finally:
        server.should_exit = True
        thread.join(15)
        sock.close()
        report['serverStopped'] = not thread.is_alive()
        Path(str(prefix)+'-server.json').write_text(json.dumps(timings.report(), indent=2)+'\n')
        Path(str(prefix)+'-http.json').write_text(json.dumps(report, indent=2)+'\n')
        if thread.is_alive():
            raise RuntimeError('Fixture server still running')
report['fixtureRemoved'] = not base.exists()
Path(str(prefix)+'-http.json').write_text(json.dumps(report, indent=2)+'\n')
print(json.dumps(report))
raise SystemExit(int(any(row['ms'] >= 200 for row in report['samples'])))
