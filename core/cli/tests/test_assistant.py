from __future__ import annotations

from pathlib import Path

from click.testing import CliRunner

from lab import assistant, paths
from lab.cli import main


def _configure(monkeypatch, tmp_path: Path) -> Path:
    root = tmp_path / "assistant-db"
    monkeypatch.setenv("LAB_ASSISTANT_HOME", str(root))
    return root


def test_assistant_root_reads_client_env(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.delenv("LAB_ASSISTANT_HOME", raising=False)
    env_file = tmp_path / "client.env"
    env_file.write_text("LAB_ASSISTANT_HOME='/tmp/my assistant'\n", encoding="utf-8")
    monkeypatch.setenv("LAB_ENV_FILE", str(env_file))
    assert paths.assistant_root(tmp_path) == Path("/tmp/my assistant").resolve()


def test_assistant_init_and_task_lifecycle(monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    root = _configure(monkeypatch, tmp_path)
    paths.register_workspace(monorepo, name="Test", workspace_id="test", active=True)
    runner = CliRunner()

    result = runner.invoke(main, ["assistant", "init"])
    assert result.exit_code == 0, result.output
    assert (root / "AGENTS.md").is_file()
    assert (root / "README.md").is_file()

    project_path = monorepo / "projects" / "demo"
    project_path.mkdir(parents=True)
    result = runner.invoke(main, [
        "assistant", "project", "add", "demo",
        "--name", "Demo", "--workspace", "test", "--path", str(project_path),
    ])
    assert result.exit_code == 0, result.output

    result = runner.invoke(main, [
        "assistant", "add", "Prepare launch note",
        "--project", "demo", "--priority", "P1", "--status", "ready",
    ])
    assert result.exit_code == 0, result.output
    task_id = result.output.split()[0]
    rows = list(assistant.iter_tasks(root))
    assert rows[0]["id"] == task_id
    assert rows[0]["workspace"] == "test"
    assert rows[0]["project_path"] == str(project_path)
    assert rows[0]["subtasks_total"] == 0
    assert rows[0]["subtasks_done"] == 0

    source, metadata, body = assistant.find_task(root, task_id)
    assistant.write_markdown(source, metadata, body + "\n- [ ] Legacy follow-up.\n")
    result = runner.invoke(main, ["assistant", "done", task_id])
    assert result.exit_code != 0
    assert "1 incomplete subtask" in result.output

    source, metadata, body = assistant.find_task(root, task_id)
    assistant.write_markdown(source, metadata, body.replace("- [ ]", "- [x]"))
    result = runner.invoke(main, ["assistant", "done", task_id])
    assert result.exit_code == 0, result.output
    _source, metadata, _body = assistant.find_task(root, task_id)
    assert metadata["status"] == "done"
    assert metadata["completed"]


def test_assistant_meeting_cli(monkeypatch, tmp_path: Path, monorepo: Path) -> None:
    root = _configure(monkeypatch, tmp_path)
    paths.register_workspace(monorepo, name="Test", workspace_id="test", active=True)
    runner = CliRunner()
    assert runner.invoke(main, ["assistant", "init"]).exit_code == 0
    project_path = monorepo / "projects" / "demo"
    project_path.mkdir(parents=True)
    assert runner.invoke(main, [
        "assistant", "project", "add", "demo",
        "--name", "Demo", "--workspace", "test", "--path", str(project_path),
    ]).exit_code == 0

    result = runner.invoke(main, [
        "assistant", "meeting", "add", "Weekly product review",
        "--project", "demo", "--date", "2026-09-03",
        "--attendee", "Maya", "--attendee", "Leo", "--tag", "demo",
    ])
    assert result.exit_code == 0, result.output
    meeting_id = result.output.split()[0]

    listed = runner.invoke(main, ["assistant", "meeting", "ls", "--project", "demo"])
    assert listed.exit_code == 0, listed.output
    assert meeting_id in listed.output
    assert "Weekly product review" in listed.output

    shown = runner.invoke(main, ["assistant", "meeting", "show", meeting_id])
    assert shown.exit_code == 0, shown.output
    assert '# Summary' in shown.output
    assert 'attendees: ["Maya", "Leo"]' in shown.output


def test_assistant_first_class_subtask_lifecycle(
    monkeypatch,
    tmp_path: Path,
    monorepo: Path,
) -> None:
    root = _configure(monkeypatch, tmp_path)
    paths.register_workspace(monorepo, name="Test", workspace_id="test", active=True)
    runner = CliRunner()
    assert runner.invoke(main, ["assistant", "init"]).exit_code == 0
    project_path = monorepo / "projects" / "demo"
    project_path.mkdir(parents=True)
    assert runner.invoke(main, [
        "assistant", "project", "add", "demo",
        "--name", "Demo", "--workspace", "test", "--path", str(project_path),
    ]).exit_code == 0

    created = runner.invoke(main, [
        "assistant", "add", "Prepare campaign",
        "--project", "demo", "--priority", "P1", "--status", "in_progress",
    ])
    assert created.exit_code == 0, created.output
    task_id = created.output.split()[0]

    created_subtask = runner.invoke(main, [
        "assistant", "subtask", "add", "Draft announcement",
        "--parent", task_id, "--priority", "P0", "--status", "in_progress",
        "--owner", "agent", "--tag", "communication",
    ])
    assert created_subtask.exit_code == 0, created_subtask.output
    subtask_id = created_subtask.output.split()[0]
    source, metadata, body = assistant.find_subtask(root, subtask_id)
    assert source.parent == root / "projects" / "demo" / "subtasks"
    assert metadata["parent"] == task_id
    assert metadata["project"] == "demo"
    assert metadata["priority"] == "P0"
    assert metadata["status"] == "in_progress"
    assert metadata["owner"] == "agent"
    assert metadata["tags"] == ["communication"]
    assert "# Context" in body

    tasks = list(assistant.iter_tasks(root))
    assert tasks[0]["subtasks_total"] == 1
    assert tasks[0]["subtasks_done"] == 0
    assert tasks[0]["first_class_subtasks"][0]["id"] == subtask_id
    assert tasks[0]["first_class_subtasks"][0]["document_backed"] is True

    listed = runner.invoke(main, [
        "assistant", "subtask", "ls", "--parent", task_id, "--priority", "P0",
    ])
    assert listed.exit_code == 0, listed.output
    assert subtask_id in listed.output
    assert "Draft announcement" in listed.output

    shown = runner.invoke(main, ["assistant", "subtask", "show", subtask_id])
    assert shown.exit_code == 0, shown.output
    assert f'parent: "{task_id}"' in shown.output

    waiting = runner.invoke(main, [
        "assistant", "subtask", "set", subtask_id, "status", "waiting",
    ])
    assert waiting.exit_code == 0, waiting.output
    for field, value in (
        ("waiting_on", "Maya"),
        ("follow_up_at", "2026-09-08"),
        ("follow_up_channel", "email"),
        ("executor", "codex"),
        ("reviewer", "Jesus"),
    ):
        result = runner.invoke(main, [
            "assistant", "subtask", "set", subtask_id, field, value,
        ])
        assert result.exit_code == 0, result.output
    _source, metadata, _body = assistant.find_subtask(root, subtask_id)
    assert metadata["waiting_since"]
    assert metadata["waiting_on"] == "Maya"
    assert metadata["follow_up_at"] == "2026-09-08"
    assert metadata["follow_up_channel"] == "email"
    assert metadata["executor"] == "codex"
    assert metadata["reviewer"] == "Jesus"

    review = runner.invoke(main, [
        "assistant", "subtask", "set", subtask_id, "status", "ready_to_review",
    ])
    assert review.exit_code == 0, review.output
    _source, metadata, _body = assistant.find_subtask(root, subtask_id)
    assert metadata["status"] == "ready_to_review"
    assert metadata["review_requested_at"]

    blocked = runner.invoke(main, ["assistant", "done", task_id])
    assert blocked.exit_code != 0
    assert "1 incomplete subtask" in blocked.output
    assert "first-class subtask" in blocked.output

    completed = runner.invoke(main, ["assistant", "subtask", "done", subtask_id])
    assert completed.exit_code == 0, completed.output
    _source, metadata, _body = assistant.find_subtask(root, subtask_id)
    assert metadata["status"] == "done"
    assert metadata["completed"]
    completed_parent = runner.invoke(main, ["assistant", "done", task_id])
    assert completed_parent.exit_code == 0, completed_parent.output


def test_assistant_ready_to_review_task_and_invalid_subtask_parent(
    monkeypatch,
    tmp_path: Path,
    monorepo: Path,
) -> None:
    root = _configure(monkeypatch, tmp_path)
    paths.register_workspace(monorepo, name="Test", workspace_id="test", active=True)
    runner = CliRunner()
    assert runner.invoke(main, ["assistant", "init"]).exit_code == 0
    project_path = monorepo / "projects" / "demo"
    project_path.mkdir(parents=True)
    assert runner.invoke(main, [
        "assistant", "project", "add", "demo",
        "--name", "Demo", "--workspace", "test", "--path", str(project_path),
    ]).exit_code == 0

    created = runner.invoke(main, [
        "assistant", "add", "Review generated copy",
        "--project", "demo", "--status", "ready_to_review",
    ])
    assert created.exit_code == 0, created.output
    task_id = created.output.split()[0]
    _source, metadata, _body = assistant.find_task(root, task_id)
    assert metadata["status"] == "ready_to_review"
    assert metadata["review_requested_at"]

    listed = runner.invoke(main, [
        "assistant", "ls", "--status", "ready_to_review",
    ])
    assert listed.exit_code == 0, listed.output
    assert task_id in listed.output

    invalid = runner.invoke(main, [
        "assistant", "subtask", "add", "Orphan", "--parent", "missing-task",
    ])
    assert invalid.exit_code != 0
    assert "task 'missing-task' not found" in invalid.output
