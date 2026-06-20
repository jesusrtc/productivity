"""Latency-budget tests — assert p95 under explicit thresholds on the
hot paths.

All tests are ``@slow`` so ``pytest`` without ``-m slow`` skips them.
When a budget fails, the assertion message includes observed p50/p95/p99
so the operator can see *how* we regressed, not just that we did.

Budgets are calibrated for the dev laptop running ``make start``. They
are intentionally generous (≥2× what the path should cost on a quiet
box) so they don't flake on a busy CI. Where a budget turns out to be
unrealistic on this machine we document the observed baseline in a
constant rather than silently bumping the threshold.
"""
from __future__ import annotations

import os
import statistics
import time
from pathlib import Path
from typing import Callable

import pytest


pytestmark = pytest.mark.slow


def _time_ns(f: Callable[[], None]) -> int:
    t0 = time.perf_counter_ns()
    f()
    return time.perf_counter_ns() - t0


def _percentiles(samples_ns: list[int]) -> tuple[float, float, float]:
    """Return p50, p95, p99 in milliseconds."""
    ordered = sorted(samples_ns)
    n = len(ordered)

    def _pct(p: float) -> float:
        # Nearest-rank; for our sample sizes (≥20) this is stable.
        k = max(0, min(n - 1, int(round(p / 100.0 * (n - 1)))))
        return ordered[k] / 1e6  # ms

    return _pct(50), _pct(95), _pct(99)


def _assert_p95(samples_ns: list[int], budget_ms: float, *, name: str,
                warmup: int = 5) -> None:
    """Compute percentiles, format a helpful message, assert p95<budget.

    The first ``warmup`` samples are discarded (TestClient + ASGI has a
    per-session warm-up that dwarfs steady-state); the remainder feeds
    the percentile calculation.
    """
    hot = samples_ns[warmup:]
    assert len(hot) >= 15, f"{name}: need ≥15 post-warmup samples, got {len(hot)}"
    p50, p95, p99 = _percentiles(hot)
    msg = (f"{name}: p50={p50:.2f}ms p95={p95:.2f}ms p99={p99:.2f}ms "
           f"(budget p95<{budget_ms}ms, n={len(hot)})")
    print("\n  " + msg)
    assert p95 < budget_ms, msg


# ─── Hot-path HTTP endpoints ───────────────────────────────────────────────


class TestTermSessionsLatency:
    """``GET /api/term/sessions`` is polled from the UI every few seconds
    on every project tab. With mocked tmux (no subprocess spawn) it
    should be near-trivial. Budget: p95 < 20ms."""

    def test_list_sessions_budget(self, client, mock_tmux_alive, monkeypatch):
        from core.routes import term as term_route

        # Force an empty _tmux_list to isolate handler overhead from the
        # subprocess spawn cost (the real cost is measured in the real-
        # tmux test below).
        monkeypatch.setattr(term_route, "_tmux_list", lambda prefix: [])

        samples = [_time_ns(lambda: client.get("/api/term/sessions"))
                   for _ in range(30)]
        _assert_p95(samples, budget_ms=20.0, name="GET /api/term/sessions")


class TestClientLogPostLatency:
    """``POST /api/log/client`` 10-event batch p95 < 15ms. Includes
    Pydantic validation + file write on the rotating handler (buffered)."""

    def test_batch_post_budget(self, client, monkeypatch):
        # Reset + raise rate limit so the budget run doesn't self-throttle.
        from core.routes import log as log_route
        monkeypatch.setattr(log_route, "_rate_count", 0, raising=False)
        monkeypatch.setattr(log_route, "_rate_window_start", 0.0, raising=False)
        monkeypatch.setattr(log_route, "_RATE_LIMIT", 1_000_000, raising=False)

        payload = {"events": [
            {"level": "error", "msg": f"synth-{i}", "path": "/"}
            for i in range(10)
        ]}

        def _post():
            r = client.post("/api/log/client", json=payload)
            assert r.status_code == 200

        samples = [_time_ns(_post) for _ in range(30)]
        _assert_p95(samples, budget_ms=15.0, name="POST /api/log/client (10 ev)")


class TestPingLatency:
    """Ultra-minimal health check. If this budget fails, we have an
    instrumentation overhead issue somewhere in the middleware chain."""

    def test_ping_budget(self, client):
        samples = [_time_ns(lambda: client.get("/api/ping")) for _ in range(30)]
        _assert_p95(samples, budget_ms=10.0, name="GET /api/ping")


# ─── WebSocket handshake latency ───────────────────────────────────────────


class TestWSHandshakeLatency:
    """Time from ``websocket_connect`` entry to receiving the first frame
    on the no-session path. This is the only reliably-deterministic WS
    latency we can measure via TestClient; the PTY happy path requires a
    real tmux and its own per-session warm-up dominates.

    Budget: p95 < 50ms. The path is: ASGI upgrade → accept → run_in_executor
    for the has-session call → safe_send → close. Executor round-trip is
    the bulk of the cost on this box."""

    def test_ws_handshake_first_byte_budget(self, client, mock_tmux_dead):
        os.environ.setdefault("LAB_TMUX_PREFIX", "lab-")

        def _connect():
            with client.websocket_connect("/ws/term/lab-latency") as ws:
                frame = ws.receive_json()
                assert frame["reason"] == "no-session"

        samples = [_time_ns(_connect) for _ in range(25)]
        _assert_p95(samples, budget_ms=50.0,
                    name="WS /ws/term handshake → first frame")
