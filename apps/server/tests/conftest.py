from __future__ import annotations

import asyncio
import gc
import json
import logging
import os
import resource
import sys
from pathlib import Path
from typing import Callable, Iterator

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def monorepo(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Minimal monorepo for backend tests. Mirrors lab's fixture."""
    root = tmp_path / "productivity"
    (root / "knowledge" / "projects").mkdir(parents=True)
    (root / "knowledge" / "meetings").mkdir()
    (root / ".git").mkdir()
    monkeypatch.setenv("LAB_ROOT", str(root))
    monkeypatch.chdir(root)
    return root


@pytest.fixture()
def seed_project(monorepo: Path):
    def _create(project_id: str = "demo", *, description: str = "") -> Path:
        pdir = monorepo / "knowledge" / "projects" / project_id
        pdir.mkdir(parents=True)
        (pdir / "project.json").write_text(json.dumps({
            "id": project_id,
            "name": project_id,
            "description": description,
            "status": "active",
            "tags": [],
            "labels": [],
            "priority": None,
            "loe": None,
            "due": None,
            "created": "2026-04-17",
            "updated": "2026-04-17",
            "worktrees": [],
            "prs": [],
            "artifacts": [],
            "pinned": [],
        }, indent=2))
        (pdir / "tasks.json").write_text(json.dumps({"next_id": 1, "tasks": []}, indent=2))
        (pdir / "docs").mkdir()
        (pdir / "notes").mkdir()
        return pdir
    return _create


class MaterializedClient:
    """Test client that synchronously rebuilds the index cache before each call.

    Production behavior is eventually-consistent — the watcher debounces real
    filesystem events by 250ms. Tests mutate the fixture monorepo synchronously
    and expect immediate reads, so this shim forces a cache rebuild before
    every HTTP / WS operation. The real watcher path is exercised by the
    end-to-end integration test (test_integration_e2e.py).
    """

    def __init__(self, inner: TestClient) -> None:
        self._inner = inner

    def _rebuild(self) -> None:
        cache = getattr(self._inner.app.state, "index_cache", None)
        if cache is not None:
            cache.rebuild()

    def get(self, *args, **kwargs):
        self._rebuild()
        return self._inner.get(*args, **kwargs)

    def post(self, *args, **kwargs):
        self._rebuild()
        return self._inner.post(*args, **kwargs)

    def put(self, *args, **kwargs):
        self._rebuild()
        return self._inner.put(*args, **kwargs)

    def patch(self, *args, **kwargs):
        self._rebuild()
        return self._inner.patch(*args, **kwargs)

    def delete(self, *args, **kwargs):
        self._rebuild()
        return self._inner.delete(*args, **kwargs)

    def websocket_connect(self, *args, **kwargs):
        self._rebuild()
        return self._inner.websocket_connect(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self._inner, name)


@pytest.fixture()
def client(monorepo: Path):
    """FastAPI TestClient pointed at the fixture monorepo."""
    # Ensure the `lab` CLI is discoverable by subprocess.run.
    venv_bin = Path(sys.executable).parent
    os.environ["PATH"] = f"{venv_bin}:{os.environ.get('PATH', '')}"

    from server.main import create_app
    app = create_app()
    with TestClient(app) as c:
        yield MaterializedClient(c)


# ─── Resource discipline ────────────────────────────────────────────────────
#
# A test that leaks file descriptors, asyncio tasks, or logging handlers is
# a bug waiting to happen under real load. These fixtures snapshot those
# counts before a test runs and diff at teardown so regressions fail loudly
# with a message that points straight at what leaked.

def _count_open_fds() -> int:
    """Best-effort open-fd count for the current process.

    Uses /dev/fd which is correct on Darwin + Linux (FreeBSD-style). The
    count includes the fds implicit in the listing itself; we return the
    raw number and let callers compare BEFORE vs AFTER rather than chasing
    an exact absolute value (which is noisy across Python versions).
    """
    try:
        return len(os.listdir("/dev/fd"))
    except OSError:  # pragma: no cover — /dev/fd missing on some platforms
        # Fallback: walk /proc/self/fd on Linux.
        try:
            return len(os.listdir(f"/proc/{os.getpid()}/fd"))
        except OSError:
            return -1  # signal "unknown"; callers should skip the assertion


def _count_running_tasks() -> int:
    """Number of asyncio tasks visible from any live event loop, or 0.

    When no loop is running (common at test teardown) we return 0 rather
    than crashing — this is the normal case for sync tests. The fixture
    only asserts *stability* across a test, so "both 0" is just as good
    a signal as "both N".
    """
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        return 0
    return len([t for t in asyncio.all_tasks(loop) if not t.done()])


def _count_root_log_handlers() -> int:
    return len(logging.getLogger().handlers)


@pytest.fixture()
def resource_snapshot() -> Iterator[Callable[[], None]]:
    """Snapshot open-fd / asyncio-task / root-logger-handler counts on
    entry; when the caller invokes the returned ``check()`` callable (or
    at fixture teardown), assert those counts are stable.

    Usage:
        def test_x(resource_snapshot):
            ...do work...
            resource_snapshot()  # explicit mid-test check, optional

    The final assertion runs at teardown. Encourage a final ``gc.collect()``
    before calling to drop cycles that would otherwise show as "leaked".
    """
    gc.collect()
    fds_before = _count_open_fds()
    tasks_before = _count_running_tasks()
    handlers_before = _count_root_log_handlers()
    # Also record RSS (kilobytes on macOS, bytes on Linux) as an FYI —
    # we don't assert on it (too noisy across test runs) but surface it
    # in failure messages so trends are visible.
    ru = resource.getrusage(resource.RUSAGE_SELF)
    rss_before = ru.ru_maxrss

    def check() -> None:
        gc.collect()
        fds_after = _count_open_fds()
        tasks_after = _count_running_tasks()
        handlers_after = _count_root_log_handlers()
        ru2 = resource.getrusage(resource.RUSAGE_SELF)
        rss_after = ru2.ru_maxrss
        msgs: list[str] = []
        # Allow small drift on fds (TestClient occasionally keeps a
        # connection-pool fd warm across a single test; +3 is generous
        # without hiding real leaks of dozens of fds per reconnect).
        if fds_before >= 0 and fds_after - fds_before > 3:
            msgs.append(f"FD leak: {fds_before} → {fds_after} (+{fds_after - fds_before})")
        if tasks_after > tasks_before:
            msgs.append(
                f"asyncio task leak: {tasks_before} → {tasks_after} "
                f"(+{tasks_after - tasks_before})"
            )
        if handlers_after != handlers_before:
            msgs.append(
                f"root-logger handler count changed: {handlers_before} → "
                f"{handlers_after} (Δ={handlers_after - handlers_before})"
            )
        if msgs:
            msgs.append(f"(RSS max {rss_before} → {rss_after})")
            raise AssertionError("resource leak detected:\n  " + "\n  ".join(msgs))

    yield check
    check()


@pytest.fixture()
def tmp_log_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect the server's RotatingFileHandler target to a per-test
    directory. The lifespan hook reads ``root / "logs"`` so we only need
    to set LAB_ROOT (already done by ``monorepo``) — this fixture is
    mainly a place to centralize the expected log path."""
    # Lifespan creates logs/ under LAB_ROOT; this just computes the path
    # so tests can locate the server.log file without hardcoding it.
    root = Path(os.environ.get("LAB_ROOT", tmp_path))
    log_dir = root / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    return log_dir


@pytest.fixture()
def mock_tmux_alive(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_tmux_has_session`` + ``_tmux_available`` to report a live
    session deterministically. Leaves subprocess calls elsewhere alone.

    Does NOT mock ``pty.fork`` — tests that exercise the PTY happy path
    should either spawn a real tmux (integration, @slow) or patch the
    fork chain explicitly. This fixture is for tests that only care about
    the pre-PTY guard path."""
    from server.routes import term as term_route

    monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
    monkeypatch.setattr(term_route, "_tmux_has_session", lambda name: True)
    return True


@pytest.fixture()
def mock_tmux_dead(monkeypatch: pytest.MonkeyPatch):
    """Patch ``_tmux_has_session`` to report no live session for every
    name (the exact condition that triggered the original crash)."""
    from server.routes import term as term_route

    monkeypatch.setattr(term_route, "_tmux_available", lambda: True)
    monkeypatch.setattr(term_route, "_tmux_has_session", lambda name: False)
    return False
