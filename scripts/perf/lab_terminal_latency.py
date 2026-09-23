#!/usr/bin/env python3
"""Measure authenticated local Lab PTY/WebSocket echo, with and without polling.

Run with core/.venv/bin/python scripts/perf/lab_terminal_latency.py.
Creates and removes its own terminal; never types into a user terminal.
Uses the same local signed-session mechanism as scripts/check-ui.sh. Measures
transport latency by default. Add --browser for synthetic keyboard-to-render
latency and an empty-page frame baseline (not physical keyboard/display delay).
The navigation fixture's --typing mode supplies --workspace and uses native CDP
input timestamps with normal polling instead of the older synthetic probe.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
from pathlib import Path
import shlex
import signal
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


def echo_program(marker: str, trace_path: Path | None = None) -> str:
    lines = ['import os,tty', 'tty.setraw(0)']
    if trace_path is not None:
        lines += [
            'import json,signal,time',
            'from pathlib import Path',
            f'trace_path=Path({str(trace_path)!r})',
            'events=[]',
            'def dump(signum,frame):',
            ' trace_path.write_text(json.dumps(events))',
            'signal.signal(signal.SIGUSR1,dump)',
            'trace_path.with_suffix(".pid").write_text(str(os.getpid()))',
        ]
    lines += [f'os.write(1,bytes.fromhex({marker.encode().hex()!r}))',
              'while True:', ' data=os.read(0,4096)', ' if not data: break']
    if trace_path is None:
        lines += [' os.write(1,data)']
    else:
        lines += [' received=time.time()*1000', ' written=os.write(1,data)',
                  ' events.append({"readEpoch":received,"writeEpoch":time.time()*1000,"bytes":len(data),"written":written})']
    return '\n'.join(lines)


async def dump_echo_trace(socket: str, name: str, trace_path: Path) -> None:
    # The PID file was written by our raw echo program. Verify that it still owns
    # the uniquely named fixture pane before signaling, never a reused PID.
    pid = int(trace_path.with_suffix('.pid').read_text())
    pane_pid = int(subprocess.check_output(
        _tmux_command(socket, 'display-message', '-p', '-t', name, '#{pane_pid}'),
        text=True, timeout=5).strip())
    if pid != pane_pid:
        raise RuntimeError('Owned echo process no longer owns the benchmark pane')
    os.kill(pid, signal.SIGUSR1)
    deadline = time.monotonic() + 5
    while time.monotonic() < deadline:
        try:
            json.loads(trace_path.read_text())
            return
        except (FileNotFoundError, json.JSONDecodeError):
            await asyncio.sleep(.01)
    raise RuntimeError('Owned echo process did not export its timing trace')


async def measure(samples: int, interval: float, browser: bool = False, base_url: str | None = None,
                  workspace: str | None = None) -> None:
    base = base_url or subprocess.check_output([str(ROOT / 'scripts/lab-url.sh')], text=True).strip()
    user = auth.get_user(os.environ.get('UI_CHECK_USER', 'admin'))
    if user is None:
        raise RuntimeError('Local benchmark user does not exist')
    cookie = auth.issue_session(user)
    async with httpx.AsyncClient(base_url=base, timeout=30, cookies={auth.SESSION_COOKIE: cookie}) as client:
        response = await client.get('/api/auth/me')
        response.raise_for_status()  # Fail before reporting login-page timings.
        body = {'kind': 'terminal', 'cwd': workspace or str(ROOT), 'name': 'latency-check-' + uuid.uuid4().hex}
        if workspace:
            body['workspace_id'] = Path(workspace).name
        response = await client.post('/api/term/sessions', json=body)
        response.raise_for_status()
        name = response.json()['name']
        resource = '/api/term/sessions/' + quote(name, safe='')
        echo_trace = None
        socket = None
        try:
            # Replace only our newly created shell with a deterministic echo
            # process: shell initialization and completion plugins aren't PTY
            # transport cost. A fixture-scoped session is purged in finally,
            # including its saved workspace entry.
            marker = 'ready-' + uuid.uuid4().hex
            if os.environ.get('LAB_PERF_ECHO_TRACE'):
                echo_trace = Path(os.environ['LAB_PERF_ECHO_TRACE']).resolve()
                fixture = Path(workspace).resolve().parents[2] if workspace else None
                if not fixture or not fixture.name.startswith('lab-navigation-') or echo_trace.parent != fixture:
                    raise RuntimeError('Echo tracing requires the disposable navigation fixture')
            code = echo_program(marker, echo_trace)
            socket = _tmux_find_session_socket(name)
            if not socket:
                raise RuntimeError('Could not find the newly created benchmark terminal')
            command = shlex.join([sys.executable, '-u', '-c', code])
            subprocess.run(_tmux_command(socket, 'respawn-pane', '-k', '-t', name, command), check=True)
            if browser:
                probe = 'lab_terminal_interactive_latency.mjs' if workspace else 'lab_terminal_render_latency.mjs'
                subprocess.run([
                    'node', str(ROOT / 'scripts/perf' / probe),
                    base, name, marker, str(samples), workspace or '', str(interval),
                ], cwd=ROOT, check=True, env={**os.environ, 'LAB_PROBE_COOKIE': cookie},
                   timeout=max(90, samples * interval * 2 + 60))
                return
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
            try:
                if echo_trace is not None and socket:
                    await dump_echo_trace(socket, name, echo_trace)
            finally:
                response = await client.delete(resource + '?purge=true')
                response.raise_for_status()
                print('Removed benchmark terminal.', file=sys.stderr)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--browser', action='store_true', help='Also exercise xterm input, parsing, and rendering in Chrome')
    parser.add_argument('--samples', type=int, default=200)
    parser.add_argument('--interval', type=float, default=.025, help='Seconds between keys')
    parser.add_argument('--base-url', help='Override the server URL, for an isolated fixture')
    parser.add_argument('--workspace', help='Workspace path for normal-UI input and sidebar-load measurements')
    args = parser.parse_args()
    if args.samples < 20 or args.interval < 0:
        parser.error('Use at least 20 samples and a nonnegative interval')
    if args.workspace and not args.browser:
        parser.error('--workspace requires --browser')
    asyncio.run(measure(args.samples, args.interval, args.browser, args.base_url, args.workspace))
