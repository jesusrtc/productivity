from __future__ import annotations

from pathlib import Path

import pytest

from lab import assistant as assistant_db


def _seed(monkeypatch, tmp_path: Path, monorepo: Path) -> tuple[Path, Path]:
    root = tmp_path / "assistant-db"
    monkeypatch.setenv("LAB_ASSISTANT_HOME", str(root))
    assistant_db.initialize(root)
    workspace_path = monorepo / "workspaces" / "demo"
    workspace_path.mkdir(parents=True, exist_ok=True)
    assistant_db.create_workspace(
        root,
        "demo",
        name="Demo",
        vault="local",
        vault_path=monorepo,
        workspace_path=workspace_path,
    )
    task = assistant_db.create_task(
        root,
        "Write launch update",
        workspace_id="demo",
        priority="P0",
        status="in_progress",
    )
    return root, task


def test_assistant_unconfigured(client, monkeypatch) -> None:
    monkeypatch.delenv("LAB_ASSISTANT_HOME", raising=False)
    response = client.get("/api/assistant")
    assert response.status_code == 200
    assert response.json()["configured"] is False


def test_assistant_folder_can_be_configured_and_initialized_from_home(
    client, monkeypatch, tmp_path: Path,
) -> None:
    target = tmp_path / "selected-assistant"
    env_file = tmp_path / "client.env"
    monkeypatch.delenv("LAB_ASSISTANT_HOME", raising=False)
    monkeypatch.setenv("LAB_ENV_FILE", str(env_file))
    monkeypatch.setattr(assistant_db.paths, "find_framework_root", lambda: tmp_path / "framework")

    response = client.put(
        "/api/assistant/config",
        json={"path": str(target), "create": True},
    )

    assert response.status_code == 200, response.text
    assert response.json()["root"] == str(target.resolve())
    assert response.json()["initialized"] is True
    assert (target / "AGENTS.md").is_file()
    assert (target / "README.md").is_file()
    assert f'LAB_ASSISTANT_HOME="{target.resolve()}"' in env_file.read_text(encoding="utf-8")
    assert client.get("/api/assistant").json()["root"] == str(target.resolve())
    files = client.get("/api/workspace-files", params={"path": str(target)})
    assert files.status_code == 200, files.text
    assert {row["path"] for row in files.json()} >= {"AGENTS.md", "README.md"}
    created = client.post(
        "/api/workspace-entry",
        json={"path": str(target), "parent": "", "name": "notes.md", "kind": "file"},
    )
    assert created.status_code == 200, created.text
    assert (target / "notes.md").is_file()


def test_assistant_folder_rejects_framework_checkout(client, monkeypatch) -> None:
    monkeypatch.delenv("LAB_ASSISTANT_HOME", raising=False)
    framework = Path(__file__).resolve().parents[2]
    response = client.put(
        "/api/assistant/config",
        json={"path": str(framework), "create": True},
    )
    assert response.status_code == 400
    assert "outside the Lab framework" in response.json()["detail"]


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
    assert body["workspaces"][0]["id"] == "demo"
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
    assert detail.json()["body"] == assistant_db.read_markdown(task)[1]


