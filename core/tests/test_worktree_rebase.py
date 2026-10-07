"""Real owned Git repositories exercise worktree pull/rebase and retained work."""
from pathlib import Path
import subprocess

from fastapi import HTTPException
import pytest

from core import worktree_rebase


def git(root: Path, *args: str) -> str:
    proc = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=10)
    assert proc.returncode == 0, proc.stderr
    return proc.stdout.strip()


@pytest.fixture
def checkout(monorepo):
    remote = monorepo / "upstream.git"
    primary = monorepo / "project"
    tree = monorepo / "trees" / "feature"
    primary.mkdir(); remote.mkdir()
    git(remote, "init", "--bare", "--initial-branch=master")
    git(primary, "init", "--initial-branch=master")
    git(primary, "config", "user.name", "Worktree Test")
    git(primary, "config", "user.email", "worktree@example.invalid")
    git(primary, "config", "commit.gpgsign", "false")
    git(primary, "config", "rebase.updateRefs", "true")
    (primary / "shared.txt").write_text("base\n")
    (primary / "local.txt").write_text("saved\n")
    git(primary, "add", "."); git(primary, "commit", "-m", "Initial")
    git(primary, "remote", "add", "origin", str(remote))
    git(primary, "push", "-u", "origin", "master")
    git(primary, "worktree", "add", "-b", "feature/test", str(tree))
    (tree / "feature.txt").write_text("feature\n")
    git(tree, "add", "."); git(tree, "commit", "-m", "Feature work")
    git(primary, "branch", "untouched-feature", git(tree, "rev-parse", "HEAD"))
    return {"primary": primary, "tree": tree, "remote": remote}


def advance(checkout, *, conflict=False):
    primary = checkout["primary"]
    (primary / ("shared.txt" if conflict else "upstream.txt")).write_text("upstream\n")
    git(primary, "add", "."); git(primary, "commit", "-m", "New master work")
    git(primary, "push", "origin", "master")
    return git(primary, "rev-parse", "HEAD")


def post(client, checkout):
    return client.post("/api/git/worktree-pull-rebase", json={"path": str(checkout["tree"])})


def test_pull_rebases_feature_onto_fresh_remote_master_and_retains_local_edits(client, checkout):
    tree = checkout["tree"]
    original = git(tree, "rev-parse", "HEAD")
    (tree / "local.txt").write_text("unsaved tracked edit\n")
    (tree / "scratch.txt").write_text("untracked work\n")
    upstream = advance(checkout)
    response = post(client, checkout)
    assert response.status_code == 200, response.text
    result = response.json()
    assert result["status"] == "ok" and result["revision"] == upstream
    assert result["target"] == "origin/master" and result["branch"] == "feature/test"
    assert git(tree, "branch", "--show-current") == "feature/test"
    assert git(tree, "rev-parse", "HEAD^") == upstream
    assert git(tree, "rev-parse", "HEAD") != original
    assert git(tree, "rev-parse", "untouched-feature") == original
    assert git(checkout["primary"], "rev-parse", "HEAD") == upstream
    assert git(checkout["remote"], "rev-parse", "master") == upstream
    assert (tree / "feature.txt").read_text() == "feature\n"
    assert (tree / "local.txt").read_text() == "unsaved tracked edit\n"
    assert (tree / "scratch.txt").read_text() == "untracked work\n"
    assert not git(tree, "stash", "list")
    assert not result["rebase_paused"] and not result["conflicted_files"]


def test_conflicts_pause_rebase_and_abort_restores_original_work(client, checkout):
    tree = checkout["tree"]
    (tree / "shared.txt").write_text("feature change\n")
    git(tree, "add", "."); git(tree, "commit", "-m", "Conflicting feature")
    original = git(tree, "rev-parse", "HEAD")
    (tree / "local.txt").write_text("local unsaved work\n")
    advance(checkout, conflict=True)
    response = post(client, checkout)
    assert response.status_code == 409, response.text
    result = response.json()
    assert result["status"] == "conflict" and result["rebase_paused"]
    assert "shared.txt" in result["conflicted_files"]
    assert "CONFLICT" in result["output"]
    again = post(client, checkout)
    assert again.status_code == 409 and "already paused" in again.json()["detail"]
    git(tree, "rebase", "--abort")
    assert git(tree, "rev-parse", "HEAD") == original
    assert (tree / "local.txt").read_text() == "local unsaved work\n"
    assert (tree / "shared.txt").read_text() == "feature change\n"


