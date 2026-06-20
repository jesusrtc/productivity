from __future__ import annotations

import pytest

from lab.model import ModelError, Priority, Project, ProjectStatus


def test_project_status_enum_values() -> None:
    assert {s.value for s in ProjectStatus} == {"active", "paused", "done", "archived"}


def test_priority_enum_values() -> None:
    assert {p.value for p in Priority} == {"P0", "P1", "P2", "P3"}


def test_project_from_dict_roundtrip() -> None:
    data = {
        "id": "davi-vision",
        "name": "DAVI Vision",
        "description": "Reshape DAVI",
        "status": "active",
        "tags": ["davi"],
        "labels": ["lipy-davi"],
        "priority": "P1",
        "loe": 10,
        "due": "2026-05-01",
        "created": "2026-04-15",
        "updated": "2026-04-16",
        "worktrees": [],
        "prs": [],
        "artifacts": [],
        "references": [],
        "pinned": [],
        "hold": None,
        "agent": None,
        "model": None,
    }
    p = Project.from_dict(data)
    assert p.id == "davi-vision"
    assert p.status is ProjectStatus.active
    assert p.priority is Priority.P1
    assert p.to_dict() == data


def test_project_hold_roundtrip() -> None:
    data = {
        "id": "x", "name": "x", "status": "active",
        "hold": {
            "until": "2026-05-01T14:00:00-07:00",
            "reason": "PR review",
            "url": "https://example.com/pr/1",
            "set_at": "2026-04-20T09:00:00-07:00",
        },
    }
    p = Project.from_dict(data)
    assert p.hold is not None
    assert p.hold["until"] == "2026-05-01T14:00:00-07:00"
    assert p.to_dict()["hold"] == data["hold"]


def test_project_hold_requires_until() -> None:
    with pytest.raises(ModelError):
        Project.from_dict({"id": "x", "name": "x", "status": "active",
                           "hold": {"reason": "nope"}})


def test_project_hold_accepts_bare_date() -> None:
    p = Project.from_dict({"id": "x", "name": "x", "status": "active",
                           "hold": {"until": "2026-05-01"}})
    assert p.hold == {"until": "2026-05-01"}


def test_project_rejects_bad_status() -> None:
    data = {"id": "x", "name": "x", "status": "weird"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_priority() -> None:
    data = {"id": "x", "name": "x", "status": "active", "priority": "P9"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_due_format() -> None:
    data = {"id": "x", "name": "x", "status": "active", "due": "tomorrow"}
    with pytest.raises(ModelError):
        Project.from_dict(data)


def test_project_rejects_bad_id() -> None:
    with pytest.raises(ModelError):
        Project.from_dict({"id": "Bad ID!", "name": "x", "status": "active"})


def test_project_defaults_fill_missing_fields() -> None:
    p = Project.from_dict({"id": "x", "name": "x", "status": "active"})
    assert p.tags == []
    assert p.labels == []
    assert p.worktrees == []
    assert p.priority is None
    assert p.due is None


from lab.model import Task, TaskStatus


def test_task_status_enum_values() -> None:
    assert {s.value for s in TaskStatus} == {"todo", "in_progress", "blocked", "done"}


def test_task_from_dict_roundtrip() -> None:
    data = {
        "id": 2,
        "title": "Review",
        "status": "in_progress",
        "priority": "P1",
        "loe": 0.5,
        "due": "2026-04-20",
        "tags": ["review"],
        "labels": [],
        "blocker": None,
        "notes_file": "notes/002-review.md",
        "created": "2026-04-15",
        "updated": "2026-04-16",
        "closed_at": None,
    }
    t = Task.from_dict(data)
    assert t.id == 2
    assert t.status is TaskStatus.in_progress
    assert t.priority is Priority.P1
    assert t.to_dict() == data


def test_task_requires_priority() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": 1, "title": "x", "status": "todo"})


def test_task_rejects_negative_id() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": -1, "title": "x", "status": "todo", "priority": "P2"})


def test_task_rejects_empty_title() -> None:
    with pytest.raises(ModelError):
        Task.from_dict({"id": 1, "title": "", "status": "todo", "priority": "P2"})


def test_task_done_requires_closed_at_in_to_dict() -> None:
    # Storing a done task writes closed_at; model does not compute it — caller does.
    t = Task.from_dict({
        "id": 1, "title": "x", "status": "done", "priority": "P2",
        "closed_at": "2026-04-16T12:00:00-07:00",
    })
    assert t.closed_at == "2026-04-16T12:00:00-07:00"
