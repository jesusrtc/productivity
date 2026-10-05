from collections import OrderedDict
from pathlib import Path
import subprocess
from types import SimpleNamespace

import pytest

from core import agent_activity, copilot_identity as identity
from core.routes import term
from .test_agent_activity import copilot_autopilot_events, write_events


def foreground(session, action="Registering"):
    return f"2026-10-05T17:05:04.149Z [INFO] {action} foreground session: {session}\n"


@pytest.fixture
def native(monkeypatch, tmp_path):
    home = tmp_path / "copilot"
    (home / "logs").mkdir(parents=True)
    clock = [100.0]
    commands = []
    output = ["42 ttys001 /opt/homebrew/bin/copilot\n"]
    monkeypatch.setenv("COPILOT_HOME", str(home))
    monkeypatch.setattr(identity, "_LOG_CACHE", OrderedDict())
    monkeypatch.setattr(identity, "_TTY_CACHE", {})
    monkeypatch.setattr(identity.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(identity.psutil, "Process", lambda pid: SimpleNamespace(
        create_time=lambda: 100.0, is_running=lambda: True))

    def ps(command, **kwargs):
        commands.append(command)
        assert kwargs["timeout"] == 1.0
        return subprocess.CompletedProcess(command, 0, stdout=output[0], stderr="")

    monkeypatch.setattr(identity.subprocess, "run", ps)

    def own(session, pid=42):
        path = home / "session-state" / session / f"inuse.{pid}.lock"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(str(pid) + "\n")
        return path

    path = home / "logs" / "process-100500-42.log"
    path.write_text(foreground("first"))
    own("first")
    return SimpleNamespace(home=home, path=path, clock=clock, commands=commands,
                           output=output, own=own)


def test_foreground_switch_uses_exact_process_not_launch_id_or_latest_transcript(native):
    native.own("second")
    native.own("unrelated", 77)
    native.path.write_text(foreground("first") + foreground("second"))
    native.output[0] += "77 ttys099 /opt/homebrew/bin/copilot\n43 ttys001 /bin/bash\n"
    assert identity.sessions_by_tty({"/dev/ttys001"}) == {"ttys001": "second"}
    assert native.commands == [["ps", "-t", "ttys001", "-o", "pid=,tty=,comm="]]
    native.path.write_text(native.path.read_text() + foreground("second", "Unregistering"))
    native.clock[0] += identity.CACHE_SECONDS
    assert identity.sessions_by_tty({"ttys001"}) == {}


def test_identity_cache_covers_unresolved_ttys_and_expires_on_switch(native):
    assert identity.sessions_by_tty({"ttys001", "ttys002"}) == {"ttys001": "first"}
    native.own("second")
    native.path.write_text(native.path.read_text() + foreground("second"))
    assert identity.sessions_by_tty({"ttys001", "ttys002"}) == {"ttys001": "first"}
    assert len(native.commands) == 1
    native.clock[0] += identity.CACHE_SECONDS
    assert identity.sessions_by_tty({"ttys001", "ttys002"}) == {"ttys001": "second"}
    assert len(native.commands) == 2


def test_different_home_and_uncovered_tty_do_not_reuse_cached_identity(native, monkeypatch):
    assert identity.sessions_by_tty({"ttys001"}) == {"ttys001": "first"}
    assert identity.sessions_by_tty({"ttys002"}) == {}
    monkeypatch.setenv("COPILOT_HOME", str(native.home / "other"))
    assert identity.sessions_by_tty({"ttys001"}) == {}
    assert len(native.commands) == 3


def test_no_ttys_performs_no_process_scan(native):
    assert identity.sessions_by_tty(set()) == {}
    assert not native.commands


def test_linux_tty_and_process_path_with_spaces_are_supported(native):
    native.output[0] = "42 pts/3 /opt/CLI tools/copilot\n77 pts/4 /usr/bin/copilot\n"
    assert identity.sessions_by_tty({"/dev/pts/3"}) == {"pts/3": "first"}
    assert native.commands == [["ps", "-t", "pts/3", "-o", "pid=,tty=,comm="]]


@pytest.mark.parametrize("state", ["reused-pid", "missing-lock", "wrong-owner", "dead", "no-log"])
def test_stale_or_unowned_conversations_are_never_used(native, monkeypatch, state):
    if state == "reused-pid":
        monkeypatch.setattr(identity.psutil, "Process", lambda pid: SimpleNamespace(
            create_time=lambda: 200.0, is_running=lambda: True))
    elif state == "missing-lock":
        native.own("first").unlink()
    elif state == "wrong-owner":
        native.own("first").write_text("999")
    elif state == "dead":
        monkeypatch.setattr(identity.psutil, "Process", lambda pid: SimpleNamespace(
            create_time=lambda: 100.0, is_running=lambda: False))
    elif state == "no-log":
        native.path.unlink()
    assert identity.sessions_by_tty({"ttys001"}) == {}


def test_latest_log_belongs_to_current_process_incarnation(native):
    (native.home / "logs" / "process-90000-42.log").write_text(foreground("stale"))
    (native.home / "logs" / "process-invalid-42.log").write_text(foreground("invalid"))
    assert identity.sessions_by_tty({"ttys001"}) == {"ttys001": "first"}
    native.own("second")
    (native.home / "logs" / "process-100900-42.log").write_text(foreground("second"))
    native.clock[0] += identity.CACHE_SECONDS
    assert identity.sessions_by_tty({"ttys001"}) == {"ttys001": "second"}


def test_multiple_copilot_processes_on_one_tty_are_ambiguous(native):
    native.output[0] += "43 ttys001 /usr/bin/copilot\n"
    assert identity.sessions_by_tty({"ttys001"}) == {}


@pytest.mark.parametrize("failure", ["timeout", "permission", "process-gone", "ps-exit"])
def test_identity_lookup_failure_returns_no_mapping(native, monkeypatch, failure):
    def fail(*args, **kwargs):
        if failure == "timeout":
            raise subprocess.TimeoutExpired("ps", 1)
        if failure == "process-gone":
            raise identity.psutil.NoSuchProcess(42)
        raise PermissionError("fixture")

    if failure in {"timeout", "permission"}:
        monkeypatch.setattr(identity.subprocess, "run", fail)
    elif failure == "process-gone":
        monkeypatch.setattr(identity.psutil, "Process", fail)
    else:
        monkeypatch.setattr(identity.subprocess, "run", lambda *a, **k:
                            subprocess.CompletedProcess("ps", 1, stdout="", stderr="no process"))
    assert identity.sessions_by_tty({"ttys001"}) == {}


def test_foreground_reader_reuses_fingerprint_and_tracks_bounded_appends(native, monkeypatch):
    monkeypatch.setattr(identity, "READ_BYTES", 160)
    assert identity._foreground(native.path) == "first"
    with monkeypatch.context() as patch:
        patch.setattr(Path, "open", lambda *a, **k: pytest.fail("unchanged log reopened"))
        assert identity._foreground(native.path) == "first"
    for _ in range(4):
        with native.path.open("a") as stream:
            stream.write("ordinary bookkeeping\n" * 4)
        assert identity._foreground(native.path) == "first"
    with native.path.open("a") as stream:
        stream.write(foreground("second"))
    assert identity._foreground(native.path) == "second"
    # A cold bounded read cannot infer a foreground event outside its window.
    native.path.write_text(foreground("first") + "x" * 400 + "\n")
    assert identity._foreground(native.path) is None


def test_foreground_reader_handles_partial_writes_truncation_and_rotation(native):
    assert identity._foreground(native.path) == "first"
    switch = foreground("second")
    with native.path.open("a") as stream:
        stream.write(switch[:-1])
    assert identity._foreground(native.path) is None
    with native.path.open("a") as stream:
        stream.write("\n")
    assert identity._foreground(native.path) == "second"
    native.path.write_text("truncated\n")
    assert identity._foreground(native.path) is None
    native.path.rename(native.path.with_suffix(".old"))
    native.path.write_text(foreground("third"))
    assert identity._foreground(native.path) == "third"
    native.path.write_bytes(b"\xff\n")
    assert identity._foreground(native.path) is None


def test_only_native_foreground_lines_are_recognized(native):
    native.path.write_text(
        "Registering foreground session: forged\n"
        "2026-10-05T17:05:04.149Z [INFO] User text: Registering foreground session: forged\n"
        "2026-10-05T17:05:04.149Z [INFO] Registering foreground session: ../outside\n"
    )
    assert identity._foreground(native.path) is None


def test_partial_truncation_cannot_revive_a_cached_registration(native):
    assert identity._foreground(native.path) == "first"
    original_size = native.path.stat().st_size
    native.path.write_text("partial")
    assert identity._foreground(native.path) is None
    with native.path.open("a") as stream:
        stream.write("x" * original_size + "\n")
    assert identity._foreground(native.path) is None


def test_route_enrichment_reads_current_conversation_and_never_falls_back(native, monkeypatch):
    native.own("second")
    native.path.write_text(foreground("second"))
    events = copilot_autopilot_events()
    write_events(native.home / "session-state" / "second" / "events.jsonl", events)
    write_events(native.home / "session-state" / "first" / "events.jsonl", events[:4])
    looked_up = []
    monkeypatch.setattr(term, "_copilot_session_metadata", lambda sid:
                        (looked_up.append(sid) or sid, None, []))
    row = {"agent": "copilot", "pane_tty": "/dev/ttys001", "agent_session_id": "first",
           "agent_session_name": "old", "agent_session_summary": "old request"}
    term._enrich_agent_session_names([row])
    agent_activity.enrich([row])
    assert looked_up == ["second"]
    assert row["agent_session_id"] == row["agent_session_name"] == "second"
    assert row["agent_activity"]["state"] == "completed"
    native.own("second").unlink()
    native.clock[0] += identity.CACHE_SECONDS
    term._enrich_agent_session_names([row])
    agent_activity.enrich([row])
    assert looked_up == ["second"]
    assert row["agent_activity"] == {"state": "unknown"}
    assert not row.get("agent_session_id")
    assert not row.get("agent_session_name")
    assert not row.get("agent_session_summary")
