from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

import click

from lab import paths


def _ensure_workspace(root: Path) -> None:
    if not root.is_dir():
        raise click.ClickException(f"workspace path not found: {root}")
    if not (root / "lab.toml").is_file() and not (root / "content").is_dir():
        raise click.ClickException(f"{root} is not a Lab workspace; run `lab init {root}` first")


def server_port(workspace: Path | None = None) -> str:
    """Resolve the lab server's port.

    Precedence: LAB_PORT env var → workspace server port file (written by the running
    server on startup) → ``3333`` (legacy default). Mirrors
    ``scripts/lab-url.sh`` so CLI + shell tools agree.
    """
    env = os.environ.get("LAB_PORT")
    if env:
        return env.strip()
    roots: list[Path] = []
    if workspace is not None:
        roots.append(workspace.expanduser().resolve())
    else:
        try:
            roots.append(paths.find_workspace_root())
        except paths.MonorepoNotFound:
            pass
    active = paths.active_workspace()
    if active is not None and active not in roots:
        roots.append(active)
    for root in roots:
        for pf in (paths.port_file(root), root / ".lab-server.port"):
            if not pf.is_file():
                continue
            try:
                value = pf.read_text().strip()
                if value:
                    return value
            except OSError:
                pass
    return "3333"


@click.command(name="start")
@click.option("--workspace", "workspace_path", type=click.Path(path_type=Path),
              default=None, help="Workspace to serve.")
@click.option("--port", "-p", "port", type=int, default=None,
              help="Port for this server run.")
def start(workspace_path: Path | None, port: int | None) -> None:
    """Start the backend in the background."""
    if workspace_path is not None:
        workspace = workspace_path.expanduser().resolve()
    else:
        workspace = paths.find_workspace_root()
    _ensure_workspace(workspace)
    paths.register_workspace(workspace, name=workspace.name, active=True)

    framework = paths.find_framework_root()
    env = os.environ.copy()
    env["LAB_WORKSPACE"] = str(workspace)
    cmd = ["make", "start-bg"]
    if port is not None:
        env["LAB_PORT"] = str(port)
        cmd.append(f"PORT={port}")
    subprocess.run(cmd, check=True, cwd=str(framework), env=env)


@click.command(name="stop")
def stop() -> None:
    """Stop the running backend (`make stop`)."""
    framework = paths.find_framework_root()
    subprocess.run(["make", "stop"], check=True, cwd=str(framework))


@click.command(name="open")
def open_cmd() -> None:
    """Open the backend index URL in the default browser."""
    webbrowser.open(f"http://localhost:{server_port()}/api/index")