def test_autostash_restore_conflicts_are_reported_even_when_git_returns_success(client, checkout):
    tree = checkout["tree"]
    (tree / "shared.txt").write_text("local unsaved edit\n")
    upstream = advance(checkout, conflict=True)
    response = post(client, checkout)
    assert response.status_code == 409, response.text
    result = response.json()
    assert result["status"] == "local_changes_conflict" and not result["rebase_paused"]
    assert result["conflicted_files"] == ["shared.txt"]
    assert git(tree, "rev-parse", "HEAD^") == upstream
    assert "autostash" in git(tree, "stash", "list")
    assert "local unsaved edit" in git(tree, "stash", "show", "-p")
    again = post(client, checkout)
    assert again.status_code == 409 and "unresolved file conflicts" in again.json()["detail"]


def test_missing_remote_master_does_not_rebase_or_switch_branches(client, checkout):
    tree = checkout["tree"]
    original = git(tree, "rev-parse", "HEAD")
    git(checkout["remote"], "symbolic-ref", "HEAD", "refs/heads/main")
    git(checkout["remote"], "branch", "-m", "master", "main")
    response = post(client, checkout)
    assert response.status_code == 409 and "master" in response.json()["detail"]
    assert git(tree, "rev-parse", "HEAD") == original
    assert git(tree, "branch", "--show-current") == "feature/test"


def test_primary_checkout_and_detached_worktree_are_rejected(client, checkout):
    response = client.post("/api/git/worktree-pull-rebase", json={"path": str(checkout["primary"])})
    assert response.status_code == 409 and "linked worktrees" in response.json()["detail"]
    git(checkout["tree"], "checkout", "--detach")
    response = post(client, checkout)
    assert response.status_code == 409 and "detached HEAD" in response.json()["detail"]


def test_concurrent_worktree_update_is_rejected_and_lock_is_released(client, checkout):
    common = (checkout["primary"] / ".git").resolve()
    worktree_rebase._ACTIVE.add(common)
    try:
        response = post(client, checkout)
        assert response.status_code == 409 and "already running" in response.json()["detail"]
    finally:
        worktree_rebase._ACTIVE.discard(common)
    assert post(client, checkout).status_code == 200
    assert not worktree_rebase._ACTIVE


def test_branch_change_during_fetch_prevents_rebase(client, checkout, monkeypatch):
    advance(checkout)
    run = worktree_rebase._git
    original = git(checkout["tree"], "rev-parse", "HEAD")
    def change_branch(root, args, **kwargs):
        proc = run(root, args, **kwargs)
        if args[0] == "fetch":
            git(root, "checkout", "-b", "different-branch")
        return proc
    monkeypatch.setattr(worktree_rebase, "_git", change_branch)
    response = post(client, checkout)
    assert response.status_code == 409 and "branch changed" in response.json()["detail"]
    assert git(checkout["tree"], "rev-parse", "HEAD") == original
    assert not worktree_rebase._ACTIVE


def test_fetch_timeout_releases_lock_without_rebasing(client, checkout, monkeypatch):
    run = worktree_rebase._git
    original = git(checkout["tree"], "rev-parse", "HEAD")
    def timeout(root, args, **kwargs):
        if args[0] == "fetch":
            raise HTTPException(status_code=504, detail="Git fetch timed out.")
        return run(root, args, **kwargs)
    monkeypatch.setattr(worktree_rebase, "_git", timeout)
    response = post(client, checkout)
    assert response.status_code == 504
    assert git(checkout["tree"], "rev-parse", "HEAD") == original
    assert not worktree_rebase._ACTIVE


def test_unapproved_path_is_rejected_before_git(client, tmp_path, monkeypatch):
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(worktree_rebase, "_git", lambda *a, **kw: pytest.fail("Unapproved path reached Git"))
    response = client.post("/api/git/worktree-pull-rebase", json={"path": str(outside)})
    assert response.status_code == 403


def test_action_requires_admin(client, checkout, monkeypatch):
    from core.routes import git as route
    def denied(request):
        raise HTTPException(status_code=403, detail="Admin required")
    monkeypatch.setattr(route.auth, "require_admin", denied)
    monkeypatch.setattr(worktree_rebase, "_git", lambda *a, **kw: pytest.fail("Unauthorized request reached Git"))
    assert post(client, checkout).status_code == 403
