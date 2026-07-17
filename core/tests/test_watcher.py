from __future__ import annotations

import sys
import time
from pathlib import Path

from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler

from core.state import IndexCache
from core.watcher import IndexWatcher


def test_watcher_debounces_bursts(monorepo: Path) -> None:
    """Rapid successive changes should trigger exactly one rebuild."""
    cache = IndexCache(monorepo)
    cache.rebuild()
    rebuild_count = {"n": 0}

    def on_rebuild(_data) -> None:
        rebuild_count["n"] += 1

    # Debounce wider than the 50ms poll interval by a good margin: under
    # full-suite CPU load a delayed poll tick can deliver stragglers after a
    # 100ms window already fired, splitting the burst into two rebuilds.
    w = IndexWatcher(monorepo, cache, debounce_ms=300, on_rebuild=on_rebuild)
    w.start()
    try:
        target = monorepo / "projects" / ".probe"
        target.mkdir()
        for i in range(5):
            (target / f"f{i}.md").write_text("x")
            time.sleep(0.01)
        deadline = time.time() + 3.0
        while time.time() < deadline and rebuild_count["n"] == 0:
            time.sleep(0.05)
        time.sleep(0.7)  # quiet period: a second debounce fire would land here
    finally:
        w.stop()

    assert rebuild_count["n"] == 1


def test_watcher_rebuilds_on_project_creation(monorepo: Path, seed_project) -> None:
    cache = IndexCache(monorepo)
    cache.rebuild()
    events: list[dict] = []

    def on_rebuild(data) -> None:
        events.append(data)

    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=on_rebuild)
    w.start()
    try:
        seed_project("late-comer")
        # Deadline-based wait: under full-suite load the 50ms poll observer
        # plus the debounce can overshoot a fixed sleep, and the creation
        # burst can occasionally straddle two debounce windows. Exact
        # coalescing is asserted by test_watcher_debounces_bursts above.
        deadline = time.time() + 3.0
        while time.time() < deadline and not events:
            time.sleep(0.05)
    finally:
        w.stop()

    assert events, "watcher never rebuilt after project creation"
    ids = [p["id"] for p in events[-1]["projects"]]
    assert "late-comer" in ids


def test_project_watches_skip_arbitrary_worktree_dirs(monorepo: Path) -> None:
    """Project polling stays scoped to lab metadata/content, not whole worktrees."""
    project = monorepo / "projects" / "demo"
    (project / "docs").mkdir(parents=True)
    (project / "scripts").mkdir()
    (project / "worktree" / ".git").mkdir(parents=True)

    class FakeObserver:
        def __init__(self) -> None:
            self.scheduled: list[tuple[str, bool]] = []

        def schedule(self, _handler, path: str, *, recursive: bool = False):
            self.scheduled.append((str(Path(path)), recursive))

    observer = FakeObserver()
    cache = IndexCache(monorepo)
    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=lambda d: None)
    w._handler = FileSystemEventHandler()

    w._schedule_project_watches(observer)  # type: ignore[arg-type]

    scheduled = set(observer.scheduled)
    assert (str(monorepo / "projects"), False) in scheduled
    assert (str(project), False) in scheduled
    assert (str(project / "docs"), True) in scheduled
    assert (str(project / "scripts"), True) in scheduled
    assert (str(project / "worktree"), True) not in scheduled


def test_watcher_stop_is_idempotent(monorepo: Path) -> None:
    cache = IndexCache(monorepo)
    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=lambda d: None)
    w.start()
    w.stop()
    w.stop()  # should not raise


def test_watcher_defaults_to_polling_on_darwin(
    monorepo: Path, monkeypatch
) -> None:
    monkeypatch.delenv("LAB_WATCHER_OBSERVER", raising=False)
    monkeypatch.setattr(sys, "platform", "darwin")
    cache = IndexCache(monorepo)
    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=lambda d: None)

    observer = w._make_observer()

    assert isinstance(observer, PollingObserver)
