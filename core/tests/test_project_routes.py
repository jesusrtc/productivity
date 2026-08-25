import json
import subprocess
from pathlib import Path
from types import SimpleNamespace


def _request(root):
    return SimpleNamespace(
        app=SimpleNamespace(
            state=SimpleNamespace(index_cache=SimpleNamespace(root=root)),
        ),
    )


def test_list_projects_empty(client) -> None:
    r = client.get("/api/projects")
    assert r.status_code == 200
    assert r.json() == []


def test_list_projects_returns_index_slice(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/projects")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha", "beta"]


def test_list_projects_filter_by_status(client, seed_project, monorepo) -> None:
    alpha = seed_project("alpha")
    beta = seed_project("beta")
    data = json.loads((beta / "project.json").read_text())
    data["status"] = "archived"
    (beta / "project.json").write_text(json.dumps(data))

    r = client.get("/api/projects?status=active")
    ids = [p["id"] for p in r.json()]
    assert ids == ["alpha"]

    r = client.get("/api/projects?status=archived")
    ids = [p["id"] for p in r.json()]
    assert ids == ["beta"]


def test_get_single_project_returns_full_json(client, seed_project) -> None:
    seed_project("alpha", description="Alpha desc")
    r = client.get("/api/projects/alpha")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == "alpha"
    assert body["description"] == "Alpha desc"
    assert body["worktrees"] == []


def test_get_single_project_missing(client) -> None:
    r = client.get("/api/projects/nope")
    assert r.status_code == 404


def test_get_single_project_rejects_bad_id(client) -> None:
    r = client.get("/api/projects/..%2Fbad")
    assert r.status_code in {400, 404}


def test_get_project_tasks_empty(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/tasks")
    assert r.status_code == 200
    assert r.json() == {"next_id": 1, "tasks": []}


def test_get_project_tasks_reflects_on_disk(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "hi", "status": "todo", "priority": "P1",
                   "loe": None, "due": None, "tags": [], "labels": [],
                   "blocker": None, "notes_file": None,
                   "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None}],
    }))
    r = client.get("/api/projects/alpha/tasks")
    body = r.json()
    assert body["next_id"] == 2
    assert body["tasks"][0]["title"] == "hi"


def test_get_project_tasks_missing_project(client) -> None:
    r = client.get("/api/projects/nope/tasks")
    assert r.status_code == 404


def test_get_self_project_tasks_reads_framework_root(tmp_path, monkeypatch) -> None:
    from core.routes import project as project_routes

    workspace = tmp_path / "workspace"
    framework = tmp_path / "framework"
    (workspace / "content").mkdir(parents=True)
    (framework / "content").mkdir(parents=True)
    (workspace / "content" / ".self-tasks.json").write_text(json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "workspace task"}],
    }))
    (framework / "content" / ".self-tasks.json").write_text(json.dumps({
        "next_id": 2,
        "tasks": [{"id": 1, "title": "framework task"}],
    }))
    monkeypatch.setattr(project_routes.paths, "find_framework_root", lambda: framework)

    body = project_routes.get_project_tasks("__self__", _request(workspace))

    assert body["tasks"][0]["title"] == "framework task"


