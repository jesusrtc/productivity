from __future__ import annotations

import subprocess
from pathlib import Path

from click.testing import CliRunner

from lab import tmux_sockets
from lab.cli import main
from lab.commands import terminal as terminal_cmd


def _completed(
    returncode: int = 0,
    stdout: str = "",
    stderr: str = "",
) -> subprocess.CompletedProcess[str]:
    return subprocess.CompletedProcess([], returncode, stdout, stderr)


def test_terminal_status_defaults_to_one_legacy_socket(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.setattr(
        terminal_cmd,
        "_run",
        lambda *_args: _completed(1, stderr="no server running"),
    )

    result = CliRunner().invoke(main, ["terminal", "status"])

    assert result.exit_code == 0, result.output
    assert "active   default" in result.output
    assert "Lab sessions: 0" in result.output
    assert not tmux_sockets.state_file().exists()


def test_terminal_rotate_seeds_fresh_socket_and_keeps_old_draining(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run(socket_name: str, *args: str):
        calls.append((socket_name, args))
        if args and args[0] == "list-sessions":
            return _completed(stdout="neurona-project-copilot-abcdef\n")
        return _completed()

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code == 0, result.output
    state = tmux_sockets.read_state()
    assert state["active"].startswith("lab-")
    draining = [
        row for row in state["generations"] if row["status"] == "draining"
    ]
    assert draining and draining[0]["name"] == "default"
    assert any(
        args == (
            "start-server",
            ";",
            "set-option",
            "-g",
            "exit-empty",
            "off",
        )
        for _socket, args in calls
    )
    assert not any(args and args[0] == "new-session" for _, args in calls)


def test_terminal_rotate_refuses_inside_tmux_without_starting_anything(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.setenv("TMUX", "/tmp/tmux/default,1,0")
    calls: list[tuple] = []
    monkeypatch.setattr(
        terminal_cmd,
        "_run",
        lambda *args: calls.append(args) or _completed(),
    )

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code != 0
    assert "directly from the working iTerm" in result.output
    assert calls == []


def test_terminal_rotate_skips_drain_when_old_socket_has_no_lab_sessions(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")

    def fake_run(_socket_name: str, *args: str):
        if args and args[0] == "list-sessions":
            return _completed(stdout="personal-shell\n")
        return _completed()

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code == 0, result.output
    state = tmux_sockets.read_state()
    assert len(state["generations"]) == 1
    assert state["generations"][0]["status"] == "active"


def test_terminal_rotate_is_bounded_while_previous_generation_drains(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")
    tmux_sockets.write_state(
        tmux_sockets.rotated_state(tmux_sockets.default_state(), "lab-current")
    )
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run(socket_name: str, *args: str):
        calls.append((socket_name, args))
        return _completed(stdout="neurona-project-shell-abcdef\n")

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code != 0
    assert "still draining" in result.output
    assert not any(args and args[0] == "start-server" for _, args in calls)


def test_terminal_rotate_rolls_back_new_server_if_old_cannot_retire(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")
    tmux_sockets.write_state({
        "version": 1,
        "active": "lab-current",
        "generations": [{
            "name": "lab-current",
            "status": "active",
            "created_at": 1,
        }],
    })
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run(socket_name: str, *args: str):
        calls.append((socket_name, args))
        if args and args[0] == "list-sessions":
            return _completed(stdout="neurona-project-shell-abcdef\n")
        if (
            socket_name == "lab-current"
            and args == ("set-option", "-g", "exit-empty", "on")
        ):
            return _completed(1, stderr="cannot change option")
        return _completed()

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code != 0
    assert "cannot change option" in result.output
    assert tmux_sockets.read_state()["active"] == "lab-current"
    assert any(args == ("kill-server",) for _, args in calls)
    assert (
        "lab-current",
        ("set-option", "-g", "exit-empty", "off"),
    ) in calls


def test_terminal_rotate_replaces_a_dead_active_named_socket(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")
    tmux_sockets.write_state({
        "version": 1,
        "active": "lab-dead",
        "generations": [{
            "name": "lab-dead",
            "status": "active",
            "created_at": 1,
        }],
    })
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run(socket_name: str, *args: str):
        calls.append((socket_name, args))
        if args and args[0] == "list-sessions":
            return _completed(1, stderr="no server running")
        if socket_name == "lab-dead" and args[:1] == ("set-option",):
            return _completed(1, stderr="no server running")
        return _completed()

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code == 0, result.output
    state = tmux_sockets.read_state()
    assert state["active"].startswith("lab-")
    assert state["active"] != "lab-dead"
    assert [row["name"] for row in state["generations"]] == [state["active"]]
    assert (
        "lab-dead",
        ("set-option", "-g", "exit-empty", "on"),
    ) in calls
    assert (
        "lab-dead",
        ("set-option", "-g", "exit-empty", "off"),
    ) not in calls


def test_terminal_rotate_retires_an_empty_live_named_socket_without_a_drain(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    monkeypatch.delenv("TMUX", raising=False)
    monkeypatch.setattr(terminal_cmd.shutil, "which", lambda _name: "/usr/bin/tmux")
    tmux_sockets.write_state({
        "version": 1,
        "active": "lab-current",
        "generations": [{
            "name": "lab-current",
            "status": "active",
            "created_at": 1,
        }],
    })
    calls: list[tuple[str, tuple[str, ...]]] = []

    def fake_run(socket_name: str, *args: str):
        calls.append((socket_name, args))
        if args and args[0] == "list-sessions":
            return _completed(1, stderr="no sessions")
        return _completed()

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "rotate"])

    assert result.exit_code == 0, result.output
    state = tmux_sockets.read_state()
    assert [row["name"] for row in state["generations"]] == [state["active"]]
    assert "no old Lab sessions to drain" in result.output
    assert (
        "lab-current",
        ("set-option", "-g", "exit-empty", "on"),
    ) in calls


def test_terminal_status_prunes_an_empty_draining_generation(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    tmux_sockets.write_state(
        tmux_sockets.rotated_state(tmux_sockets.default_state(), "lab-current")
    )

    def fake_run(socket_name: str, *args: str):
        if args and args[0] == "list-sessions" and socket_name == "default":
            return _completed(1, stderr="no server running")
        return _completed(stdout="neurona-project-shell-abcdef\n")

    monkeypatch.setattr(terminal_cmd, "_run", fake_run)

    result = CliRunner().invoke(main, ["terminal", "status"])

    assert result.exit_code == 0, result.output
    assert tmux_sockets.read_state()["active"] == "lab-current"
    assert [
        row["name"] for row in tmux_sockets.read_state()["generations"]
    ] == ["lab-current"]
    assert "default" not in result.output


def test_tmux_command_preserves_default_shape_and_namespaces_rotated_socket() -> None:
    assert tmux_sockets.command(
        "default", "has-session", "-t", "demo"
    ) == ["tmux", "has-session", "-t", "demo"]
    assert tmux_sockets.command(
        "lab-fresh", "has-session", "-t", "demo"
    ) == ["tmux", "-L", "lab-fresh", "has-session", "-t", "demo"]
    assert tmux_sockets.is_no_server_error(
        "error connecting to /tmp/tmux-501/default (No such file or directory)"
    )


def test_state_normalization_never_retains_more_than_two_generations(
    monkeypatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("LAB_HOME", str(tmp_path / "lab-home"))
    tmux_sockets.write_state({
        "version": 1,
        "active": "lab-active",
        "generations": [
            {"name": "lab-old-1", "created_at": 1},
            {"name": "lab-active", "created_at": 3},
            {"name": "lab-old-2", "created_at": 2},
        ],
    })

    state = tmux_sockets.read_state()
    assert [row["name"] for row in state["generations"]] == [
        "lab-active",
        "lab-old-2",
    ]
