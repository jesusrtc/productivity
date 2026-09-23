"""Opt-in diagnostics for the isolated latency fixture, never production middleware."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from inspect import iscoroutinefunction
from itertools import count
import json
from threading import get_ident
import time
from urllib.parse import parse_qs


class ServerTimings:
    """Time ASGI entry through response completion, preserving response bodies.

    Socket acceptance/event-loop delay before ASGI entry is outside this measure.
    Only the route and workspace scope are recorded, never headers or bodies.
    Optional fixture-only Server-Timing headers correlate browser/server records.
    """

    def __init__(self, app, *, correlate_requests=False, trace_terminal=False):
        self.app = app
        self.correlate_requests = correlate_requests
        self.trace_terminal = trace_terminal
        self._terminal_id = ContextVar('lab_perf_terminal_id', default=None)
        self._terminal_numbers = count(1)
        self.terminal = []
        self._numbers = count(1)
        self._request_id = ContextVar('lab_perf_request_id', default=None)
        self.requests = []
        self.sessions = []
        self.handlers = []
        self.functions = []

    async def __call__(self, scope, receive, send):
        if self.trace_terminal and scope['type'] == 'websocket' and scope.get('path', '').startswith('/ws/term/'):
            return await self._terminal_connection(scope, receive, send)
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        start = time.perf_counter()
        query = parse_qs(scope.get('query_string', b'').decode('utf-8', errors='replace'))
        row = {
            'id': next(self._numbers),
            'route': scope['path'], 'method': scope['method'],
            'workspace': query.get('workspace_id', [None])[0],
            'startEpoch': time.time() * 1000,
        }

        async def timed_send(message):
            if self.correlate_requests and message['type'] == 'http.response.start':
                # Fixture-only correlation, exposed through ResourceTiming.
                # Copy rather than mutate the application's message/headers.
                message = {**message, 'headers': [*message.get('headers', []),
                    (b'server-timing', f'lab-perf;desc="{row["id"]}"'.encode())]}
            await send(message)
            elapsed = (time.perf_counter() - start) * 1000
            if message['type'] == 'http.response.start':
                row.update(status=message['status'], headersMs=elapsed)
            elif message['type'] == 'http.response.body' and not message.get('more_body', False):
                row['ms'] = elapsed

        token = self._request_id.set(row['id'])
        try:
            await self.app(scope, receive, timed_send)
        finally:
            row['appMs'] = (time.perf_counter() - start) * 1000
            self.requests.append(row)
            self._request_id.reset(token)

    async def _terminal_connection(self, scope, receive, send):
        connection = next(self._terminal_numbers)

        def record(stage, message):
            row = {'connection': connection, 'stage': stage, 'epoch': time.time() * 1000,
                   'event': message['type']}
            text = message.get('text')
            if isinstance(text, str):
                row['characters'] = len(text)
                try:
                    body = json.loads(text)
                except (ValueError, TypeError):
                    body = None
                if isinstance(body, dict):
                    kind = body.get('type')
                    if kind in ('input', 'resize', 'data', 'exit', 'detach'):
                        row['kind'] = kind
                    if isinstance(body.get('data'), str):
                        row['dataLength'] = len(body['data'])
            self.terminal.append(row)
            return row

        async def timed_receive():
            message = await receive()
            record('ws.receive', message)
            return message

        async def timed_send(message):
            row = record('ws.send', message)
            start = time.perf_counter()
            try:
                return await send(message)
            except BaseException as error:
                row['error'] = type(error).__name__
                raise
            finally:
                row['ms'] = (time.perf_counter() - start) * 1000

        token = self._terminal_id.set(connection)
        try:
            return await self.app(scope, timed_receive, timed_send)
        finally:
            self._terminal_id.reset(token)

    @contextmanager
    def trace_terminal_io(self, module):
        """Observe only term.py's owned PTY descriptors, without altering global os.

        Wrappers keep byte content private and preserve short writes/errors. The
        original module dependencies are restored when the fixture finishes.
        """
        original_os, original_pty = module.os, module.pty
        descriptors = {}
        owner = self

        def record(connection, stage, start, **fields):
            owner.terminal.append({'connection': connection, 'stage': stage,
                'epoch': time.time() * 1000, 'ms': (time.perf_counter() - start) * 1000, **fields})

        class OsProxy:
            def __getattr__(self, name):
                return getattr(original_os, name)

            def _io(self, operation, fd, value):
                connection = descriptors.get(fd)
                if connection is None:
                    return getattr(original_os, operation)(fd, value)
                start = time.perf_counter()
                try:
                    result = getattr(original_os, operation)(fd, value)
                except BaseException as error:
                    record(connection, 'pty.' + operation, start, error=type(error).__name__)
                    raise
                record(connection, 'pty.' + operation, start,
                       bytes=len(result) if operation == 'read' else result)
                return result

            def read(self, fd, size):
                return self._io('read', fd, size)

            def write(self, fd, data):
                return self._io('write', fd, data)

            def close(self, fd):
                try:
                    return original_os.close(fd)
                finally:
                    descriptors.pop(fd, None)

        class PtyProxy:
            def __getattr__(self, name):
                return getattr(original_pty, name)

            def fork(self):
                pid, fd = original_pty.fork()
                connection = owner._terminal_id.get()
                if pid > 0 and connection is not None:
                    descriptors[fd] = connection
                return pid, fd

        module.os, module.pty = OsProxy(), PtyProxy()
        try:
            yield
        finally:
            module.os, module.pty = original_os, original_pty

    def instrument_sessions(self):
        """Measure the synchronous handler separately from dependencies/worker queuing."""
        self.instrument_handler('/api/term/sessions', self.sessions)

    def instrument_handler(self, path, records=None):
        """Time one declared GET handler without warming its route context."""
        if records is None:
            records = self.handlers
        numbers = count(1)
        def declared_routes(router):
            for route in router.routes:
                included = getattr(route, 'original_router', None)
                if included is not None:
                    yield from declared_routes(included)
                else:
                    yield route

        # New FastAPI versions retain lazy included routers. Walk declarations
        # without constructing their effective contexts and warming route setup.
        routes = [route for route in declared_routes(self.app)
                  if getattr(route, 'path', None) == path
                  and 'GET' in getattr(route, 'methods', set())]
        if len(routes) != 1:
            raise RuntimeError(f'Expected exactly one GET route for {path}')
        original = routes[0].dependant.call

        def begin(kwargs):
            number = next(numbers)
            row = {'sample': number, 'route': path, 'requestId': self._request_id.get(),
                   'workspace': kwargs.get('workspace_id'),
                   'startEpoch': time.time() * 1000, 'thread': get_ident()}
            return row, time.perf_counter()

        if iscoroutinefunction(original):
            @wraps(original)
            async def timed(*args, **kwargs):
                row, start = begin(kwargs)
                try:
                    return await original(*args, **kwargs)
                finally:
                    row['ms'] = (time.perf_counter() - start) * 1000
                    records.append(row)
        else:
            @wraps(original)
            def timed(*args, **kwargs):
                row, start = begin(kwargs)
                try:
                    return original(*args, **kwargs)
                finally:
                    row['ms'] = (time.perf_counter() - start) * 1000
                    records.append(row)

        routes[0].endpoint = timed
        routes[0].dependant.call = timed

    def trace_function(self, module, name):
        """Optional coarse function timings, including calls on fsguard workers.

        These are wall times, not exclusive CPU costs. Nested/concurrent calls
        must not be summed. Arguments/results are deliberately not recorded.
        """
        original = getattr(module, name)

        def begin():
            row = {'function': name, 'requestId': self._request_id.get(),
                   'thread': get_ident(), 'startEpoch': time.time() * 1000}
            return row, time.perf_counter()

        if iscoroutinefunction(original):
            @wraps(original)
            async def timed(*args, **kwargs):
                row, start = begin()
                try:
                    return await original(*args, **kwargs)
                finally:
                    row['ms'] = (time.perf_counter() - start) * 1000
                    self.functions.append(row)
        else:
            @wraps(original)
            def timed(*args, **kwargs):
                row, start = begin()
                try:
                    return original(*args, **kwargs)
                finally:
                    row['ms'] = (time.perf_counter() - start) * 1000
                    self.functions.append(row)

        setattr(module, name, timed)

    def report(self):
        return {'measurement': 'ASGI entry through final response body; excludes pre-entry queueing',
                'requests': self.requests, 'sessions': self.sessions,
                'handlers': self.handlers, 'functions': self.functions, 'terminal': self.terminal}
