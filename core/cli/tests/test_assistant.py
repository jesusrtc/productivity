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
    assert rows[0]["subtasks_total"] == 1
    assert rows[0]["subtasks_done"] == 0

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
