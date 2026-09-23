"""Opt-in diagnostics for the isolated latency fixture, never production middleware."""
from __future__ import annotations

from functools import wraps
from itertools import count
from threading import get_ident
import time
from urllib.parse import parse_qs


class ServerTimings:
    """Time ASGI entry through response completion without changing responses.

    Socket acceptance/event-loop delay before ASGI entry is outside this measure.
    Only the route and workspace scope are recorded, never headers or bodies.
    """

    def __init__(self, app):
        self.app = app
        self.requests = []
        self.sessions = []
        self.functions = []

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http':
            return await self.app(scope, receive, send)
        start = time.perf_counter()
        query = parse_qs(scope.get('query_string', b'').decode('utf-8', errors='replace'))
        row = {
            'route': scope['path'], 'method': scope['method'],
            'workspace': query.get('workspace_id', [None])[0],
            'startEpoch': time.time() * 1000,
        }

        async def timed_send(message):
            await send(message)
            elapsed = (time.perf_counter() - start) * 1000
            if message['type'] == 'http.response.start':
                row.update(status=message['status'], headersMs=elapsed)
            elif message['type'] == 'http.response.body' and not message.get('more_body', False):
                row['ms'] = elapsed

        try:
            await self.app(scope, receive, timed_send)
        finally:
            row['appMs'] = (time.perf_counter() - start) * 1000
            self.requests.append(row)

    def instrument_sessions(self):
        """Measure the synchronous handler separately from dependencies/worker queuing."""
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
                  if getattr(route, 'path', None) == '/api/term/sessions'
                  and 'GET' in getattr(route, 'methods', set())]
        if len(routes) != 1:
            raise RuntimeError('Expected exactly one terminal sessions GET route')
        original = routes[0].dependant.call

        @wraps(original)
        def timed_sessions(*args, **kwargs):
            number = next(numbers)
            row = {'sample': number, 'workspace': kwargs.get('workspace_id'),
                   'startEpoch': time.time() * 1000, 'thread': get_ident()}
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                row['ms'] = (time.perf_counter() - start) * 1000
                self.sessions.append(row)

        routes[0].endpoint = timed_sessions
        routes[0].dependant.call = timed_sessions

    def trace_function(self, module, name):
        """Optional coarse function timings, including calls on fsguard workers.

        These are wall times, not exclusive CPU costs. Nested/concurrent calls
        must not be summed. Arguments/results are deliberately not recorded.
        """
        original = getattr(module, name)

        @wraps(original)
        def timed(*args, **kwargs):
            row = {'function': name, 'thread': get_ident(), 'startEpoch': time.time() * 1000}
            start = time.perf_counter()
            try:
                return original(*args, **kwargs)
            finally:
                row['ms'] = (time.perf_counter() - start) * 1000
                self.functions.append(row)

        setattr(module, name, timed)

    def report(self):
        return {'measurement': 'ASGI entry through final response body; excludes pre-entry queueing',
                'requests': self.requests, 'sessions': self.sessions, 'functions': self.functions}
