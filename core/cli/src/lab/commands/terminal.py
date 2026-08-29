from __future__ import annotations

import os
import shutil
import subprocess
import time
import uuid

import click

from lab import tmux_sockets


def _run(socket_name: str, *args: str) -> subprocess.CompletedProcess[str]:
    env = {k: v for k, v in os.environ.items() if k not in ("TMUX", "TMUX_PANE")}
    return subprocess.run(
        tmux_sockets.command(socket_name, *args),
        capture_output=True,
        text=True,
        env=env,
    )


def _lab_session_names(socket_name: str) -> list[str] | None:
    proc = _run(socket_name, "list-sessions", "-F", "#{session_name}")
    if proc.returncode == 0:
        prefix = os.environ.get("LAB_TMUX_PREFIX")
        return [
            name
            for name in proc.stdout.splitlines()
            if name and (
                name.startswith(prefix)
                if prefix
                else name.startswith("neurona-") or name.startswith("lab-")
            )
        ]
    error = (proc.stderr or proc.stdout or "").lower()
    if tmux_sockets.is_no_server_error(error):
        return []
    return None


def _retire_empty_draining(
    state: dict, *, already_locked: bool = False,
) -> dict:
    empty: set[str] = set()
    for row in state["generations"]:
        if row["status"] != "draining":
            continue
        sessions = _lab_session_names(str(row["name"]))
        if sessions == []:
            empty.add(str(row["name"]))
    if empty:
        tmux_sockets.prune_drained(empty, already_locked=already_locked)
        return tmux_sockets.read_state()
    return state


@click.group("terminal")
def terminal_group() -> None:
    """Manage Lab's rolling tmux transport."""


@terminal_group.command("status")
def status() -> None:
    """Show the active and draining terminal socket generations."""
    state = _retire_empty_draining(tmux_sockets.read_state())
    for row in state["generations"]:
        sessions = _lab_session_names(str(row["name"]))
        count = "unavailable" if sessions is None else str(len(sessions))
        click.echo(f"{row['status']:8} {row['name']}  Lab sessions: {count}")


@terminal_group.command("rotate")
def rotate() -> None:
    """Seed a fresh socket here and route future Lab terminals to it.

    Run this directly from a working iTerm window. Existing terminal sessions
    keep running on the prior socket until they are closed normally.
    """
    if os.environ.get("TMUX"):
        raise click.ClickException(
            "refusing to rotate from inside tmux; run this command directly "
            "from the working iTerm so the new server inherits its security context"
        )
    if not shutil.which("tmux"):
        raise click.ClickException("tmux not installed; run: brew install tmux")

    with tmux_sockets.state_lock():
        state = _retire_empty_draining(
            tmux_sockets.read_state(), already_locked=True,
        )
        draining = [
            row for row in state["generations"] if row["status"] == "draining"
        ]
        if draining:
            name = draining[0]["name"]
            sessions = _lab_session_names(str(name))
            count = "unknown" if sessions is None else str(len(sessions))
            raise click.ClickException(
                f"socket {name!r} is still draining ({count} Lab sessions); "
                "finish those sessions before rotating again"
            )

        stamp = time.strftime("%Y%m%d-%H%M%S")
        new_socket = f"lab-{stamp}-{uuid.uuid4().hex[:8]}"
        proc = _run(
            new_socket,
            "start-server",
            ";",
            "set-option",
            "-g",
            "exit-empty",
            "off",
        )
        if proc.returncode != 0:
            raise click.ClickException(
                (proc.stderr or proc.stdout or "tmux could not seed a new socket").strip()
            )

        previous = str(state["active"])
        restore_previous = False
        state_published = False
        try:
            next_state = tmux_sockets.rotated_state(state, new_socket)
            previous_sessions = _lab_session_names(previous)

            # An empty named server can exit immediately when exit-empty is
            # restored. Publish the replacement first so a later state-write
            # failure can never strand routing on a server we just retired.
            if (
                previous != tmux_sockets.DEFAULT_SOCKET
                and previous_sessions == []
            ):
                next_state["generations"] = [
                    row
                    for row in next_state["generations"]
                    if row["name"] == new_socket
                ]
                tmux_sockets.write_state(next_state)
                state_published = True

            # A named active socket is kept alive even while empty so its
            # launch security context survives. Once superseded, restore
            # tmux's normal exit-on-empty behavior so it drains naturally.
            if previous != tmux_sockets.DEFAULT_SOCKET:
                restore_previous = True
                retiring = _run(previous, "set-option", "-g", "exit-empty", "on")
                if retiring.returncode != 0:
                    error = (retiring.stderr or retiring.stdout or "").strip()
                    if (
                        previous_sessions == []
                        and tmux_sockets.is_no_server_error(error)
                    ):
                        # The active named server died before this recovery
                        # rotation. It cannot drain and must not block the
                        # newly seeded replacement.
                        next_state["generations"] = [
                            row
                            for row in next_state["generations"]
                            if row["name"] == new_socket
                        ]
                        restore_previous = False
                    else:
                        raise click.ClickException(
                            error or f"could not mark {previous!r} as draining"
                        )
            elif previous_sessions == []:
                # The implicit default server already has nothing from Lab
                # to preserve. It may still host unrelated user sessions,
                # so omit it from Lab routing without touching the server.
                next_state["generations"] = [
                    row
                    for row in next_state["generations"]
                    if row["name"] == new_socket
                ]

            if not state_published:
                tmux_sockets.write_state(next_state)
        except Exception:
            if restore_previous:
                _run(previous, "set-option", "-g", "exit-empty", "off")
            if state_published:
                tmux_sockets.write_state(state)
            _run(new_socket, "kill-server")
            raise

    click.echo(f"seeded fresh terminal socket: {new_socket}")
    if any(row["name"] == previous for row in next_state["generations"]):
        click.echo(
            f"future Lab terminals use {new_socket}; {previous} is draining"
        )
    else:
        click.echo(
            f"future Lab terminals use {new_socket}; no old Lab sessions to drain"
        )
