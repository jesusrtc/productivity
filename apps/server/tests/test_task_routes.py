from __future__ import annotations

import json
from datetime import date, timedelta


def _task_entry(tid: int, **kwargs) -> dict:
    base = {
        "id": tid, "title": f"task-{tid}", "status": "todo", "priority": "P2",
        "loe": None, "due": None, "tags": [], "labels": [], "blocker": None,
        "notes_file": None, "created": "2026-04-17", "updated": "2026-04-17", "closed_at": None,
    }
    base.update(kwargs)
    return base


def _seed_tasks(pdir, tasks: list[dict]) -> None:
    (pdir / "tasks.json").write_text(json.dumps({"next_id": max(t["id"] for t in tasks) + 1,
                                                  "tasks": tasks}))


def test_list_tasks_empty(client) -> None:
    r = client.get("/api/tasks")
    assert r.status_code == 200
    assert r.json() == []


def test_list_tasks_flattens_across_projects(client, seed_project) -> None:
    a = seed_project("alpha")
    b = seed_project("beta")
    _seed_tasks(a, [_task_entry(1, title="in-alpha")])
    _seed_tasks(b, [_task_entry(1, title="in-beta")])
    r = client.get("/api/tasks")
    titles = [(t["project_id"], t["title"]) for t in r.json()]
    assert ("alpha", "in-alpha") in titles
    assert ("beta", "in-beta") in titles


def test_list_tasks_filter_by_status(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, status="todo", title="t"),
        _task_entry(2, status="done", title="d", closed_at="2026-04-17T09:00:00-07:00"),
    ])
    r = client.get("/api/tasks?status=done")
    assert [t["title"] for t in r.json()] == ["d"]

    r = client.get("/api/tasks?status=open")
    assert [t["title"] for t in r.json()] == ["t"]


def test_list_tasks_filter_by_priority(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, priority="P0"),
        _task_entry(2, priority="P1"),
        _task_entry(3, priority="P3"),
    ])
    r = client.get("/api/tasks?priority=P0,P1")
    assert {t["task_id"] for t in r.json()} == {1, 2}


def test_list_tasks_filter_by_tag_and_label(client, seed_project) -> None:
    a = seed_project("alpha")
    _seed_tasks(a, [
        _task_entry(1, tags=["review"]),
        _task_entry(2, labels=["lipy-davi"]),
        _task_entry(3),
    ])
    r = client.get("/api/tasks?tag=review")
    assert {t["task_id"] for t in r.json()} == {1}
    r = client.get("/api/tasks?label=lipy-davi")
    assert {t["task_id"] for t in r.json()} == {2}


def test_list_tasks_due(client, seed_project) -> None:
    a = seed_project("alpha")
    near = (date.today() + timedelta(days=3)).isoformat()
    far = (date.today() + timedelta(days=30)).isoformat()
    _seed_tasks(a, [
        _task_entry(1, due=near),
        _task_entry(2, due=far),
        _task_entry(3),
    ])
    r = client.get("/api/tasks/due?days=7")
    assert {t["task_id"] for t in r.json()} == {1}


def test_list_tasks_due_requires_positive_days(client) -> None:
    r = client.get("/api/tasks/due?days=0")
    assert r.status_code == 400 or r.status_code == 422
    r = client.get("/api/tasks/due?days=-1")
    assert r.status_code == 400 or r.status_code == 422
