from __future__ import annotations

import os
import subprocess
import webbrowser

import click

from lab import paths


def _server_port() -> str:
    """Resolve the lab server's port.

    Precedence: LAB_PORT env var → `.lab-server.port` (written by the running
    server on startup) → ``3333`` (legacy default). Mirrors
    ``scripts/lab-url.sh`` so CLI + shell tools agree.
    """
    env = os.environ.get("LAB_PORT")
    if env:
        return env.strip()
    try:
        root = paths.find_monorepo_root()
    except paths.MonorepoNotFound:
        return "3333"
    pf = root / ".lab-server.port"
    if pf.is_file():
        try:
            value = pf.read_text().strip()
            if value:
                return value
        except OSError:
            pass
    return "3333"


@click.command(name="start")
def start() -> None:
    """Start the backend in the background (`make start-bg`)."""
    root = paths.find_monorepo_root()
    subprocess.run(["make", "start-bg"], check=True, cwd=str(root))


@click.command(name="stop")
def stop() -> None:
    """Stop the running backend (`make stop`)."""
    root = paths.find_monorepo_root()
    subprocess.run(["make", "stop"], check=True, cwd=str(root))


@click.command(name="open")
def open_cmd() -> None:
    """Open the backend index URL in the default browser."""
    webbrowser.open(f"http://localhost:{_server_port()}/api/index")
