from __future__ import annotations

import subprocess
import tomllib
from pathlib import Path
from typing import Any

import click

from lab import paths


def _app_rows(root: Path) -> list[dict[str, Any]]:
    apps_root = root / "apps"
    rows: list[dict[str, Any]] = []
    if not apps_root.is_dir():
        return rows
    for manifest in sorted(apps_root.glob("*/lab-app.toml")):
        try:
            data = tomllib.loads(manifest.read_text(encoding="utf-8"))
        except tomllib.TOMLDecodeError:
            continue
        name = str(data.get("name") or manifest.parent.name)
        command = str(data.get("command") or "").strip()
        rows.append({
            "name": name,
            "description": str(data.get("description") or ""),
            "command": command,
            "dir": manifest.parent,
        })
    return rows


def _find_app(root: Path, name: str) -> dict[str, Any]:
    for row in _app_rows(root):
        if row["name"] == name or row["dir"].name == name:
            return row
    raise click.ClickException(f"workspace app {name!r} not found")


@click.group(name="app")
def app_group() -> None:
    """Run workspace-owned apps and CLIs."""


@app_group.command("list")
def list_apps() -> None:
    root = paths.find_workspace_root()
    rows = _app_rows(root)
    if not rows:
        click.echo("no workspace apps")
        return
    width = max(len(row["name"]) for row in rows)
    for row in rows:
        desc = f"  {row['description']}" if row["description"] else ""
        click.echo(f"{row['name']:<{width}}  {row['command']}{desc}")


@app_group.command("run", context_settings={"ignore_unknown_options": True})
@click.argument("name")
@click.argument("args", nargs=-1, type=click.UNPROCESSED)
def run_app(name: str, args: tuple[str, ...]) -> None:
    root = paths.find_workspace_root()
    row = _find_app(root, name)
    command = row["command"]
    if not command:
        raise click.ClickException(f"workspace app {name!r} has no command")
    command_path = Path(command)
    executable = command_path if command_path.is_absolute() else row["dir"] / command_path
    cmd = [str(executable), *args]
    raise SystemExit(subprocess.run(cmd, cwd=str(row["dir"])).returncode)
