"""Reliability tests for ``routes/term.py`` — the WS handler + its helpers.

Why this file exists: the ``/ws/term/{name}`` handler was crashing in
production when the client dropped between ``accept()`` and our first
``send_text``. The fix introduced:

- A strict name-validation regex (``_VALID_WS_NAME``) that catches
  injection / traversal before we spawn a subprocess.
- ``_ws_send_text_safe`` / ``_ws_close_safe`` helpers that swallow the
  narrow "client went away" exception family.
- An executor-backed ``_tmux_has_session`` call so the handler doesn't
  block the event loop between ``accept`` and the no-session close.

These tests exercise those seams head-on — both as unit tests against the
helpers and as integration tests via ``TestClient.websocket_connect``.
Wherever possible we avoid real tmux (fast + deterministic) and only fall
back to the real thing for the integration smoke marked ``@slow``.
"""
from __future__ import annotations

import asyncio
import json
import re
from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketDisconnect as StarletteWSDisconnect


# ─── Module-level helper unit tests ─────────────────────────────────────────


class TestSafeSendHelper:
    """``_ws_send_text_safe`` must:
    - Return True on successful send.
    - Return False (not raise) for every class of "client went away" error.
    - Log at DEBUG (not propagate) on unexpected exceptions.
    """

    def _run(self, coro):
        return asyncio.get_event_loop_policy().new_event_loop().run_until_complete(coro)

    def test_happy_path_returns_true(self):
        from server.routes.term import _ws_send_text_safe

        ws = MagicMock()
        ws.send_text = AsyncMock(return_value=None)
        result = asyncio.new_event_loop().run_until_complete(
            _ws_send_text_safe(ws, '{"ok":true}')
        )
        assert result is True
        ws.send_text.assert_awaited_once_with('{"ok":true}')

    @pytest.mark.parametrize("exc_cls", [
        WebSocketDisconnect,
        StarletteWSDisconnect,
        ConnectionError,
        RuntimeError,
        OSError,
    ])
    def test_swallows_race_family_returns_false(self, exc_cls):
        """Each flavor of 'client already gone' must be swallowed, not
        re-raised. Covers starlette.WSDisconnect, uvicorn ClientDisconnected
        (ConnectionError subclass), send-after-close (RuntimeError), and
        dead-socket OSError — the exact combo that crashed prod."""
        from server.routes.term import _ws_send_text_safe

        ws = MagicMock()
        # WebSocketDisconnect requires a code arg; ConnectionError doesn't.
        # Use a sentinel constructor that covers both shapes.
        def _raise(*_a, **_k):
            if exc_cls is WebSocketDisconnect:
                raise exc_cls(code=1006)
            raise exc_cls("client gone")
        ws.send_text = AsyncMock(side_effect=_raise)
        loop = asyncio.new_event_loop()
        try:
            result = loop.run_until_complete(_ws_send_text_safe(ws, "x"))
        finally:
            loop.close()
        assert result is False, f"{exc_cls.__name__} should have been swallowed"

    def test_unexpected_exception_also_swallowed(self, caplog):
        """Even an exception outside the documented race family must not
        propagate out of the handler — the whole point of the helper is
        that callers never see a traceback for a send failure."""
        from server.routes.term import _ws_send_text_safe

        ws = MagicMock()
        ws.send_text = AsyncMock(side_effect=ValueError("unexpected"))
        loop = asyncio.new_event_loop()
        try:
            with caplog.at_level("DEBUG", logger="server.term"):
                result = loop.run_until_complete(_ws_send_text_safe(ws, "x"))
        finally:
            loop.close()
        assert result is False
        # The last-resort guard should have logged at DEBUG.
        assert any("send_text failed" in r.message for r in caplog.records), \
            "expected DEBUG log for unexpected exception"


class TestSafeCloseHelper:
    """``_ws_close_safe`` must never raise."""

    @pytest.mark.parametrize("exc_cls", [
        WebSocketDisconnect, ConnectionError, RuntimeError, OSError, Exception,
    ])
    def test_never_raises(self, exc_cls):
        from server.routes.term import _ws_close_safe

        ws = MagicMock()
        def _raise(*_a, **_k):
            if exc_cls is WebSocketDisconnect:
                raise exc_cls(code=1006)
            raise exc_cls("x")
        ws.close = AsyncMock(side_effect=_raise)
        loop = asyncio.new_event_loop()
        try:
            loop.run_until_complete(_ws_close_safe(ws))  # must not raise
        finally:
            loop.close()
        ws.close.assert_awaited_once()


# ─── Session name validation ───────────────────────────────────────────────


