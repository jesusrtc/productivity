#!/usr/bin/env python3
"""Opt-in full local agent → Lab CLI → live Jupyter workflow verification.

Uses an isolated vault, Lab home and loopback server. Installs nothing and does
not change the selected vault or restart the user's Lab server. --keep-server
keeps this owned test instance available for a subsequent browser check.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import httpx


def observe(client, root, manifest, timeout):
    path = 'workspaces/verification/analysis.ipynb'
    deadline, previous, live_seen = time.monotonic() + timeout, None, (root / 'live-observed.json').is_file()
    while time.monotonic() < deadline:
        try:
            response = client.get('/api/agentic/verification')
            response.raise_for_status()
            state = response.json()
        except httpx.TransportError:
            # Observation can reconnect after an intentional backend restart;
            # it never resubmits the mission or launches another executor.
            time.sleep(.5)
            continue
        brief = {'tasks': [(t['id'], t['status']) for t in state['tasks']],
                 'runs': [(r['role'], r['status']) for r in state['runs']],
                 'messages': [(m['role'], m['status'], m['content'][:400]) for m in state['messages'] if m['role'] != 'event']}
        if brief != previous:
            print(json.dumps(brief, ensure_ascii=False), flush=True)
            previous = brief
        if (Path(manifest['workspace']) / 'analysis.ipynb').exists():
            try:
                notebook = client.get('/api/nb', params={'path': path}).json()
            except httpx.TransportError:
                continue
            if not live_seen and any(c.get('metadata', {}).get('lab_pending') for c in notebook.get('cells', [])):
                live_seen = True
                (root / 'live-observed.json').write_text(json.dumps({'observed_at': time.time(), 'path': path}))
        tasks = [t for t in state['tasks'] if not t.get('group')]
        if tasks and any(t['status'] == 'review' for t in tasks) and all(t['status'] in ('completed', 'review') for t in tasks):
            nb = json.loads((Path(manifest['workspace']) / 'analysis.ipynb').read_text())
            outputs = json.dumps([c.get('outputs', []) for c in nb['cells']])
            report = (Path(manifest['workspace']) / 'report.md').read_text()
            assert len(nb['cells']) >= 2 and '200' in outputs
            assert all(c['metadata'].get('lab_actor') == 'agent' for c in nb['cells'] if c['cell_type'] == 'code')
            assert '200' in report and live_seen
            assert any(a['target'] == 'analysis.ipynb' for a in state['assets'])
            evidence = {'passed': True, 'live_execution_seen': live_seen, 'cells': len(nb['cells']),
                        'review_gate_held': True, **manifest}
            (root / 'result.json').write_text(json.dumps(evidence, indent=2))
            print(json.dumps(evidence), flush=True)
            return 0
        time.sleep(.5)
    print(json.dumps({'passed': False, 'reason': 'Deadline reached; inspect actual run state before retrying', **manifest}), flush=True)
    return 1


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', choices=['codex', 'claude', 'copilot'], default='claude')
    parser.add_argument('--timeout', type=int, default=600)
    parser.add_argument('--keep-server', action='store_true')
    parser.add_argument('--resume', type=Path, help='Observe an existing verification.json without relaunching any work')
    args = parser.parse_args()
    if args.resume:
        manifest = json.loads(args.resume.read_text())
        root = args.resume.parent
        with httpx.Client(base_url=manifest['url'], timeout=120) as client:
            client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'}).raise_for_status()
            return observe(client, root, manifest, args.timeout)
    root = Path(tempfile.mkdtemp(prefix='lab-agentic-workflow-')).resolve()
    (root / 'content').mkdir()
    (root / 'lab.toml').write_text('[vault]\nname = "Agentic workflow verification"\n')
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    base = f'http://127.0.0.1:{port}'
    env = {**os.environ, 'LAB_VAULT': str(root), 'LAB_ROOT': str(root), 'LAB_HOME': str(root / '.test-home'),
           'LAB_HOST': '127.0.0.1', 'LAB_PORT': str(port), 'LAB_URL': base, 'LAB_ENV_FILE': str(root / 'missing.env'),
           'LAB_WORKSPACE_WATCHER': 'off', 'LAB_AGENTIC_SUPERVISOR': '1', 'LAB_SERVER_SUPERVISOR': '0',
           'LAB_DOCUMENT_TERMINALS_SUPERVISOR': '0', 'LAB_TASK_SCHEDULER': '0', 'LAB_TASK_TERMINAL_CLEANUP': '0',
           'LAB_TERMINAL_PROGRESS': '0', 'LAB_AUTOMATION_RECOVERY': '0', 'LAB_TMUX_PREFIX': 'lab-agentic-verification-' + root.name + '-'}
    for name in ('TMUX', 'TMUX_PANE', 'LAB_CONTEXT_WORKSPACE', 'LAB_CONTEXT_OBJECTIVE', 'LAB_DOCUMENT_CONTEXT'):
        env.pop(name, None)
    def cli(*command):
        return subprocess.run([sys.executable, '-m', 'lab', *command], env=env, cwd=root, capture_output=True, text=True, check=True)
    cli('workspace', 'new', 'verification', '--kind', 'agentic')
    cli('workspace', 'set', 'verification', 'agent', args.provider)
    folder = root / 'workspaces/verification'
    (folder / 'input.csv').write_text('period,value\nJanuary,10\nFebruary,20\nMarch,30\n')
    with (root / 'server.log').open('w') as output:
        process = subprocess.Popen([sys.executable, '-m', 'core'], cwd=root, env=env,
                                   stdout=output, stderr=subprocess.STDOUT, start_new_session=True)
    manifest = {'vault': str(root), 'workspace': str(folder), 'url': base, 'server_pid': process.pid,
                'home': env['LAB_HOME'], 'provider': args.provider}
    (root / 'verification.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest), flush=True)
    try:
        with httpx.Client(base_url=base, timeout=120) as client:
            for _ in range(60):
                try:
                    response = client.get('/api/auth/me')
                    if response.status_code in (200, 401):
                        break
                except httpx.ConnectError:
                    pass
                if process.poll() is not None:
                    raise RuntimeError('Test server exited; inspect ' + str(root / 'server.log'))
                time.sleep(.5)
            client.post('/api/auth/login', json={'username': 'admin', 'password': 'admin'}).raise_for_status()
            path = 'workspaces/verification/analysis.ipynb'
            client.put('/api/nb/runtime', json={'path': path, 'spec': {'version': 1, 'mode': 'local', 'kind': 'existing',
                       'python': sys.executable, 'packages': [], 'imports': [], 'working_dir': '.'}}).raise_for_status()
            client.post('/api/nb/runtime/build', json={'path': path}).raise_for_status()
            content = '''Nueva misión de prueba autorizada y pequeña: analiza input.csv.
Confirma brevemente lo que entendiste y delega dos tareas: (1) usa lab notebook exec
para crear y ejecutar analysis.ipynb con un cálculo del crecimiento de enero a marzo;
usa solo la librería estándar y el runtime local ya configurado, sin instalar nada.
Ejecuta una celda que defina initial=10 y final=30, y otra celda que reutilice esas
variables, calcule (final-initial)/initial*100 e imprima el resultado. En esa segunda
celda incluye time.sleep(4) para que pueda comprobar la ejecución en vivo.
(2) después del análisis, escribe report.md con el resultado y la referencia al
notebook. Esa segunda tarea debe quedar esperando mi revisión. Registra el CSV,
el notebook y el reporte como assets en sus tareas. No publiques, no contactes
servicios externos ni leas otros proyectos. Termina cuando las muestras estén listas.'''
            client.post('/api/agentic/verification/messages', json={'content': content, 'request_id': 'workflow-proof'}).raise_for_status()
            return observe(client, root, manifest, args.timeout)
    finally:
        if not args.keep_server:
            # Server shutdown does not imply task success or terminate detached
            # runners. Inspect the retained database before retrying timed-out work.
            process.terminate()
            try:
                process.wait(timeout=15)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


if __name__ == '__main__':
    raise SystemExit(main())
