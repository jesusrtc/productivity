def test_get_index_empty(client) -> None:
    r = client.get("/api/index")
    assert r.status_code == 200
    body = r.json()
    assert body["projects"] == []
    assert body["tasks"] == []
    assert "generated_at" in body


def test_get_index_reflects_seeded_projects(client, seed_project) -> None:
    seed_project("alpha")
    seed_project("beta")
    r = client.get("/api/index")
    assert r.status_code == 200
    ids = [p["id"] for p in r.json()["projects"]]
    assert ids == ["alpha", "beta"]


def test_get_index_reflects_task_counts(client, seed_project) -> None:
    import json as _json
    pdir = seed_project("alpha")
    (pdir / "tasks.json").write_text(_json.dumps({
        "next_id": 3,
        "tasks": [
            {"id": 1, "title": "t", "status": "todo", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None},
            {"id": 2, "title": "u", "status": "done", "priority": "P1",
             "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
             "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17",
             "closed_at": "2026-04-17T09:00:00-07:00"},
        ],
    }))
    r = client.get("/api/index")
    p = r.json()["projects"][0]
    assert p["open_task_count"] == 1
    assert p["task_counts"]["done"] == 1
