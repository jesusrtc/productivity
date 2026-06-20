"""Client-robustness tests: WS lifecycle under adversarial client patterns.

These exercise the patterns a buggy or reconnecting browser produces —
tight reconnect storms, mid-handshake drops, and validate that nothing
leaks across them. Marked ``@slow`` because they are cycle-count-heavy
(tens of round-trips); use ``pytest -m slow`` to run.

We use the ``mock_tmux_dead`` fixture so the storm always takes the
no-session path — that was the ACTUAL crash path in production, and it
exercises the full accept → safe-send → close lifecycle without the
complexity of a real PTY. Real-tmux end-to-end coverage already exists
in ``test_term_routes.py`` (the session CRUD tests) and in the happy-path
``test_term_routes.py`` scenarios.
"""
from __future__ import annotations

import gc
import os
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi import WebSocketDisconnect
from starlette.websockets import WebSocketDisconnect as StarletteWSDisconnect


pytestmark = pytest.mark.slow


# ─── Rapid reconnect storm (the original crash repro) ───────────────────────


class TestReconnectStorm:
    """Hammer the WS endpoint with connect/disconnect cycles. Pre-fix each
    no-session close raced with the server's send_text and crashed. Post-
    fix all must close cleanly with a deterministic exit frame."""

    def test_many_no_session_connects_do_not_crash(self, client, mock_tmux_dead,
                                                     resource_snapshot):
        """50 consecutive no-session WS attempts. Post-fix every one
        produces the documented exit frame + clean close."""
        os.environ.setdefault("LAB_TMUX_PREFIX", "lab-")
        for i in range(50):
            with client.websocket_connect(f"/ws/term/lab-ghost-{i}") as ws:
                frame = ws.receive_json()
                assert frame == {"type": "exit", "reason": "no-session"}, \
                    f"iter {i}: unexpected frame {frame}"
        # resource_snapshot's check runs at teardown → asserts no fd /
        # task / handler leak across the storm.

    def test_fd_count_stable_across_storm(self, client, mock_tmux_dead):
        """Explicit fd-count assertion (in addition to the
        resource_snapshot fixture's implicit check) with a numeric
        budget: less than 5 fds of drift across 30 connect/disconnect
        cycles. A leak would have manifested as monotonic growth."""
        try:
            fds_before = len(os.listdir("/dev/fd"))
        except OSError:
            pytest.skip("/dev/fd unavailable")

        for i in range(30):
            with client.websocket_connect(f"/ws/term/lab-fd-{i}") as ws:
                frame = ws.receive_json()
                assert frame["reason"] == "no-session"
        gc.collect()

        try:
            fds_after = len(os.listdir("/dev/fd"))
        except OSError:
            pytest.skip("/dev/fd unavailable")
        drift = fds_after - fds_before
        assert drift < 5, f"fd drift of {drift} across 30 WS cycles suggests leak"

    def test_storm_keeps_http_responsive(self, client, mock_tmux_dead):
        """Interleave WS connects with HTTP requests. If a crash leaked a
        background error state or a fd-less reader task, /api/ping would
        start failing. All 50 iterations must return 200."""
        for i in range(25):
            with client.websocket_connect(f"/ws/term/lab-storm-{i}") as ws:
                ws.receive_json()
            r = client.get("/api/ping")
            assert r.status_code == 200, \
                f"HTTP broke on iter {i}: {r.status_code} {r.text!r}"


# ─── Server does not log ERROR on client-gone races ────────────────────────


class TestNoErrorLogsOnRace:
    """The entire point of ``_ws_send_text_safe`` is that a send-after-
    disconnect lands as DEBUG, not ERROR. If any of these storm tests
    surfaces an ERROR from our logger, we regressed."""

    def test_no_error_logs_across_storm(self, client, mock_tmux_dead, caplog):
        with caplog.at_level("ERROR"):
            for i in range(20):
                with client.websocket_connect(f"/ws/term/lab-err-{i}") as ws:
                    ws.receive_json()
        term_errors = [r for r in caplog.records
                       if r.name.startswith("server.term")
                       and r.levelno >= 40]  # ERROR
        assert not term_errors, \
            f"server.term ERROR logs surfaced: {[r.message for r in term_errors]}"


# ─── Concurrent WS connects from separate threads ──────────────────────────


class TestConcurrentConnects:
    """Multiple threads each opening/closing WS connections concurrently.
    TestClient is thread-safe for this pattern — each thread gets its
    own WebSocketTestSession. The server's handler must handle N parallel
    no-session closes without serializing or crashing."""

    def test_parallel_no_session_ok(self, client, mock_tmux_dead):
        def _one(i: int) -> str:
            with client.websocket_connect(f"/ws/term/lab-par-{i}") as ws:
                return ws.receive_json()["reason"]

        with ThreadPoolExecutor(max_workers=8) as pool:
            reasons = list(pool.map(_one, range(16)))
        assert all(r == "no-session" for r in reasons), reasons


# ─── Mid-handshake abandonment ─────────────────────────────────────────────


class TestAbandonMidHandshake:
    """Open the WS, do NOT read the no-session frame, just close. The
    server was sending its exit frame at that instant; post-fix the
    safe-send helpers swallow the race. This is the tightest repro of
    the production crash (client has already dropped when we send)."""

    def test_close_before_reading(self, client, mock_tmux_dead, caplog):
        with caplog.at_level("ERROR"):
            for i in range(30):
                # Enter the context but exit without receive_json() — the
                # TestClient WebSocketTestSession may still read the server's
                # initial frame during __enter__, but the server has
                # already sent + closed so the racy state is already past.
                # We rely on the storm cycle count to catch regressions
                # here rather than a single perfect repro.
                try:
                    with client.websocket_connect(f"/ws/term/lab-abandon-{i}"):
                        pass
                except (WebSocketDisconnect, StarletteWSDisconnect):
                    # Context entry can raise if the server closes before
                    # we yield — that's still a clean interaction.
                    pass
        term_errors = [r for r in caplog.records
                       if r.name.startswith("server.term")
                       and r.levelno >= 40]
        assert not term_errors, \
            f"abandon-midhandshake surfaced ERRORs: {[r.message for r in term_errors]}"