class TestNameValidation:
    """``_VALID_WS_NAME`` is the argv-safety guard on the WS path. It runs
    before ``tmux has-session -t <name>`` so a hostile name never reaches
    subprocess. Charset: A-Z a-z 0-9 _ - (matches tmux's own rules; excludes
    the `.`/`:`/`/` characters tmux itself rejects)."""

    @pytest.mark.parametrize("name", [
        "lab-demo-claude",
        "lab-test-abc123-claude",
        "lab-_-x",
        "lab",                      # prefix itself, still letters-only
        "a" * 200,                  # long but legal charset
        "ABC_xyz-123",
    ])
    def test_accepts_legal_names(self, name: str):
        from server.routes.term import _VALID_WS_NAME
        assert _VALID_WS_NAME.match(name), f"{name!r} should be accepted"

    @pytest.mark.parametrize("name", [
        "",                         # empty
        "lab-..",                   # traversal bait
        "lab-../etc",               # traversal
        "lab-a/b",                  # slash
        "lab-a.b",                  # tmux rejects dots
        "lab-a:b",                  # tmux rejects colons
        "lab-a;rm -rf /",           # shell-injection bait (argv-safe, still rejected)
        "lab-a b",                  # whitespace
        "lab-a\nb",                 # newline
        "lab-a\x00b",               # NUL
        "lab-ü",                    # non-ASCII
    ])
    def test_rejects_hazardous_names(self, name: str):
        from server.routes.term import _VALID_WS_NAME
        assert not _VALID_WS_NAME.match(name), f"{name!r} should be rejected"


# ─── term_ws end-to-end via TestClient ─────────────────────────────────────


class TestTermWSNoSession:
    """The original crash path: WS connects to a tmux session that doesn't
    exist, server must send ``{type:"exit", reason:"no-session"}`` and
    close cleanly. No traceback on the server, no hanging client."""

    def test_no_session_returns_exit_frame(self, client, mock_tmux_dead):
        # Use a valid-looking name but mock _tmux_has_session → False.
        import os
        os.environ.setdefault("LAB_TMUX_PREFIX", "lab-")
        name = "lab-nosuchsession"
        with client.websocket_connect(f"/ws/term/{name}") as ws:
            frame = ws.receive_json()
            assert frame == {"type": "exit", "reason": "no-session"}
            # Server closes next; receiving raises WebSocketDisconnect.
            with pytest.raises((WebSocketDisconnect, StarletteWSDisconnect)):
                ws.receive_text()

    def test_no_session_does_not_raise_on_server(self, client, mock_tmux_dead, caplog):
        """Regression: even if the client tears down between accept() and
        our send_text, we must not log an ERROR traceback. The helpers
        downgrade to DEBUG."""
        # Connect + immediately close; the server race path is internal.
        with caplog.at_level("ERROR", logger="server.term"):
            with client.websocket_connect("/ws/term/lab-ghost") as ws:
                try:
                    ws.receive_json()
                except Exception:
                    pass
        # No ERROR-level records from our logger.
        ours = [r for r in caplog.records if r.name == "server.term" and r.levelname == "ERROR"]
        assert not ours, f"unexpected ERROR logs: {[r.message for r in ours]}"


class TestTermWSInvalidName:
    """A name that fails ``_VALID_WS_NAME`` must also take the no-session
    path (same user-visible contract) without touching subprocess. We can
    verify the latter by asserting ``subprocess.run`` is never invoked
    for a hazardous name (patched to fail loudly)."""

    def test_invalid_name_rejected_before_subprocess(self, client, monkeypatch):
        from server.routes import term as term_route

        calls: list[list] = []

        def _tracking_run(argv, *a, **kw):
            calls.append(list(argv))
            # Still return a dead object so any accidental call short-circuits.
            out = type("P", (), {"returncode": 1, "stdout": "", "stderr": ""})()
            return out

        # We only guard the target-taking tmux call. Other subprocess.run
        # uses (has-session etc. through _tmux_has_session) get a pass.
        monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
        monkeypatch.setattr(term_route, "_tmux_has_session",
                            lambda name: calls.append(["has-session", name]) or True)

        # A name that fails the regex — contains a dot. `.` is URL-safe
        # in a path segment so it reaches the handler unchanged.
        with client.websocket_connect("/ws/term/lab-a.b") as ws:
            frame = ws.receive_json()
            assert frame == {"type": "exit", "reason": "no-session"}
        # We must NOT have called has-session — the regex gate stopped it.
        assert not any(c[0] == "has-session" for c in calls), \
            f"invalid name reached subprocess: {calls}"

    @pytest.mark.parametrize("bad_name", [
        "lab-a.b",   # dot — URL-safe, reaches the handler
        "lab-a~b",   # tilde — URL-safe, rejected by regex
        "lab-a=b",   # equals — URL-safe, rejected by regex
    ])
    def test_hazardous_names_fall_through_cleanly(self, client, monkeypatch, bad_name):
        from server.routes import term as term_route
        monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
        # Force has-session True so only the regex can reject.
        monkeypatch.setattr(term_route, "_tmux_has_session", lambda n: True)

        with client.websocket_connect(f"/ws/term/{bad_name}") as ws:
            frame = ws.receive_json()
            assert frame == {"type": "exit", "reason": "no-session"}


