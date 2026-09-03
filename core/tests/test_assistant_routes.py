from __future__ import annotations

from pathlib import Path

from lab import assistant as assistant_db


def _seed(monkeypatch, tmp_path: Path, monorepo: Path) -> tuple[Path, Path]:
    root = tmp_path / "assistant-db"
    monkeypatch.setenv("LAB_ASSISTANT_HOME", str(root))
    assistant_db.initialize(root)
    project_path = monorepo / "projects" / "demo"
    project_path.mkdir(parents=True, exist_ok=True)
    assistant_db.create_project(
        root,
        "demo",
        name="Demo",
        workspace="local",
        workspace_path=monorepo,
        project_path=project_path,
    )
    task = assistant_db.create_task(
        root,
        "Write launch update",
        project_id="demo",
        priority="P0",
        status="in_progress",
    )
    return root, task


def test_assistant_unconfigured(client, monkeypatch) -> None:
    monkeypatch.delenv("LAB_ASSISTANT_HOME", raising=False)
    response = client.get("/api/assistant")
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_assistant_list_and_detail(client, monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    metadata, task_body = assistant_db.read_markdown(task)
    assistant_db.write_markdown(
        task,
        {**metadata, "group": "Launch operations", "tldr": "A concise launch TLDR."},
        task_body + "\n# Generate content\n\n![Launch thumbnail](chart.png)\n\nLaunch email.\n",
    )
    response = client.get("/api/assistant")
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["root"] == str(root)
    assert body["projects"][0]["id"] == "demo"
    assert body["tasks"][0]["title"] == "Write launch update"
    assert body["tasks"][0]["group"] == "Launch operations"
    assert body["tasks"][0]["tldr"] == "A concise launch TLDR."
    assert "body" not in body["tasks"][0]
    assert body["tasks"][0]["subtasks_total"] == 0
    assert body["tasks"][0]["subtasks_done"] == 0
    assert body["tasks"][0]["has_generated_content"] is True
    assert body["tasks"][0]["preview_image"] == {
        "alt": "Launch thumbnail",
        "src": "chart.png",
    }

    detail = client.get(
        "/api/assistant/task",
        params={"path": str(task.relative_to(root))},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["metadata"]["priority"] == "P0"
    assert detail.json()["subtasks"] == []
    assert "# Context" in detail.json()["body"]


def test_assistant_meeting_list_and_detail(client, monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    root, _task = _seed(monkeypatch, tmp_path, monorepo)
    meeting = assistant_db.create_meeting(
        root,
        "Weekly product review",
        project_id="demo",
        date="2026-09-03",
        attendees=["Maya", "Leo"],
    )
    metadata, body = assistant_db.read_markdown(meeting)
    assistant_db.write_markdown(
        meeting,
        metadata,
        body.replace("- [ ] Add a personal follow-up.", "- [x] Share experiment results."),
    )

    response = client.get("/api/assistant")
    assert response.status_code == 200, response.text
    row = response.json()["meetings"][0]
    assert row["title"] == "Weekly product review"
    assert row["action_items_total"] == 2
    assert row["action_items_done"] == 1
    assert "body" not in row

    detail = client.get(
        "/api/assistant/meeting",
        params={"path": str(meeting.relative_to(root))},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["metadata"]["attendees"] == ["Maya", "Leo"]
    assert "# Highlights" in detail.json()["body"]


def test_assistant_first_class_subtasks_are_summarized_and_have_detail(
    client, monkeypatch, tmp_path: Path, monorepo: Path,
) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    task_metadata, _ = assistant_db.read_markdown(task)
    subtask = assistant_db.create_subtask(
        root,
        "Review the generated announcement",
        parent=str(task_metadata["id"]),
        priority="P1",
        status="ready_to_review",
    )
    metadata, _ = assistant_db.read_markdown(subtask)
    assistant_db.write_markdown(
        subtask,
        metadata,
        "# Context\n\nThe agent drafted the announcement.\n\n# Generate content\n\nHello subscribers.\n",
    )

    response = client.get("/api/assistant")
    assert response.status_code == 200, response.text
    row = response.json()["tasks"][0]
    child = row["first_class_subtasks"][0]
    assert child["status"] == "ready_to_review"
    assert child["document_backed"] is True
    assert child["summary"] == "The agent drafted the announcement. Hello subscribers."
    assert child["tldr"] == child["summary"]
    assert child["has_generated_content"] is True
    assert "body" not in child
    assert "body" not in row["subtasks"][0]

    task_detail = client.get(
        "/api/assistant/task",
        params={"path": str(task.relative_to(root))},
    )
    assert task_detail.status_code == 200, task_detail.text
    assert task_detail.json()["subtasks"][0]["path"] == str(subtask.relative_to(root))
    assert task_detail.json()["subtasks"][0]["tldr"] == "The agent drafted the announcement. Hello subscribers."
    assert "body" not in task_detail.json()["subtasks"][0]

    detail = client.get(
        "/api/assistant/subtask",
        params={"path": str(subtask.relative_to(root))},
    )
    assert detail.status_code == 200, detail.text
    assert detail.json()["metadata"]["parent"] == task_metadata["id"]
    assert "# Generate content" in detail.json()["body"]


def test_assistant_asset_allows_mapped_project_file(
    client, monkeypatch, tmp_path: Path, monorepo: Path,
) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    image = monorepo / "projects" / "demo" / "chart.png"
    image.write_bytes(b"not-a-real-png")
    response = client.get(
        "/api/assistant/asset",
        params={"task": str(task.relative_to(root)), "src": str(image)},
    )
    assert response.status_code == 200, response.text
    assert response.content == b"not-a-real-png"


def test_assistant_task_path_rejects_traversal(client, monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    _seed(monkeypatch, tmp_path, monorepo)
    response = client.get("/api/assistant/task", params={"path": "../secret.md"})
    assert response.status_code == 400


def test_assistant_subtask_path_rejects_task_document(
    client, monkeypatch, tmp_path: Path, monorepo: Path,
) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    response = client.get(
        "/api/assistant/subtask",
        params={"path": str(task.relative_to(root))},
    )
    assert response.status_code == 400
