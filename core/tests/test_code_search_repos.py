"""Repository summaries remain complete, fresh and ordered while Git overlaps."""
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from threading import Event, Lock
from types import SimpleNamespace

import pytest

from core.routes import code_search


def request_for(root):
    return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(
        index_cache=SimpleNamespace(root=root),
    )))


def repository(root, name, *, worktree=False):
    path = root / "repositories" / name
    path.mkdir(parents=True)
    if worktree:
        (path / ".git").write_text("gitdir: /owned/fixture/worktree\n")
    else:
        (path / ".git").mkdir()
    return path


@pytest.fixture
def summary_pool(monkeypatch):
    # Same bound as production; terminate test-owned workers after each case.
    workers = code_search._REPO_SUMMARY_EXECUTOR._max_workers
    with ThreadPoolExecutor(max_workers=workers) as pool:
        monkeypatch.setattr(code_search, "_REPO_SUMMARY_EXECUTOR", pool)
        yield pool


def test_missing_and_empty_catalog_never_runs_git(tmp_path, monkeypatch):
    monkeypatch.setattr(code_search, "_repo_summary", lambda path: pytest.fail(str(path)))
    assert code_search.list_repos(request_for(tmp_path)) == []
    (tmp_path / "repositories").mkdir()
    (tmp_path / "repositories" / "notes").mkdir()
    (tmp_path / "repositories" / "file.txt").touch()
    repository(tmp_path, ".hidden")
    assert code_search.list_repos(request_for(tmp_path)) == []


def test_single_worktree_repository(tmp_path, monkeypatch, summary_pool):
    entry = repository(tmp_path, "one", worktree=True)
    monkeypatch.setattr(code_search, "_repo_summary", lambda path: {"path": str(path)})
    assert code_search.list_repos(request_for(tmp_path)) == [{"path": str(entry)}]


def test_out_of_order_completion_preserves_catalog_order(tmp_path, monkeypatch, summary_pool):
    for name in ("beta", "Alpha", "charlie"):
        repository(tmp_path, name)
    later_finished = Event()
    completed = []

    def summary(path):
        if path.name == "Alpha":
            assert later_finished.wait(2), "independent repositories did not overlap"
        else:
            completed.append(path.name)
            later_finished.set()
        return {"name": path.name}

    monkeypatch.setattr(code_search, "_repo_summary", summary)
    assert code_search.list_repos(request_for(tmp_path)) == [
        {"name": name} for name in ("Alpha", "beta", "charlie")
    ]
    assert completed


def test_concurrent_requests_share_worker_bound(tmp_path, monkeypatch, summary_pool):
    roots = [tmp_path / "single", tmp_path / "first", tmp_path / "second"]
    counts = [1, 12, 12]
    for root, count in zip(roots, counts):
        for number in range(count):
            repository(root, f"repo-{number:02}")
    release, full = Event(), Event()
    lock = Lock()
    active = maximum = calls = 0

    def summary(path):
        nonlocal active, maximum, calls
        with lock:
            active += 1
            maximum = max(maximum, active)
            calls += 1
            if active == 8:
                full.set()
        try:
            assert release.wait(3), "test did not release blocked Git reads"
            return {"name": path.name, "root": str(path.parent.parent)}
        finally:
            with lock:
                active -= 1

    monkeypatch.setattr(code_search, "_repo_summary", summary)
    with ThreadPoolExecutor(max_workers=3) as clients:
        requests = [clients.submit(code_search.list_repos, request_for(root)) for root in roots]
        try:
            assert full.wait(2), "the catalog did not overlap independent Git reads"
            assert all(not future.done() for future in requests)
            with lock:
                assert active == maximum == calls == 8
        finally:
            release.set()
        for root, count, future in zip(roots, counts, requests):
            assert future.result(timeout=3) == [
                {"name": f"repo-{number:02}", "root": str(root)} for number in range(count)
            ]
    assert active == 0 and maximum == 8 and calls == 25


def test_summaries_read_fresh_git_results_and_preserve_tabs(tmp_path, monkeypatch, summary_pool):
    repository(tmp_path, "normal")
    repository(tmp_path, "worktree", worktree=True)
    version = 1
    calls = []
    lock = Lock()

    def git_out(path, args, timeout=5):
        with lock:
            calls.append((path.name, tuple(args), timeout))
        if args[0] == "rev-parse":
            return f"branch-{version}-{path.name}"
        return f"abc{version}\tAuthor\ta@example.invalid\t1 minute ago\t2026-09-23T00:00:00Z\tcafé {version}\tcontinued"

    monkeypatch.setattr(code_search, "_git_out", git_out)
    for version in (1, 2):
        rows = code_search.list_repos(request_for(tmp_path))
        assert rows == [{
            "name": name, "branch": f"branch-{version}-{name}",
            "last": {"sha": f"abc{version}", "who": "Author", "email": "a@example.invalid",
                     "when": "1 minute ago", "when_iso": "2026-09-23T00:00:00Z",
                     "subj": f"café {version}\tcontinued"},
        } for name in ("normal", "worktree")]
    assert len(calls) == 8
    assert all(timeout == 5 for _, _, timeout in calls)


@pytest.mark.parametrize("branch,last", [("", ""), ("HEAD", "malformed"), ("feature", "a\tb\tc")])
def test_empty_detached_or_failed_git_preserves_fallback(monkeypatch, branch, last):
    monkeypatch.setattr(code_search, "_git_out", lambda path, args: branch if args[0] == "rev-parse" else last)
    assert code_search._repo_summary(Path("fixture")) == {
        "name": "fixture", "branch": branch or "HEAD", "last": {},
    }
