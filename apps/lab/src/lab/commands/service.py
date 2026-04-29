from __future__ import annotations

import subprocess
import webbrowser

import click

from lab import paths


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
    webbrowser.open("http://localhost:3333/api/index")
