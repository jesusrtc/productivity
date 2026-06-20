import json


def test_post_project_new_creates_on_disk(client, monorepo) -> None:
    r = client.post("/api/projects", json={
        "id": "alpha",
        "description": "Alpha description",
        "priority": "P1",
        "tags": ["x", "y"],
        "labels": [],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == "alpha"
    assert body["priority"] == "P1"

    on_disk = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert on_disk["description"] == "Alpha description"
    assert on_disk["tags"] == ["x", "y"]


def test_post_project_new_rejects_duplicate(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects", json={"id": "alpha"})
    assert r.status_code == 400
    assert "already exists" in r.json()["detail"].lower()


def test_post_project_new_rejects_bad_id(client) -> None:
    r = client.post("/api/projects", json={"id": "Bad ID!"})
    assert r.status_code == 400


def test_post_task_new(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/tasks", json={
        "project_id": "alpha",
        "title": "Draft",
        "priority": "P1",
        "tags": ["review"],
    })
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == 1
    assert body["title"] == "Draft"
    assert body["status"] == "todo"


def test_post_task_status_done(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "done"})
    assert r.status_code == 200, r.text
    assert r.json()["status"] == "done"
    assert r.json()["closed_at"] is not None


def test_post_task_status_blocked_requires_reason(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked"})
    assert r.status_code == 400

    r = client.post("/api/tasks/alpha/1/status", json={"status": "blocked", "reason": "waiting on x"})
    assert r.status_code == 200
    assert r.json()["blocker"] == "waiting on x"


def test_post_task_update_field(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/tasks", json={"project_id": "alpha", "title": "t", "priority": "P2"})
    r = client.post("/api/tasks/alpha/1/update", json={"field": "priority", "value": "P0"})
    assert r.status_code == 200
    assert r.json()["priority"] == "P0"


def test_post_pr(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/prs", json={
        "url": "https://example/pr/1", "mp": "lipy-davi", "title": "t", "status": "open",
    })
    assert r.status_code == 200, r.text
    assert r.json()["prs"][0]["url"] == "https://example/pr/1"


def test_delete_pr(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/projects/alpha/prs", json={"url": "https://example/1"})
    client.post("/api/projects/alpha/prs", json={"url": "https://example/2"})
    r = client.delete("/api/projects/alpha/prs/0")
    assert r.status_code == 200
    assert [p["url"] for p in r.json()["prs"]] == ["https://example/2"]


def test_post_artifact(client, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/artifacts", json={
        "url": "https://docs.google.com/x", "type": "google_doc", "title": "D",
    })
    assert r.status_code == 200
    arts = r.json()["artifacts"]
    assert len(arts) == 1
    assert arts[0]["type"] == "google_doc"


def test_delete_artifact(client, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/projects/alpha/artifacts", json={"url": "https://a"})
    r = client.delete("/api/projects/alpha/artifacts/1")
    assert r.status_code == 200
    assert r.json()["artifacts"] == []


# ─── tab_open persistence ────────────────────────────────────────────────


def test_post_tab_open_persists_to_project_json(client, monorepo, seed_project) -> None:
    seed_project("alpha")
    r = client.post("/api/projects/alpha/tab", json={"open": True})
    assert r.status_code == 200, r.text
    assert r.json()["tab_open"] is True

    on_disk = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert on_disk["tab_open"] is True


def test_post_tab_close_persists_to_project_json(client, monorepo, seed_project) -> None:
    seed_project("alpha")
    client.post("/api/projects/alpha/tab", json={"open": True})
    r = client.post("/api/projects/alpha/tab", json={"open": False})
    assert r.status_code == 200, r.text
    assert r.json()["tab_open"] is False

    on_disk = json.loads((monorepo / "projects" / "alpha" / "project.json").read_text())
    assert on_disk["tab_open"] is False


def test_post_tab_unknown_project_returns_404(client) -> None:
    r = client.post("/api/projects/nonexistent/tab", json={"open": True})
    assert r.status_code == 404


def test_repos_includes_tab_open_field(client, monorepo, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    client.post("/api/projects/alpha/tab", json={"open": True})
    r = client.get("/api/repos")
    assert r.status_code == 200
    by_name = {p["name"]: p for p in r.json() if p.get("is_project")}
    assert by_name["alpha"]["tab_open"] is True
    # beta never had tab_open written; defaults to False.
    assert by_name["beta"]["tab_open"] is False
