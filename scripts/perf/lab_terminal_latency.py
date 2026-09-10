#!/usr/bin/env python3
"""Measure authenticated local Lab PTY/WebSocket echo, with and without polling.

Run with core/.venv/bin/python scripts/perf/lab_terminal_latency.py.
Creates and removes its own unsaved terminal; never types into a user terminal.
Uses the same local signed-session mechanism as scripts/check-ui.sh. Measures
transport latency, not browser paint or physical keyboard-to-screen latency.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import subprocess
import sys
import time
import uuid
from urllib.parse import quote

import httpx
import websockets

from core import auth
from core.routes.term import _tmux_command, _tmux_find_session_socket

ROOT = Path(__file__).resolve().parents[2]


def percentiles(values: list[float]) -> dict[str, float]:
    ordered = sorted(values)
    return {
        key: round(ordered[round((len(ordered) - 1) * fraction)], 2)
        for key, fraction in [('p50', .5), ('p95', .95), ('p99', .99), ('max', 1)]
    }


async def measure(samples: int, interval: float) -> None:
    base = subprocess.check_output([str(ROOT / 'scripts/lab-url.sh')], text=True).strip()
    user = auth.get_user(os.environ.get('UI_CHECK_USER', 'admin'))
    if user is None:
        raise RuntimeError('Local benchmark user does not exist')
    cookie = auth.issue_session(user)
    async with httpx.AsyncClient(base_url=base, timeout=30, cookies={auth.SESSION_COOKIE: cookie}) as client:
        response = await client.get('/api/auth/me')
        response.raise_for_status()  # Fail before reporting login-page timings.
        response = await client.post('/api/term/sessions', json={
            'kind': 'terminal', 'cwd': str(ROOT), 'name': 'latency-check-' + uuid.uuid4().hex,
        })
        response.raise_for_status()
        name = response.json()['name']
        resource = '/api/term/sessions/' + quote(name, safe='')
        try:
            # Replace only our newly created shell with a deterministic echo
            # process: shell initialization and completion plugins aren't PTY
            # transport cost. No changes to saved workspace terminal lists.
            marker = 'ready-' + uuid.uuid4().hex
            code = (
                'import os,tty; tty.setraw(0); '
                f'os.write(1,bytes.fromhex({marker.encode().hex()!r})); '
                'exec("while True:\\n os.write(1,os.read(0,4096))")'
            )
            socket = _tmux_find_session_socket(name)
            if not socket:
                raise RuntimeError('Could not find the newly created benchmark terminal')
            command = shlex.join([sys.executable, '-u', '-c', code])
            subprocess.run(_tmux_command(socket, 'respawn-pane', '-k', '-t', name, command), check=True)
            uri = base.replace('http:', 'ws:').replace('https:', 'wss:')
            uri += '/ws/term/' + quote(name, safe='') + '?cols=120&rows=32'
            async with websockets.connect(uri, additional_headers={
                'Cookie': f'{auth.SESSION_COOKIE}={cookie}',
            }, compression=None, max_size=None) as ws:
                async def receive_until(text: str) -> None:
                    seen = ''
                    async with asyncio.timeout(15):
                        while text not in seen:
                            frame = json.loads(await ws.recv())
                            if frame['type'] == 'exit':
                                raise RuntimeError('Benchmark terminal exited')
                            seen = (seen + frame.get('data', ''))[-65536:]

                await receive_until(marker)
                for loaded in (False, True):
                    requests = []

                    async def poll() -> None:
                        while True:
                            for path in (
                                '/api/vaults/workspaces', '/api/term/sessions',
                                '/api/term/sessions?workspace_id=__self__',
                            ):
                                started = time.perf_counter()
                                reply = await client.get(path)
                                reply.raise_for_status()
                                requests.append({'path': path, 'ms': round((time.perf_counter() - started) * 1000, 2)})
                            await asyncio.sleep(1)

                    task = asyncio.create_task(poll()) if loaded else None
                    times = []
                    try:
                        for index in range(samples):
                            character = chr(65 + index % 26)
                            started = time.perf_counter()
                            await ws.send(json.dumps({'type': 'input', 'data': character}))
                            await receive_until(character)
                            times.append((time.perf_counter() - started) * 1000)
                            await asyncio.sleep(interval)
                        if task and task.done():
                            task.result()  # Do not silently ignore failed load requests.
                    finally:
                        if task:
                            task.cancel()
                            await asyncio.gather(task, return_exceptions=True)
                    print(json.dumps({
                        'polling': loaded, 'echo_ms': percentiles(times),
                        'samples': len(times), 'requests': requests,
                    }), flush=True)
        finally:
            response = await client.delete(resource + '?purge=true')
            response.raise_for_status()
            print('Removed benchmark terminal.', file=sys.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--interval', type=float, default=.025, help='Seconds between keys')
    args = parser.parse_args()
    if args.samples < 20 or args.interval < 0:
        parser.error('Use at least 20 samples and a nonnegative interval')
    asyncio.run(measure(args.samples, args.interval))