def test_list_project_docs(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# hello")
    (pdir / "notes" / "001-draft.md").write_text("# draft")
    (pdir / "assets").mkdir(exist_ok=True)
    (pdir / "assets" / "chart.png").write_bytes(b"\x89PNG")

    r = client.get("/api/projects/alpha/docs")
    assert r.status_code == 200
    files = r.json()
    paths_set = {f["path"] for f in files}
    assert "docs/one-pager.md" in paths_set
    assert "notes/001-draft.md" in paths_set
    assert "assets/chart.png" in paths_set


def test_list_project_docs_missing_project(client) -> None:
    r = client.get("/api/projects/nope/docs")
    assert r.status_code == 404


def test_get_project_file_text(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "docs" / "one-pager.md").write_text("# body")
    r = client.get("/api/projects/alpha/file?path=docs/one-pager.md")
    assert r.status_code == 200
    assert "# body" in r.text


def test_get_project_file_rejects_traversal(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=../beta.md")
    assert r.status_code == 400


def test_get_project_file_missing(client, seed_project) -> None:
    seed_project("alpha")
    r = client.get("/api/projects/alpha/file?path=notes/999.md")
    assert r.status_code == 404


def test_project_files_marks_symlinks(client, seed_project) -> None:
    pdir = seed_project("alpha")
    (pdir / "AGENTS.md").write_text("# canonical\n")
    (pdir / "CLAUDE.md").symlink_to("AGENTS.md")
    (pdir / "real-docs").mkdir()
    (pdir / "real-docs" / "note.md").write_text("# note\n")
    (pdir / "linked-docs").symlink_to("real-docs", target_is_directory=True)
    (pdir / ".claude").mkdir()
    (pdir / ".claude" / "skills").symlink_to("../real-docs", target_is_directory=True)

    r = client.get(f"/api/project-files?path={pdir}")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.json()}

    assert files["CLAUDE.md"]["is_symlink"] is True
    assert files["CLAUDE.md"]["symlink_target"] == "AGENTS.md"
    assert "is_symlink" not in files["AGENTS.md"]
    assert files["linked-docs"]["type"] == "dir"
    assert files["linked-docs"]["is_symlink"] is True
    assert files["linked-docs"]["symlink_target"] == "real-docs"
    assert files["linked-docs/note.md"]["type"] == "file"

    r = client.get(f"/api/project-files?path={pdir}&include_dotfiles=true")
    assert r.status_code == 200
    files = {f["path"]: f for f in r.json()}
    assert files[".claude/skills"]["type"] == "dir"
    assert files[".claude/skills"]["is_symlink"] is True
    assert files[".claude/skills"]["symlink_target"] == "../real-docs"


def test_project_entry_create_rename_and_delete(client, seed_project) -> None:
    pdir = seed_project("explorer")

    created = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "draft.md", "kind": "file",
    })
    assert created.status_code == 200
    assert (pdir / "docs" / "draft.md").is_file()

    folder = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "research", "kind": "folder",
    })
    assert folder.status_code == 200
    assert (pdir / "docs" / "research").is_dir()

    renamed = client.patch("/api/project-entry", json={
        "path": str(pdir), "entry": "docs/draft.md", "new_name": "notes.md",
    })
    assert renamed.status_code == 200
    assert renamed.json()["renamed_to"] == "docs/notes.md"
    assert not (pdir / "docs" / "draft.md").exists()
    assert (pdir / "docs" / "notes.md").is_file()

    deleted = client.request("DELETE", "/api/project-entry", json={
        "path": str(pdir), "entry": "docs/research",
    })
    assert deleted.status_code == 200
    assert not (pdir / "docs" / "research").exists()


def test_project_entry_rejects_traversal_and_collisions(client, seed_project) -> None:
    pdir = seed_project("explorer-safe")
    (pdir / "docs" / "kept.md").write_text("safe")

    traversal = client.request("DELETE", "/api/project-entry", json={
        "path": str(pdir), "entry": "../project.json",
    })
    assert traversal.status_code == 400

    bad_name = client.patch("/api/project-entry", json={
        "path": str(pdir), "entry": "docs/kept.md", "new_name": "../gone.md",
    })
    assert bad_name.status_code == 400

    collision = client.post("/api/project-entry", json={
        "path": str(pdir), "parent": "docs", "name": "kept.md", "kind": "file",
    })
    assert collision.status_code == 409
    assert (pdir / "docs" / "kept.md").read_text() == "safe"


def test_project_diff_file_and_git_history(client, seed_project, monorepo) -> None:
    pdir = seed_project("explorer-git")
    source = pdir / "docs" / "note.txt"
    source.write_text("before\n")
    subprocess.run(["git", "init"], cwd=monorepo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Lab Test"], cwd=monorepo, check=True)
    subprocess.run(["git", "config", "user.email", "lab@example.test"], cwd=monorepo, check=True)
    subprocess.run(["git", "add", "."], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "add note"], cwd=monorepo, check=True, capture_output=True)
    source.write_text("after\n")
    subprocess.run(["git", "add", str(source.relative_to(monorepo))], cwd=monorepo, check=True)
    subprocess.run(["git", "commit", "-m", "update note"], cwd=monorepo, check=True, capture_output=True)

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert history.status_code == 200
    commits = history.json()["commits"]
    assert [commit["message"] for commit in commits[:2]] == ["update note", "add note"]

    commit_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/note.txt", "sha": commits[0]["sha"],
    })
    assert commit_diff.status_code == 200
    parsed = commit_diff.json()["files"][0]
    assert parsed["additions"] == 1
    assert parsed["deletions"] == 1

    source.write_text("working tree\n")
    working_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert working_history.status_code == 200
    working = working_history.json()["commits"][0]
    assert working["sha"] == "WORKTREE"
    assert working["message"] == "Uncommitted changes"
    assert working["states"] == ["unstaged"]

    working_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/note.txt", "sha": "WORKTREE",
    })
    assert working_diff.status_code == 200
    working_parsed = working_diff.json()["files"][0]
    assert working_parsed["additions"] == 1
    assert working_parsed["deletions"] == 1

    subprocess.run(
        ["git", "add", str(source.relative_to(monorepo))],
        cwd=monorepo, check=True,
    )
    staged_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert staged_history.json()["commits"][0]["states"] == ["staged"]

    source.write_text("working over staged\n")
    mixed_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/note.txt",
    })
    assert mixed_history.json()["commits"][0]["states"] == ["staged", "unstaged"]

    untracked = pdir / "docs" / "new.txt"
    untracked.write_text("brand new\n")
    untracked_history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/new.txt",
    })
    assert untracked_history.status_code == 200
    assert untracked_history.json()["commits"][0]["states"] == ["untracked"]
    untracked_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir), "file": "docs/new.txt", "sha": "WORKTREE",
    })
    assert untracked_diff.status_code == 200
    assert untracked_diff.json()["files"][0]["additions"] == 1

    patch = pdir / "docs" / "change.diff"
    patch.write_text(subprocess.run(
        ["git", "show", "--format=", "--no-color", commits[0]["sha"]],
        cwd=monorepo, check=True, capture_output=True, text=True,
    ).stdout)
    rendered = client.get("/api/project-diff-file", params={
        "path": str(pdir), "file": "docs/change.diff",
    })
    assert rendered.status_code == 200
    assert rendered.json()["files"][0]["filename"].endswith("docs/note.txt")
    assert rendered.json()["files"][0]["additions"] == 1


