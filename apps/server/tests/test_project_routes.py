import json


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
