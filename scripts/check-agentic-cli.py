#!/usr/bin/env python3
"""Opt-in real-CLI integration check in an isolated temporary Lab vault.

Uses existing provider login, creates only small local verification artifacts,
and never registers the test vault or changes the user's selected vault.
Run with core/.venv/bin/python scripts/check-agentic-cli.py.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time

from lab.agentic_store import Store, ACTIVE_RUNS
from core.agentic_runtime import launch, process_state


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--provider', action='append', choices=['codex', 'copilot', 'claude'])
    parser.add_argument('--timeout', type=int, default=420)
    args = parser.parse_args()
    root = Path(tempfile.mkdtemp(prefix='lab-agentic-cli-'))
    (root / 'content').mkdir()
    (root / 'lab.toml').write_text('[vault]\nname = "Agentic verification"\n')
    env = {**os.environ, 'LAB_VAULT': str(root), 'LAB_ROOT': str(root)}
    subprocess.run([sys.executable, '-m', 'lab', 'workspace', 'new', 'verification', '--kind', 'agentic'], env=env, check=True, capture_output=True)
    folder = root / 'workspaces' / 'verification'
    store = Store(folder)
    store.apply([{'type': 'mission-create', 'id': 'verification', 'title': 'CLI integration verification',
                  'objective': 'Prove each configured CLI can execute a local task and return its evidence to Lab.'}])
    print(json.dumps({'vault': str(root), 'workspace': str(folder)}), flush=True)
    processes, runs = [], []
    for provider in args.provider or ['codex', 'copilot', 'claude']:
        target = f'{provider}-proof.txt'
        store.apply([{'type': 'task-create', 'id': provider, 'mission_id': 'verification',
                      'title': f'{provider} local execution',
                      'instruction': f'This is an authorized integration test. Create exactly {target} in this workspace containing the line "Verified by {provider}" followed by one newline. Read it back and report the exact content. Do not install anything, contact external services other than your model, or modify any other files. Return the required final JSON with the actual task status and this file as an output asset only if created and verified. This is a small test; do not create agents or perform unrelated exploration.'}])
        run = store.reserve(provider=provider)
        assert run['task_id'] == provider
        runs.append(run)
    for run in runs:
        processes.append(launch(store, run, root, 'verification'))
    deadline = time.monotonic() + args.timeout
    reported, permissions = set(), set()
    while time.monotonic() < deadline:
        for run in runs:
            current = store.run(run['id'])
            if current['status'] not in ACTIVE_RUNS and run['id'] not in reported:
                task = store.detail(run['task_id'])
                print(json.dumps({'provider': run['provider'], 'run_status': current['status'], 'task_status': task['task']['status'], 'error': current.get('error'),
                                  'result': task['task']['result'], 'assets': task['assets']}), flush=True)
                reported.add(run['id'])
        for permission in store.snapshot()['permissions']:
            if permission['status'] == 'pending' and permission['id'] not in permissions:
                print(json.dumps({'permission': permission}), flush=True)
                permissions.add(permission['id'])
        if len(reported) == len(runs):
            break
        time.sleep(1)
    for process in processes:
        if process:
            process.poll()
    final = []
    for run in runs:
        proof = folder / f'{run["provider"]}-proof.txt'
        final.append({'provider': run['provider'], 'run': run['id'], 'status': store.run(run['id'])['status'],
                      'task_status': store.detail(run['task_id'])['task']['status'],
                      'verified': proof.is_file() and proof.read_text() == f'Verified by {run["provider"]}\n',
                      'live': process_state(store.run(run['id']))})
    print(json.dumps({'runs': final, 'evidence': str(store.directory)}), flush=True)
    return 0 if all(r['task_status'] == 'completed' and r['verified'] for r in final) else 1


if __name__ == '__main__':
    raise SystemExit(main())
