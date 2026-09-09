from __future__ import annotations

import os
import subprocess
import webbrowser
from pathlib import Path

import click

from lab import paths


def _ensure_vault(root: Path) -> None:
    if not root.is_dir():
        raise click.ClickException(f"vault path not found: {root}")
    if not (root / "lab.toml").is_file() and not (root / "content").is_dir():
        raise click.ClickException(f"{root} is not a Lab vault; run `lab init {root}` first")


def server_port(vault: Path | None = None) -> str:
    """Resolve the lab server's port.

    Precedence: LAB_PORT env var → vault server port file (written by the
    running server) → client ``.env`` → vault ``lab.toml`` → ``3333``.
    Mirrors ``scripts/lab-url.sh`` so CLI + shell tools agree.
    """
    env = os.environ.get("LAB_PORT")
    if env:
        return env.strip()
    roots: list[Path] = []
    if vault is not None:
        roots.append(vault.expanduser().resolve())
    else:
        try:
            roots.append(paths.find_vault_root())
        except paths.MonorepoNotFound:
            pass
    active = paths.active_vault()
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
    try:
        client_port = paths.client_env_server_port(paths.find_framework_root())
    except paths.MonorepoNotFound:
        client_port = None
    if client_port is not None:
        return str(client_port)
    configured_root = roots[0] if roots else None
    return str(paths.configured_server_port(configured_root)) if configured_root else "3333"


@click.command(name="start")
@click.option("--vault", "vault_path", type=click.Path(path_type=Path),
              default=None, help="Vault to serve.")
@click.option("--port", "-p", "port", type=int, default=None,
              help="Port for this server run.")
def start(vault_path: Path | None, port: int | None) -> None:
    """Start the backend in the background."""
    if vault_path is not None:
        vault = vault_path.expanduser().resolve()
    else:
        vault = paths.find_vault_root()
    _ensure_vault(vault)
    paths.register_vault(vault, name=vault.name, active=True)

    framework = paths.find_framework_root()
    env = os.environ.copy()
    env["LAB_VAULT"] = str(vault)
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
