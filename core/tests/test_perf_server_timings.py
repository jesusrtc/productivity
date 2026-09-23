"""Keep benchmark diagnostics faithful to the application they observe."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest
import httpx

from fastapi import APIRouter, FastAPI
from starlette.testclient import TestClient


_spec = importlib.util.spec_from_file_location(
    'lab_perf_server_timings', Path(__file__).resolve().parents[2]
    / 'scripts/perf/server_timings.py')
_module = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_module)
ServerTimings = _module.ServerTimings


def test_stream_timing_preserves_messages_and_omits_secrets():
    messages = [
        {'type': 'http.response.start', 'status': 200, 'headers': [(b'secret', b'value')]},
        {'type': 'http.response.body', 'body': b'private', 'more_body': True},
        {'type': 'http.response.body', 'body': b'body'},
    ]
    received = []

    async def app(scope, receive, send):
        for message in messages:
            await send(message)
            await asyncio.sleep(.002)

    async def send(message):
        received.append(message)

    timings = ServerTimings(app)
    asyncio.run(timings({'type': 'http', 'path': '/api/term/sessions', 'method': 'GET',
                        'query_string': b'workspace_id=alpha&token=hidden'}, None, send))
    assert received == messages
    row, = timings.requests
    assert row['workspace'] == 'alpha' and row['status'] == 200
    assert 0 <= row['headersMs'] < row['ms'] < row['appMs']
    assert not any(secret in str(timings.report()) for secret in ('private', 'hidden', 'secret'))


def test_lifespan_and_websocket_pass_through():
    received = []

    async def app(*args):
        received.append(args)
        return 'unchanged'

    timings = ServerTimings(app)
    for kind in ('lifespan', 'websocket'):
        scope = {'type': kind}
        assert asyncio.run(timings(scope, 'receive', 'send')) == 'unchanged'
        assert received[-1] == (scope, 'receive', 'send')
    assert timings.report()['requests'] == []


def test_failed_response_is_recorded_without_fabricating_completion():
    async def app(scope, receive, send):
        raise RuntimeError('original failure')

    timings = ServerTimings(app)
    with pytest.raises(RuntimeError, match='original failure'):
        asyncio.run(timings({'type': 'http', 'path': '/api/example', 'method': 'GET'}, None, None))
    row, = timings.requests
    assert row['appMs'] >= 0
    assert 'ms' not in row and 'status' not in row


def test_nested_router_times_actual_handler_without_changing_response():
    app = FastAPI()
    router, nested = APIRouter(), APIRouter()

    @nested.get('/api/term/sessions')
    def list_sessions(workspace_id: str | None = None):
        return [{'name': workspace_id}]

    router.include_router(nested)
    app.include_router(router)
    timings = ServerTimings(app)
    timings.instrument_sessions()
    with TestClient(timings) as client:
        response = client.get('/api/term/sessions?workspace_id=alpha')
        assert response.status_code == 200
        assert response.json() == [{'name': 'alpha'}]
    request, = timings.requests
    session, = timings.sessions
    assert session['workspace'] == request['workspace'] == 'alpha'
    assert session['startEpoch'] >= request['startEpoch']
    assert 0 <= session['ms'] < request['ms']
    assert isinstance(session['thread'], int)


def test_function_timings_preserve_results_exceptions_and_omit_arguments():
    def function(value):
        if value is None:
            raise ValueError('original error')
        return value

    module = SimpleNamespace(function=function)
    timings = ServerTimings(None)
    timings.trace_function(module, 'function')
    assert module.function('private argument') == 'private argument'
    with pytest.raises(ValueError, match='original error'):
        module.function(None)
    assert len(timings.functions) == 2
    assert all(row['function'] == 'function' and row['ms'] >= 0 for row in timings.functions)
    assert 'private' not in str(timings.report())


def test_request_correlation_preserves_existing_headers_and_messages():
    start = {'type': 'http.response.start', 'status': 200,
             'headers': [(b'server-timing', b'existing;dur=3'), (b'x-original', b'yes')]}
    body = {'type': 'http.response.body', 'body': b'unchanged'}
    received = []

    async def app(scope, receive, send):
        await send(start)
        await send(body)

    async def send(message):
        received.append(message)

    timings = ServerTimings(app, correlate_requests=True)
    asyncio.run(timings({'type': 'http', 'path': '/api/example', 'method': 'GET'}, None, send))
    row, = timings.requests
    assert received[0]['headers'] == [*start['headers'],
        (b'server-timing', f'lab-perf;desc="{row["id"]}"'.encode())]
    assert len(start['headers']) == 2
    assert received[1] is body


def test_concurrent_worker_and_async_handlers_keep_distinct_request_ids():
    app = FastAPI()

    @app.get('/api/worker')
    def worker(value: int):
        return {'value': value}

    @app.get('/api/async')
    async def async_handler(value: int):
        await asyncio.sleep(.002)
        return {'value': value}

    timings = ServerTimings(app, correlate_requests=True)
    timings.instrument_handler('/api/worker')
    timings.instrument_handler('/api/async')

    async def exercise():
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=timings),
                                    base_url='http://fixture') as client:
            responses = await asyncio.gather(*[
                client.get(f'/api/{kind}?value={value}')
                for value, kind in enumerate(['worker', 'async'] * 3)
            ])
        assert timings._request_id.get() is None
        return responses

    responses = asyncio.run(exercise())
    ids = set()
    for value, response in enumerate(responses):
        assert response.json() == {'value': value}
        request_id = int(response.headers['server-timing'].split('"')[1])
        ids.add(request_id)
        request, = [r for r in timings.requests if r['id'] == request_id]
        handler, = [r for r in timings.handlers if r['requestId'] == request_id]
        assert request['route'] == handler['route']
        assert handler['startEpoch'] >= request['startEpoch']
        assert 0 <= handler['ms'] < request['ms']
    assert len(ids) == 6


def test_async_function_tracing_keeps_await_result_and_exception():
    async def function(value):
        await asyncio.sleep(.001)
        if value is None:
            raise ValueError('original async error')
        return value

    module = SimpleNamespace(function=function)
    timings = ServerTimings(None)
    timings.trace_function(module, 'function')
    assert asyncio.run(module.function('private argument')) == 'private argument'
    with pytest.raises(ValueError, match='original async error'):
        asyncio.run(module.function(None))
    assert len(timings.functions) == 2
    assert all(row['ms'] >= 1 for row in timings.functions)
    assert 'private' not in str(timings.report())


def test_terminal_timings_preserve_frames_context_and_omit_payloads():
    incoming = {'type': 'websocket.receive', 'text': '{"type":"input","data":"private input"}'}
    outgoing = {'type': 'websocket.send', 'text': '{"type":"data","data":"private output"}'}
    seen = []

    async def app(scope, receive, send):
        connection = timings._terminal_id.get()
        assert connection is not None
        assert await receive() is incoming
        await asyncio.sleep(.001)
        assert timings._terminal_id.get() == connection
        await send(outgoing)
        return connection

    async def receive():
        return incoming

    async def send(message):
        assert message is outgoing
        seen.append(message)

    timings = ServerTimings(app, trace_terminal=True)

    async def exercise():
        ids = await asyncio.gather(*[timings({'type': 'websocket', 'path': '/ws/term/private-name'}, receive, send) for _ in range(2)])
        assert timings._terminal_id.get() is None
        return ids

    assert asyncio.run(exercise()) == [1, 2]
    for connection in (1, 2):
        received, sent = [r for r in timings.terminal if r['connection'] == connection]
        assert received['stage'] == 'ws.receive' and received['kind'] == 'input'
        assert received['dataLength'] == len('private input')
        assert sent['stage'] == 'ws.send' and sent['kind'] == 'data'
        assert sent['dataLength'] == len('private output') and sent['ms'] >= 0
        assert sent['epoch'] >= received['epoch']
    assert 'private' not in str(timings.report())
    assert len(seen) == 2


def test_terminal_pty_timing_keeps_short_writes_errors_and_descriptor_scope():
    calls = []
    fail = False

    def read(fd, size):
        calls.append(('read', fd, size))
        if fail:
            raise BlockingIOError('private error')
        return b'private bytes'

    def write(fd, data):
        calls.append(('write', fd, data))
        return 2  # Preserve the partial count for the application's retry loop.

    original_os = SimpleNamespace(read=read, write=write, close=lambda fd:calls.append(('close', fd)), sentinel=object())
    original_pty = SimpleNamespace(fork=lambda:(42, 8))
    module = SimpleNamespace(os=original_os, pty=original_pty)
    timings = ServerTimings(None, trace_terminal=True)
    with timings.trace_terminal_io(module):
        assert module.os.sentinel is original_os.sentinel
        assert module.pty.fork() == (42, 8)  # No connection context: no recording.
        assert module.os.read(8, 99) == b'private bytes'
        assert timings.terminal == []
        token = timings._terminal_id.set(7)
        try:
            assert module.pty.fork() == (42, 8)
        finally:
            timings._terminal_id.reset(token)
        assert module.os.read(8, 100) == b'private bytes'
        assert module.os.write(8, b'private write') == 2
        fail = True
        with pytest.raises(BlockingIOError, match='private error'):
            module.os.read(8, 101)
        fail = False
        module.os.close(8)
        assert module.os.read(8, 102) == b'private bytes'  # Reused/closed fd is untracked.
    assert module.os is original_os and module.pty is original_pty
    assert [(r['stage'], r.get('bytes'), r.get('error')) for r in timings.terminal] == [
        ('pty.fork', None, None), ('pty.read', len(b'private bytes'), None),
        ('pty.write', 2, None), ('pty.read', None, 'BlockingIOError'), ('pty.close', None, None)]
    assert all(r['connection'] == 7 and r['ms'] >= 0 for r in timings.terminal)
    assert 'private' not in str(timings.report())
    assert calls[-1] == ('read', 8, 102)


def test_terminal_tracing_keeps_unrelated_websockets_untouched():
    original = []

    async def app(*args):
        original.append(args)
        return 3

    timings = ServerTimings(app, trace_terminal=True)
    scope = {'type': 'websocket', 'path': '/ws'}
    assert asyncio.run(timings(scope, 'receive', 'send')) == 3
    assert original == [(scope, 'receive', 'send')]
    assert timings.terminal == []


def test_terminal_close_trace_keeps_a_concurrently_reused_descriptor():
    timings = ServerTimings(None, trace_terminal=True)
    module = SimpleNamespace(pty=SimpleNamespace(fork=lambda:(42, 8)))

    def close(fd):
        # Model the event loop opening another PTY as a worker finishes close.
        token = timings._terminal_id.set(8)
        try:
            module.pty.fork()
        finally:
            timings._terminal_id.reset(token)

    module.os = SimpleNamespace(close=close, read=lambda fd, size:b'new data')
    with timings.trace_terminal_io(module):
        token = timings._terminal_id.set(7)
        try:
            module.pty.fork()
        finally:
            timings._terminal_id.reset(token)
        module.os.close(8)
        module.os.read(8, 100)
    assert [(r['stage'], r['connection']) for r in timings.terminal] == [
        ('pty.fork', 7), ('pty.fork', 8), ('pty.close', 7), ('pty.read', 8)]


def _terminal_probe_module():
    spec = importlib.util.spec_from_file_location(
        'lab_perf_terminal_probe', Path(__file__).resolve().parents[2]
        / 'scripts/perf/lab_terminal_latency.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize('traced', [False, True])
def test_owned_echo_program_preserves_bytes_and_exports_only_timing(tmp_path, traced):
    import json
    import os
    import pty
    import select
    import signal
    import subprocess
    import sys
    import time

    module = _terminal_probe_module()
    path = tmp_path / 'echo.json'
    master, slave = pty.openpty()
    child = subprocess.Popen([sys.executable, '-u', '-c', module.echo_program('READY', path if traced else None)],
                             stdin=slave, stdout=slave, stderr=subprocess.PIPE)
    os.close(slave)

    def read_exact(expected):
        output = b''
        deadline = time.monotonic() + 3
        while len(output) < len(expected):
            assert time.monotonic() < deadline and child.poll() is None
            if select.select([master], [], [], .1)[0]:
                output += os.read(master, 4096)
        assert output == expected

    try:
        read_exact(b'READY')
        for value in (b'a', b'bc'):
            os.write(master, value)
            read_exact(value)
        if traced:
            assert int(path.with_suffix('.pid').read_text()) == child.pid
            child.send_signal(signal.SIGUSR1)
            deadline = time.monotonic() + 3
            while True:
                try:
                    rows = json.loads(path.read_text())
                    break
                except (FileNotFoundError, json.JSONDecodeError):
                    assert time.monotonic() < deadline
                    time.sleep(.01)
            assert sum(row['bytes'] for row in rows) == 3
            assert all(row['bytes'] == row['written'] and row['writeEpoch'] >= row['readEpoch'] for row in rows)
            assert all(set(row) == {'readEpoch', 'writeEpoch', 'bytes', 'written'} for row in rows)
        else:
            assert not path.exists() and not path.with_suffix('.pid').exists()
    finally:
        child.terminate()
        child.wait(timeout=3)
        child.stderr.close()
        os.close(master)


@pytest.mark.parametrize('owns_pane', [False, True])
def test_echo_export_never_signals_a_reused_pid(tmp_path, monkeypatch, owns_pane):
    module = _terminal_probe_module()
    path = tmp_path / 'echo.json'
    path.with_suffix('.pid').write_text('321')
    monkeypatch.setattr(module.subprocess, 'check_output', lambda *args, **kwargs:'321' if owns_pane else '654')
    signaled = []

    def kill(pid, sig):
        signaled.append((pid, sig))
        path.write_text('[]')

    monkeypatch.setattr(module.os, 'kill', kill)
    if owns_pane:
        asyncio.run(module.dump_echo_trace('fixture', 'owned-terminal', path))
        assert signaled == [(321, module.signal.SIGUSR1)]
    else:
        with pytest.raises(RuntimeError, match='no longer owns'):
            asyncio.run(module.dump_echo_trace('fixture', 'owned-terminal', path))
        assert signaled == []


def test_failed_terminal_send_is_reported_and_preserves_the_exception():
    async def app(scope, receive, send):
        await send({'type':'websocket.send', 'text':'private body'})

    async def send(message):
        raise OSError('private exception')

    timings = ServerTimings(app, trace_terminal=True)
    with pytest.raises(OSError, match='private exception'):
        asyncio.run(timings({'type':'websocket', 'path':'/ws/term/private-name'}, None, send))
    row, = timings.terminal
    assert row['stage'] == 'ws.send' and row['error'] == 'OSError' and row['ms'] >= 0
    assert timings._terminal_id.get() is None
    assert 'private' not in str(timings.report())
