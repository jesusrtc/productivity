from pathlib import Path

import pytest
from click.testing import CliRunner

from lab import assistant as db, assistant_meetings as meetings
from lab.assistant_recurrence import advance
from lab.cli import main


@pytest.fixture(params=[False, True], ids=["workspace", "legacy-project"])
def database(tmp_path, monkeypatch, request):
    root = tmp_path / "assistant"
    monkeypatch.setenv("LAB_ASSISTANT_HOME", str(root))
    if request.param:
        db.write_markdown(root / "projects/demo/project.md", {
            "id": "demo", "name": "Demo", "workspace": "local",
            "workspace_path": str(tmp_path), "project_path": str(tmp_path / "demo"),
        }, "# Existing mapping\n")
    else:
        db.create_workspace(root, "demo", name="Demo", vault="local", vault_path=tmp_path,
                            workspace_path=tmp_path / "demo")
    return root


def snapshot(root):
    return {str(p.relative_to(root)): p.read_bytes() for p in root.rglob("*") if p.is_file()}


def test_series_originals_and_content_keep_independent_history(database, tmp_path):
    root = database
    raw = b'\xef\xbb\xbf---\r\ntitle: original  \r\n---\r\n\r\n# Summary\r\nRaw only.\r\n'
    original = tmp_path / "raw.txt"
    original.write_bytes(raw)
    meetings.create_series(root, "weekly", workspace_id="demo", title="Weekly")
    runner = CliRunner()
    result = runner.invoke(main, ["assistant", "meeting", "add", "Review", "--workspace", "demo",
                                 "--series", "weekly", "--raw-file", str(original), "--undated"])
    assert result.exit_code == 0, result.output
    identifier = result.output.split()[0]
    meeting, metadata, _ = db.find_meeting(root, identifier)
    assert metadata["date"] is None
    db.write_markdown(meeting, metadata, "# Summary\n\nDecision.\n# Action items\n\n- [ ] Follow up.\n# Notes\n\n- [ ] Not an action.\n")
    assert meetings.summary(db.read_markdown(meeting)[1]) == "Decision."
    content = meetings.create_content(root, "Question", meeting_id=identifier, kind="question")
    assert meetings.resolve_content(root, str(content.relative_to(root)))[1] == meeting
    row = meetings.list_rows(root)[0]
    assert row["content_count"] == 1 and row["has_raw"] and row["action_items_total"] == 1
    assert row["series_title"] == "Weekly" and "body" not in row
    for field, value in [("title", "Updated"), ("date", "2026-09-14"), ("series", None), ("date", None)]:
        meetings.update_meeting(root, identifier, field, value)
    assert meetings.raw_path(root, meeting).read_bytes() == raw
    shown = runner.invoke(main, ["assistant", "meeting", "raw", "show", identifier])
    assert shown.stdout_bytes == raw
    before = snapshot(root)
    with pytest.raises(ValueError, match="cannot be overwritten"):
        meetings.add_raw(root, identifier, original)
    with pytest.raises(ValueError):
        meetings.create_series(root, "weekly", workspace_id="demo", title="Overwrite")
    assert snapshot(root) == before


@pytest.mark.parametrize("value", ["2026-02-30", "2026-9-14", "tomorrow", "", "0000-01-01"])
def test_invalid_dates_do_not_write(database, value):
    before = snapshot(database)
    with pytest.raises(ValueError):
        meetings.create_meeting(database, "Bad", workspace_id="demo", date=value)
    assert snapshot(database) == before


def test_invalid_imports_and_symlinks_never_escape(database, tmp_path):
    raw = tmp_path / "invalid.txt"
    raw.write_bytes(b"\xff")
    before = snapshot(database)
    with pytest.raises(ValueError):
        meetings.create_meeting(database, "Bad", workspace_id="demo", raw_file=raw)
    assert snapshot(database) == before
    meeting = meetings.create_meeting(database, "Good", workspace_id="demo")
    outside = tmp_path / "outside"
    outside.mkdir()
    meeting.with_suffix("").symlink_to(outside)
    raw.write_bytes(b"Original")
    with pytest.raises(ValueError, match="symlinks"):
        meetings.add_raw(database, meeting.stem, raw)
    with pytest.raises(ValueError, match="symlinks"):
        meetings.create_content(database, "Bad", meeting_id=meeting.stem, kind="question")
    assert list(outside.iterdir()) == []


def test_sections_and_actions_ignore_code_and_supporting_checklists():
    body = "Preamble\n# Summary ###\n\nActual.\n````md\n# Notes\nExample.\n````\n# Action items\n- [x] Done\n~~~\n- [ ] Code\n~~~\n    - [ ] Indented code\n# Notes\n- [ ] Support\n"
    overview, notes = meetings.sections(body)
    assert "Preamble" in notes and "Support" in notes and "Actual." not in notes
    assert "Actual." in overview
    assert meetings.summary(body) == "Actual."
    assert [row["title"] for row in meetings.actions(body)] == ["Done"]


def test_series_are_workspace_local_and_not_title_inferred(database, tmp_path):
    db.create_workspace(database, "other", name="Other", vault="local", vault_path=tmp_path, workspace_path=tmp_path)
    for workspace in ("demo", "other"):
        meetings.create_series(database, "weekly", workspace_id=workspace, title="Weekly")
    with pytest.raises(ValueError, match="specify --workspace"):
        meetings.find_series(database, "weekly")
    meetings.create_meeting(database, "Weekly", workspace_id="demo")
    assert meetings.list_rows(database)[0]["series_path"] is None


def test_recurring_tasks_preserve_history_and_restore_month_end(database):
    task = db.create_task(database, "Monthly review", workspace_id="demo", due="2028-01-31")
    db.update_task(database, task.stem, "recurrence", "monthly")
    with pytest.raises(ValueError, match="complete"):
        advance(database, task.stem)
    db.update_task(database, task.stem, "status", "done")
    original = task.read_bytes()
    feb = advance(database, task.stem)
    assert advance(database, task.stem) == feb
    assert db.read_markdown(feb)[0]["due"] == "2028-02-29"
    assert task.read_bytes() == original
    db.update_task(database, feb.stem, "status", "done")
    march = advance(database, feb.stem)
    assert db.read_markdown(march)[0]["due"] == "2028-03-31"
    assert db.read_markdown(march)[0]["previous_task"] == feb.stem
    undated = db.create_task(database, "Unknown schedule", workspace_id="demo")
    db.update_task(database, undated.stem, "recurrence", "weekly")
    db.update_task(database, undated.stem, "status", "done")
    before = snapshot(database)
    with pytest.raises(ValueError, match="confirm a valid due"):
        advance(database, undated.stem)
    assert snapshot(database) == before