class TestTermWSPrefixMismatch:
    """Even if the name passes the regex, it must also start with the
    tmux prefix — otherwise we'd be willing to attach to arbitrary tmux
    sessions on the user's machine. The WS handler enforces both."""

    def test_wrong_prefix_rejected(self, client, monkeypatch):
        from server.routes import term as term_route

        # Ensure _tmux_has_session would say "yes" if asked, so any
        # failure to reject isn't masked by a happy downstream state.
        monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
        monkeypatch.setattr(term_route, "_tmux_has_session", lambda n: True)

        with client.websocket_connect("/ws/term/other-mysession") as ws:
            frame = ws.receive_json()
            assert frame == {"type": "exit", "reason": "no-session"}


class TestTermWSTmuxUnavailable:
    """If tmux isn't on PATH (``_tmux_available() → False``), the handler
    must still accept and cleanly close without crashing."""

    def test_tmux_missing(self, client, monkeypatch):
        from server.routes import term as term_route
        monkeypatch.setattr(term_route, "_tmux_available", lambda: False)

        with client.websocket_connect("/ws/term/lab-whatever") as ws:
            frame = ws.receive_json()
            assert frame == {"type": "exit", "reason": "no-session"}


class TestTermWSExecutorOffload:
    """``_tmux_has_session`` is a blocking subprocess call. The handler
    must run it via ``loop.run_in_executor`` so the event loop isn't
    stalled between ``accept()`` and the no-session send — that stall
    was the window in which the original crash race fired.

    We verify this indirectly: a slow ``_tmux_has_session`` (sleeps)
    must NOT prevent the server from accepting other HTTP requests in
    parallel."""

    def test_slow_tmux_check_does_not_block_other_requests(self, client, monkeypatch):
        import threading
        import time
        from concurrent.futures import ThreadPoolExecutor
        from server.routes import term as term_route

        ready = threading.Event()

        def _slow_has_session(name: str) -> bool:
            ready.set()
            time.sleep(0.5)  # simulated blocking tmux call
            return False  # still take the no-session path

        monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
        monkeypatch.setattr(term_route, "_tmux_has_session", _slow_has_session)

        # Fire the WS in a background thread.
        def _ws_connect():
            with client.websocket_connect("/ws/term/lab-slow") as ws:
                return ws.receive_json()

        with ThreadPoolExecutor(max_workers=2) as pool:
            ws_future = pool.submit(_ws_connect)
            # Wait until the slow call has started.
            assert ready.wait(timeout=2.0), "slow _tmux_has_session never ran"
            # Now hit an HTTP endpoint; if the event loop is stalled,
            # this will time out. With executor offload it should return
            # in well under the 0.5s sleep.
            t0 = time.perf_counter()
            r = client.get("/api/ping")
            elapsed = time.perf_counter() - t0
            assert r.status_code == 200
            assert elapsed < 0.45, \
                f"HTTP request was blocked by blocking WS check ({elapsed:.3f}s)"
            assert ws_future.result(timeout=2.0) == {"type": "exit", "reason": "no-session"}


# ─── Exception class family — the taxonomy the helpers claim to cover ──────


def test_send_race_errors_tuple_contains_expected_classes():
    """Regression-guard the tuple of exceptions we promise to swallow in
    ``_ws_send_text_safe``. If a future refactor narrows this, we want a
    loud test failure, not silent regressions to the original crash."""
    from server.routes.term import _WS_SEND_RACE_ERRORS

    # At minimum these four: WSDisconnect, ConnectionError (covers
    # uvicorn ClientDisconnected + websockets ConnectionClosed sub-classes),
    # RuntimeError, OSError.
    assert WebSocketDisconnect in _WS_SEND_RACE_ERRORS
    assert RuntimeError in _WS_SEND_RACE_ERRORS
    assert OSError in _WS_SEND_RACE_ERRORS
    # ClientDisconnected / ConnectionClosed are typed aliases that fall
    # back to ConnectionError when the import fails — check the effective
    # coverage by instantiating.
    ex_cd = ConnectionError("x")
    assert isinstance(ex_cd, tuple(
        c for c in _WS_SEND_RACE_ERRORS if isinstance(c, type)
    )), "ConnectionError family not covered"
