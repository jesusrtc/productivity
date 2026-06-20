"""Resource-discipline tests — one dedicated home for the asserts the
``resource_snapshot`` fixture makes across the other suites.

The fixture itself is used as a teardown sanity-check sprinkled into
hot-path tests in the other files. The cases below **exercise it head-
on** to make sure a real leak would actually fail the fixture, and that
the fixture doesn't fire false positives on normal workloads.
"""
from __future__ import annotations

import asyncio
import gc
import logging
import os
from pathlib import Path

import pytest


# ─── The fixture itself ────────────────────────────────────────────────────


class TestResourceSnapshotFixture:
    """Guardrails: the fixture must (a) not false-positive on clean
    workloads, (b) actually catch planted leaks. If the fixture is
    broken we'd silently lose coverage across the whole suite."""

    def test_clean_workload_passes(self, client, resource_snapshot):
        # Just a couple of cheap hits; no fds / tasks / handlers added.
        client.get("/api/ping")
        client.get("/api/ping")
        # Teardown check runs automatically and should pass.

    def test_detects_handler_leak(self, resource_snapshot):
        """A leaked logging handler must trigger the assertion at
        teardown. We verify this by planting a leak then manually
        invoking the check() callable and expecting AssertionError."""
        root = logging.getLogger()
        leaked = logging.StreamHandler()
        root.addHandler(leaked)
        try:
            with pytest.raises(AssertionError, match="handler count"):
                resource_snapshot()
        finally:
            # Clean up so the fixture's own teardown doesn't fire too.
            root.removeHandler(leaked)

    def test_detects_fd_leak(self, resource_snapshot, tmp_path: Path):
        """Open a handful of fds without closing; the fixture should
        notice. We clean up after planting so the fixture's teardown
        doesn't re-fire."""
        paths = [tmp_path / f"leak-{i}" for i in range(10)]
        for p in paths:
            p.write_text("")
        fds = [os.open(str(p), os.O_RDONLY) for p in paths]
        try:
            with pytest.raises(AssertionError, match="FD leak"):
                resource_snapshot()
        finally:
            for fd in fds:
                os.close(fd)


# ─── Real-workload leak sweeps ─────────────────────────────────────────────


class TestNoLeaksInHotPaths:
    """Concrete regression guards: run known-sensitive code paths and
    assert the snapshot check passes. Complements the per-test
    ``resource_snapshot`` fixture by forcing a deliberate sweep of the
    paths we most recently touched."""

    def test_ws_no_session_cycle_clean(self, client, mock_tmux_dead,
                                        resource_snapshot):
        """The exact pattern that broke pre-fix. 20 iterations must
        leave no trace in fds / tasks / handlers."""
        for i in range(20):
            with client.websocket_connect(f"/ws/term/lab-rd-{i}") as ws:
                frame = ws.receive_json()
                assert frame["reason"] == "no-session"
        gc.collect()

    def test_log_ingest_cycle_clean(self, client, monkeypatch, resource_snapshot):
        from server.routes import log as log_route
        monkeypatch.setattr(log_route, "_rate_count", 0, raising=False)
        monkeypatch.setattr(log_route, "_rate_window_start", 0.0, raising=False)
        monkeypatch.setattr(log_route, "_RATE_LIMIT", 10_000, raising=False)

        for _ in range(30):
            r = client.post("/api/log/client", json={
                "events": [{"level": "error", "msg": "x"}]
            })
            assert r.status_code == 200
        gc.collect()


# ─── asyncio task hygiene inside term_ws ───────────────────────────────────


class TestNoLingeringTasks:
    """``term_ws`` spawns a ``reader_task`` (PTY pump) and now awaits it
    with ``await reader_task`` after cancelling. A regression that lost
    the await would surface as "Task was destroyed but it is pending!"
    warnings in the logs.

    We can't directly observe tasks running on the TestClient's inner
    loop (it's owned by the portal thread). Instead we drive a no-session
    storm and assert no "was destroyed but it is pending" warnings show
    up in captured output. This is a proxy but catches the common bug."""

    def test_no_pending_task_warnings(self, client, mock_tmux_dead, caplog):
        import warnings
        with warnings.catch_warnings(record=True) as captured:
            warnings.simplefilter("always")
            for i in range(20):
                with client.websocket_connect(f"/ws/term/lab-task-{i}") as ws:
                    ws.receive_json()
        bad = [w for w in captured
               if "pending" in str(w.message).lower()
               and "task" in str(w.message).lower()]
        assert not bad, f"pending-task warnings: {[str(w.message) for w in bad]}"
