from __future__ import annotations

import time
from pathlib import Path

from core.state import IndexCache
from core.watcher import IndexWatcher


def test_watcher_debounces_bursts(monorepo: Path) -> None:
    """Rapid successive changes should trigger exactly one rebuild."""
    cache = IndexCache(monorepo)
    cache.rebuild()
    rebuild_count = {"n": 0}

    def on_rebuild(_data) -> None:
        rebuild_count["n"] += 1

    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=on_rebuild)
    w.start()
    try:
        target = monorepo / "projects" / ".probe"
        target.mkdir()
        for i in range(5):
            (target / f"f{i}.md").write_text("x")
            time.sleep(0.01)
        time.sleep(0.3)  # give debouncer time to fire
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
        time.sleep(0.3)
    finally:
        w.stop()

    assert len(events) == 1
    ids = [p["id"] for p in events[0]["projects"]]
    assert "late-comer" in ids


def test_watcher_stop_is_idempotent(monorepo: Path) -> None:
    cache = IndexCache(monorepo)
    w = IndexWatcher(monorepo, cache, debounce_ms=100, on_rebuild=lambda d: None)
    w.start()
    w.stop()
    w.stop()  # should not raise