def test_assistant_meeting_list_and_detail(client, monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    root, _task = _seed(monkeypatch, tmp_path, monorepo)
    meeting = assistant_db.create_meeting(
        root,
        "Weekly product review",
        workspace_id="demo",
        date="2026-09-03",
        attendees=["Maya", "Leo"],
    )
    metadata, body = assistant_db.read_markdown(meeting)
    assistant_db.write_markdown(
        meeting,
        metadata,
        body + "\n# Action items\n\n- [x] Share experiment results.\n- [ ] Prepare next review.\n",
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
    assert detail.json()["body"] == assistant_db.read_markdown(meeting)[1]


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


def test_assistant_asset_allows_mapped_workspace_file(
    client, monkeypatch, tmp_path: Path, monorepo: Path,
) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    image = monorepo / "workspaces" / "demo" / "chart.png"
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


def test_cross_workspace_subtask_is_in_parent_list_and_document(
    client, monkeypatch, tmp_path: Path, monorepo: Path,
) -> None:
    root, task = _seed(monkeypatch, tmp_path, monorepo)
    other_path = monorepo / "workspaces" / "video"
    other_path.mkdir(parents=True)
    assistant_db.create_workspace(root, "video", name="Video", vault="local",
                                vault_path=monorepo, workspace_path=other_path)
    metadata, _ = assistant_db.read_markdown(task)
    child = assistant_db.create_subtask(root, "Record explainer", parent=metadata["id"], workspace="video")
    listed = client.get("/api/assistant").json()["tasks"][0]
    assert listed["subtasks_total"] == 1
    assert listed["subtasks"][0]["workspace"] == "video"
    detail = client.get("/api/assistant/task", params={"path": str(task.relative_to(root))})
    assert detail.status_code == 200
    assert detail.json()["subtasks"][0]["path"] == str(child.relative_to(root))
    child_detail = client.get("/api/assistant/subtask", params={"path": str(child.relative_to(root))})
    assert child_detail.status_code == 200
    assert child_detail.json()["workspace"]["id"] == "video"
    assert child_detail.json()["metadata"]["parent_workspace"] == "demo"


def test_meeting_series_content_raw_and_external_edits(client, monkeypatch, tmp_path, monorepo):
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    series = assistant_db.create_meeting_series(root, 'weekly', workspace_id='demo', title='Weekly')
    raw = tmp_path / 'pasted.txt'
    original = b'  Original\r\n# Summary\r\nNot the summary.\r\n'
    raw.write_bytes(original)
    first = assistant_db.create_meeting(root, 'Review', workspace_id='demo', series='weekly', date='2026-09-14', raw_file=raw)
    second = assistant_db.create_meeting(root, 'Older', workspace_id='demo', series='weekly', date='2026-09-07')
    unknown = assistant_db.create_meeting(root, 'Unknown', workspace_id='demo', series='weekly', undated=True)
    metadata, _ = assistant_db.read_markdown(first)
    assistant_db.write_markdown(first, metadata, '# Summary\n\nUpdated by an external editor.\n# Action items\n- [x] Real action\n# Notes\n- [ ] Supporting checklist\n')
    content = assistant_db.create_meeting_content(root, 'Draft', meeting_id=first.stem, kind='document')
    content_path = str(content.relative_to(root))
    rows = client.get('/api/assistant').json()
    assert rows['meeting_series'][0]['meeting_count'] == 3
    assert rows['meetings'][0]['summary'] == 'Updated by an external editor.'
    assert rows['meetings'][0]['action_items_total'] == 1
    detail = client.get('/api/assistant/meeting', params={'path':str(first.relative_to(root))}).json()
    assert 'Supporting checklist' not in detail['overview']
    assert 'Supporting checklist' in detail['notes']
    raw_detail = client.get('/api/assistant/meeting-content', params={'path':detail['raw']['path']}).json()
    assert raw_detail['format'] == 'text' and raw_detail['body'].encode() == original
    history = client.get('/api/assistant/meeting-series', params={'path':str(series.relative_to(root))}).json()
    assert [row['id'] for row in history['meetings']] == [first.stem, second.stem, unknown.stem]
    content_detail = client.get('/api/assistant/meeting-content', params={'path':content_path})
    assert content_detail.status_code == 200
    assert content_detail.json()['workspace']['id'] == 'demo'
    meta, body = assistant_db.read_markdown(content)
    assistant_db.write_markdown(content, {**meta, 'meeting':'some-other-meeting'}, body)
    assert client.get('/api/assistant/meeting-content', params={'path':content_path}).status_code == 400
    assert client.get('/api/assistant').json()['meetings'][0]['content_count'] == 0
    client.cookies.clear()
    for endpoint, path in [('meeting', first), ('meeting-series', series), ('meeting-content', content)]:
        assert client.get('/api/assistant/' + endpoint, params={'path':str(path.relative_to(root))}).status_code in {401,403}


@pytest.mark.parametrize('part', ['meeting','series','companion','content'])
def test_meeting_endpoints_reject_symlink_aliases(client, monkeypatch, tmp_path, monorepo, part):
    root, _ = _seed(monkeypatch, tmp_path, monorepo)
    series = assistant_db.create_meeting_series(root, 'weekly', workspace_id='demo', title='Weekly')
    meeting = assistant_db.create_meeting(root, 'Review', workspace_id='demo', series='weekly')
    content = assistant_db.create_meeting_content(root, 'Question', meeting_id=meeting.stem, kind='question')
    source = {'meeting':meeting, 'series':series, 'companion':meeting.with_suffix(''), 'content':content}[part]
    moved = root / ('moved-' + source.name)
    source.rename(moved)
    source.symlink_to(moved)
    target, endpoint = (series, 'meeting-series') if part == 'series' else (content, 'meeting-content')
    assert client.get('/api/assistant/' + endpoint, params={'path':str(target.relative_to(root))}).status_code == 400


@pytest.mark.parametrize('path', ['../secret.md','/absolute/raw.txt','workspaces/demo/meetings/x/other.txt',
                                  'workspaces/demo/meetings/x/questions/../raw.txt'])
def test_meeting_content_rejects_invalid_paths(client, monkeypatch, tmp_path, monorepo, path):
    _seed(monkeypatch, tmp_path, monorepo)
    assert client.get('/api/assistant/meeting-content', params={'path':path}).status_code == 400