def test_project_git_history_uses_nearest_nested_repository(
    client, seed_project, monorepo,
) -> None:
    pdir = seed_project("explorer-nested-git")
    subprocess.run(["git", "init"], cwd=monorepo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Outer Test"], cwd=monorepo, check=True)
    subprocess.run(
        ["git", "config", "user.email", "outer@example.test"],
        cwd=monorepo, check=True,
    )

    nested = pdir / "docs" / "nested-repo"
    nested.mkdir()
    source = nested / "inside.txt"
    source.write_text("nested before\n")
    subprocess.run(["git", "init"], cwd=nested, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Nested Test"], cwd=nested, check=True)
    subprocess.run(
        ["git", "config", "user.email", "nested@example.test"],
        cwd=nested, check=True,
    )
    subprocess.run(["git", "add", "inside.txt"], cwd=nested, check=True)
    subprocess.run(
        ["git", "commit", "-m", "nested initial"],
        cwd=nested, check=True, capture_output=True,
    )
    source.write_text("nested after\n")

    history = client.get("/api/project-entry/history", params={
        "path": str(pdir), "file": "docs/nested-repo/inside.txt",
    })
    assert history.status_code == 200
    body = history.json()
    assert Path(body["repo"]) == nested
    assert body["repo_file"] == "inside.txt"
    assert [item["message"] for item in body["commits"]] == [
        "Uncommitted changes", "nested initial",
    ]

    working_diff = client.get("/api/project-entry/history-diff", params={
        "path": str(pdir),
        "file": "docs/nested-repo/inside.txt",
        "sha": "WORKTREE",
    })
    assert working_diff.status_code == 200
    parsed = working_diff.json()["files"][0]
    assert parsed["filename"] == "inside.txt"
    assert parsed["additions"] == 1
    assert parsed["deletions"] == 1


def test_set_project_hold_with_duration(client, seed_project) -> None:
    pdir = seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={
        "duration": "2d",
        "reason": "PR review",
        "url": "https://example.com/pr/1",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["ok"] is True
    hold = body["hold"]
    assert hold["reason"] == "PR review"
    assert hold["url"] == "https://example.com/pr/1"
    assert hold["until"]  # non-empty ISO timestamp
    # Persisted to disk
    stored = json.loads((pdir / "project.json").read_text())
    assert stored["hold"]["reason"] == "PR review"


def test_set_project_hold_with_until_date(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"until": "2099-01-15"})
    assert r.status_code == 200
    hold = r.json()["hold"]
    assert hold["until"].startswith("2099-01-15")


def test_set_project_hold_requires_one_of_duration_or_until(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"reason": "x"})
    assert r.status_code == 400


def test_set_project_hold_rejects_both_duration_and_until(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={
        "duration": "2d", "until": "2099-01-15",
    })
    assert r.status_code == 400


def test_set_project_hold_rejects_bad_duration(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/hold", json={"duration": "2 weeks"})
    assert r.status_code == 400


def test_clear_project_hold(client, seed_project) -> None:
    pdir = seed_project("alpha")
    client.post("/api/projects/alpha/hold", json={"duration": "1d"})
    r = client.delete("/api/projects/alpha/hold")
    assert r.status_code == 200
    assert r.json() == {"ok": True}
    stored = json.loads((pdir / "project.json").read_text())
    assert stored["hold"] is None


def test_clear_project_hold_when_none(client, seed_project) -> None:
    seed_project("alpha")
    r = client.delete("/api/projects/alpha/hold")
    assert r.status_code == 200


def test_hold_missing_project(client) -> None:
    r = client.post("/api/projects/nope/hold", json={"duration": "1d"})
    assert r.status_code == 404


# ─── /api/project-mtime perf regression guard ──────────────────────────────
#
# Background: the 2s-interval poll from the client used to walk the entire
# monorepo (including .venv + repositories + .git) with rglob("*"), stalling
# the event loop for 20+ seconds per tick. The fix skips the same heavy
# subtrees /api/project-files already filters out and caps recursion depth.
# These tests plant those exact subtree shapes and assert the endpoint
# ignores them — protecting the performance contract, not just correctness.


def test_project_mtime_skips_venv_and_node_modules(monorepo, client, seed_project) -> None:
    """Plant a heavy .venv-like tree whose newest mtime is clearly AFTER
    any real project file. If project-mtime walks it, ``latest`` will
    pick up that timestamp. If the skip list works, it won't."""
    import os
    import time

    pdir = seed_project("heavy")
    # Real project file (older).
    doc = pdir / "docs" / "note.md"
    doc.write_text("hi")
    old_ts = time.time() - 10_000
    os.utime(doc, (old_ts, old_ts))

    # Plant a .venv with a much-newer file that MUST be skipped.
    venv = pdir / ".venv" / "lib" / "site-packages" / "foo"
    venv.mkdir(parents=True)
    tainted = venv / "tainted.py"
    tainted.write_text("x")
    future_ts = time.time() + 1_000_000
    os.utime(tainted, (future_ts, future_ts))

    # Also plant a node_modules with a tainted mtime.
    nm = pdir / "node_modules" / "pkg"
    nm.mkdir(parents=True)
    tainted2 = nm / "tainted.js"
    tainted2.write_text("x")
    os.utime(tainted2, (future_ts, future_ts))

    r = client.get(f"/api/project-mtime?path={pdir}")
    assert r.status_code == 200
    mt = r.json()["mtime"]
    # If the skip list works, mt reflects ``pdir`` itself + its children
    # but never the tainted .venv / node_modules files.
    assert mt < future_ts, (
        f"project-mtime walked a skipped subtree (mt={mt}, future={future_ts}). "
        f"Confirm SKIP_DIRS in api_project_mtime includes .venv + node_modules."
    )


def test_project_mtime_fast_on_large_tree(seed_project, client) -> None:
    """Explicit p95 budget (p95<500ms). Plant a few hundred files inside
    allowed subdirs — the walk should still be comfortably sub-second.
    Pre-fix this test wouldn't exist because the endpoint was >20s on
    the real monorepo; this guard prevents silent regression to the old
    ``rglob("*")`` behavior."""
    import time

    pdir = seed_project("bulk")
    # 200 real-shape files across 20 docs/ subfolders.
    for i in range(20):
        sub = pdir / "docs" / f"sub-{i}"
        sub.mkdir(parents=True)
        for j in range(10):
            (sub / f"note-{j}.md").write_text("x")

    samples: list[float] = []
    for _ in range(5):
        t0 = time.perf_counter()
        r = client.get(f"/api/project-mtime?path={pdir}")
        samples.append(time.perf_counter() - t0)
        assert r.status_code == 200
    # After discarding the warmup sample, p95 must be < 500ms. Observed
    # on a dev laptop: ~20ms. This budget is ~25× headroom.
    hot = sorted(samples[1:])
    p95 = hot[-1] if hot else 0.0
    assert p95 < 0.5, (
        f"project-mtime p95 = {p95*1000:.1f}ms exceeds 500ms budget. "
        f"Samples (ms): {[f'{s*1000:.1f}' for s in samples]}. "
        f"Check for reintroduced rglob / missing SKIP_DIRS."
    )


def test_project_mtime_depth_capped(seed_project, client) -> None:
    """Walk depth is capped so a pathological deeply-nested tree can't
    hang the endpoint. Plant 30-level-deep dirs and confirm we return
    without hanging — the cap is 5 levels below the project root, so
    files past that don't contribute but the walk also doesn't run away."""
    pdir = seed_project("deep")
    p = pdir
    for _ in range(30):
        p = p / "dir"
        p.mkdir()
    (p / "leaf.txt").write_text("x")

    r = client.get(f"/api/project-mtime?path={pdir}")
    assert r.status_code == 200
    assert "mtime" in r.json()
