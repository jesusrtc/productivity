import os
from pathlib import Path
import subprocess

import pytest

from core import worktree_recent


def git(root, *args):
    return subprocess.check_output(
        ["git", "-C", str(root), *args], text=True, stderr=subprocess.DEVNULL,
    ).strip()


@pytest.fixture
def checkout(monorepo):
    source = monorepo / "source"
    source.mkdir()
    git(source, "init", "-b", "main")
    git(source, "config", "user.name", "Lab Test")
    git(source, "config", "user.email", "lab@example.test")
    (source / "docs").mkdir()
    for name in ["untouched.md", "edited.md", "committed.md", "saved.md"]:
        (source / "docs" / name).write_text("initial content\n")
    git(source, "add", ".")
    git(source, "commit", "-m", "initial")
    wrapper = monorepo / "branch-wrapper"
    tree = wrapper / "checkout"
    git(source, "worktree", "add", "-b", "feature", str(tree))
    return source, tree, wrapper


@pytest.mark.parametrize("scope", ["worktree", "subfolder", "wrapper"])
def test_initial_checkout_is_excluded_but_immediate_edits_and_commits_remain(client, checkout, scope):
    source, tree, wrapper = checkout
    initial, cutoff = worktree_recent.checkout_baseline(tree)
    # Make every mtime land in the checkout's last second, exercising the
    # ambiguity that a timestamp-only filter would incorrectly hide.
    for path in (tree / "docs").iterdir():
        os.utime(path, (cutoff - .5, cutoff - .5))
    (tree / "docs/edited.md").write_text("edited immediately\n")
    (tree / "docs/committed.md").write_text("committed before Lab first opens\n")
    (tree / "docs/new-committed.md").write_text("new and committed\n")
    git(tree, "add", "docs/committed.md", "docs/new-committed.md")
    git(tree, "commit", "-m", "work after creating the worktree")
    (tree / "docs/new.md").write_text("new untracked file\n")
    for path in (tree / "docs").iterdir():
        os.utime(path, (cutoff - .5, cutoff - .5))
    # A later save counts as recent even if its contents match the initial file.
    os.utime(tree / "docs/saved.md", (cutoff + 2, cutoff + 2))

    assert worktree_recent.checkout_baseline(tree) == (initial, cutoff)
    root = {"worktree": tree, "subfolder": tree / "docs", "wrapper": wrapper}[scope]
    response = client.get("/api/workspace-files", params={"path": str(root)})
    assert response.status_code == 200
    entries = {Path(row["path"]).name: row for row in response.json() if row["type"] == "file"}
    assert entries["untouched.md"]["checkout_generated"] is True
    assert entries["untouched.md"]["mtime"] == (tree / "docs/untouched.md").stat().st_mtime
    for name in ["edited.md", "committed.md", "new-committed.md", "new.md", "saved.md"]:
        assert not entries[name].get("checkout_generated"), name

    # The main checkout's ordinary mtimes retain their existing meaning.
    main = client.get("/api/workspace-files", params={"path": str(source)}).json()
    assert all("checkout_generated" not in row for row in main)


def test_initial_worktree_is_empty_until_a_file_changes(client, checkout):
    _, tree, _ = checkout
    first = client.get("/api/workspace-files", params={"path": str(tree)}).json()
    assert len(first) == 4
    assert all(row.get("checkout_generated") for row in first)
    (tree / "docs/edited.md").write_text("first edit\n")
    after = client.get("/api/workspace-files", params={"path": str(tree)}).json()
    assert [row["path"] for row in after if not row.get("checkout_generated")] == ["docs/edited.md"]


def test_reflog_reset_does_not_move_the_creation_baseline(checkout):
    _, tree, _ = checkout
    baseline = worktree_recent.checkout_baseline(tree)
    (tree / "docs/edited.md").write_text("commit\n")
    git(tree, "add", ".")
    git(tree, "commit", "-m", "later")
    git(tree, "reset", "--hard", "HEAD~1")
    assert worktree_recent.checkout_baseline(tree) == baseline


@pytest.mark.parametrize("problem", ["missing", "expired", "old"])
def test_unknown_or_old_creation_record_falls_back_to_normal_mtimes(client, checkout, monkeypatch, problem):
    _, tree, _ = checkout
    git_dir = Path(git(tree, "rev-parse", "--absolute-git-dir"))
    log = git_dir / "logs/HEAD"
    lines = log.read_bytes().splitlines(keepends=True)
    if problem == "missing":
        log.unlink()
    elif problem == "expired":
        log.write_bytes(lines[1])
    else:
        _, cutoff = worktree_recent.checkout_baseline(tree)
        monkeypatch.setattr(worktree_recent.time, "time", lambda: cutoff + 86401)
    assert worktree_recent.checkout_baseline(tree) is None
    rows = client.get("/api/workspace-files", params={"path": str(tree)}).json()
    assert all("checkout_generated" not in row for row in rows)


def test_detached_checkout_uses_initial_contents_when_git_omits_reset_record(client, checkout):
    source, _, wrapper = checkout
    tree = wrapper / "detached"
    git(source, "worktree", "add", "--detach", str(tree))
    initial = git(tree, "rev-parse", "HEAD")
    assert worktree_recent.checkout_baseline(tree) == (initial, None)
    (tree / "docs/edited.md").write_text("edited in detached worktree\n")
    (tree / "docs/committed.md").write_text("committed in detached worktree\n")
    git(tree, "add", "docs/committed.md")
    git(tree, "commit", "-m", "detached change")
    (tree / "docs/new.md").write_text("new file\n")
    assert worktree_recent.checkout_baseline(tree) == (initial, None)
    rows = client.get("/api/workspace-files", params={"path": str(tree)}).json()
    assert sorted(row["path"] for row in rows if not row.get("checkout_generated")) == [
        "docs/committed.md", "docs/edited.md", "docs/new.md",
    ]


def test_git_failure_keeps_files_visible(checkout, monkeypatch):
    _, tree, _ = checkout
    baseline = worktree_recent.checkout_baseline(tree)
    entry = {"mtime": (tree / "docs/untouched.md").stat().st_mtime}

    def unavailable(*args, **kwargs):
        raise subprocess.TimeoutExpired("git", 3)

    monkeypatch.setattr(worktree_recent.subprocess, "run", unavailable)
    worktree_recent.mark_checkout_files(tree, baseline, [("docs/untouched.md", entry)])
    assert "checkout_generated" not in entry
