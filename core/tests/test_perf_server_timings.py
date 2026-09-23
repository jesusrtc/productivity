"""Keep benchmark diagnostics faithful to the application they observe."""
import asyncio
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

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
