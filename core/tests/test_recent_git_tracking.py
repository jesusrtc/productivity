"""Recently updated requires Git membership; Files still lists all files."""
from pathlib import Path
import subprocess

import pytest
from watchdog.events import FileModifiedEvent

from core import git_files, workspace_snapshot, workspace_index
from core.routes.diff import _collect_workspace_snapshot, _sidebar_git_recent_files
from .test_workspace_index import Hub


def git(root, *args):
    return subprocess.check_output(["git", "-C", str(root), *args], stderr=subprocess.DEVNULL).decode().strip()


def snapshot(root, index=None):
    progress = workspace_snapshot.Progress(str(root))
    view = index.begin(progress) if index else None
    progress.cache = view
    result = _collect_workspace_snapshot(root, True, progress)
    if view:
        view.commit()
    return result


@pytest.fixture
def repo(tmp_path):
    root = tmp_path / "project"
    root.mkdir()
    git(root, "init", "-b", "main")
    git(root, "config", "user.name", "Lab Test")
    git(root, "config", "user.email", "lab@example.test")
    (root / "docs").mkdir()
    (root / ".gitignore").write_text("*.log\nlogs/*\n!logs/keep.txt\n")
    for name in ["tracked.md", "with space.md", "with\nnewline.md", "forced.log"]:
        (root / "docs" / name).write_text("initial\n")
    git(root, "add", "-f", ".")
    git(root, "commit", "-m", "Initial")
    return root


@pytest.mark.parametrize("scope", ["project", "subfolder", "wrapper", "worktree"])
def test_only_tracked_nonignored_files_are_eligible_in_every_scope(tmp_path, repo, scope):
    root = repo
    if scope == "worktree":
        root = tmp_path / "trees/feature"
        git(repo, "worktree", "add", "-b", "feature", str(root))
    (root / "docs/untracked.md").write_text("new\n")
    (root / "docs/ignored.log").write_text("log\n")
    (root / "docs/staged.md").write_text("staged\n")
    git(root, "add", "docs/staged.md")
    for name in ["tracked.md", "forced.log"]:
        (root / "docs" / name).write_text("edited\n")
    visible = root / "docs" if scope == "subfolder" else tmp_path if scope == "wrapper" else root
    rows = {Path(row["path"]).name: row for row in snapshot(visible).files}
    for name in ["tracked.md", "staged.md", "with space.md", "with\nnewline.md"]:
        assert rows[name]["git_tracked"] is True
    for name in ["untracked.md", "ignored.log", "forced.log"]:
        assert rows[name]["git_tracked"] is False
    assert set(_sidebar_git_recent_files(str(root / "docs"), "uncommitted")["files"]) == {"tracked.md", "staged.md"}


def test_ignore_negation_repository_and_global_exclusions(tmp_path, repo):
    (repo / "logs").mkdir()
    (repo / "logs/keep.txt").write_text("kept\n")
    (repo / "logs/drop.txt").write_text("ignored\n")
    (repo / "private.txt").write_text("private\n")
    (repo / "global.txt").write_text("global\n")
    git(repo, "add", "-f", ".")
    (repo / ".git/info/exclude").write_text("private.txt\n")
    excludes = tmp_path / "ignore"
    excludes.write_text("global.txt\n")
    git(repo, "config", "core.excludesFile", str(excludes))
    tracked = git_files.tracked_paths(repo)
    assert "logs/keep.txt" in tracked
    assert not tracked.intersection({"logs/drop.txt", "private.txt", "global.txt", "docs/forced.log"})


def test_staging_and_ignore_changes_refresh_worktree_membership_without_mtime_change(tmp_path, repo):
    tree = tmp_path / "trees/feature"
    git(repo, "worktree", "add", "-b", "feature", str(tree))
    new = tree / "new.md"
    new.write_text("new\n")
    index = workspace_index.DirectoryIndex(tree, False, Hub())
    initial = snapshot(tree, index)
    before = new.stat().st_mtime_ns
    git(tree, "add", "new.md")
    metadata = Path(git(tree, "rev-parse", "--absolute-git-dir"))
    index.on_any_event(FileModifiedEvent(str(metadata / "index")))
    assert index.pending()[0]
    staged = snapshot(tree, index)
    assert staged.revision != initial.revision
    assert next(row for row in staged.files if row["path"] == "new.md")["git_tracked"] is True
    (tree / ".gitignore").write_text("new.md\n")
    index.on_any_event(FileModifiedEvent(str(tree / ".gitignore")))
    assert index.pending()[0]
    ignored = snapshot(tree, index)
    assert ignored.revision != staged.revision
    assert next(row for row in ignored.files if row["path"] == "new.md")["git_tracked"] is False
    assert new.stat().st_mtime_ns == before


def test_unborn_and_non_git_projects(tmp_path):
    (tmp_path / "new.md").write_text("new\n")
    assert snapshot(tmp_path).files[0]["git_tracked"] is False
    git(tmp_path, "init", "-b", "main")
    git(tmp_path, "add", "new.md")
    assert git_files.tracked_paths(tmp_path) == {"new.md"}
    assert _sidebar_git_recent_files(str(tmp_path), "uncommitted")["files"] == ["new.md"]
