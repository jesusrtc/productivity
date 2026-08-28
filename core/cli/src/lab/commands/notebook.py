from __future__ import annotations

import http.cookiejar
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import click

from lab import paths
from lab.commands.service import server_port


def _workspace_id(root: Path) -> str | None:
    wanted = root.expanduser().resolve()
    for row in paths.read_workspace_registry().get("workspaces") or []:
        try:
            registered = Path(str(row.get("path") or "")).expanduser().resolve()
        except OSError:
            continue
        if registered == wanted and row.get("id"):
            return str(row["id"])
    return None


def _notebook_path(root: Path, value: str) -> str:
    raw = Path(value).expanduser()
    if raw.is_absolute():
        target = raw.resolve()
    elif raw.parts and raw.parts[0] == "projects":
        target = (root / raw).resolve()
    else:
        target = (Path.cwd() / raw).resolve()
    try:
        relative = target.relative_to(root.resolve())
    except ValueError as exc:
        raise click.ClickException(
            f"notebook must live under workspace {root}: {target}"
        ) from exc
    if relative.suffix.lower() != ".ipynb":
        raise click.ClickException("notebook path must end in .ipynb")
    return relative.as_posix()


def _json_request(
    opener: urllib.request.OpenerDirector,
    url: str,
    *,
    method: str,
    body: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"} if data is not None else {},
        method=method,
    )
    try:
        with opener.open(request) as response:
            parsed = json.load(response)
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            detail = json.loads(raw).get("detail") or raw
        except (json.JSONDecodeError, AttributeError):
            detail = raw
        raise click.ClickException(f"Lab API {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise click.ClickException(f"cannot reach Lab server at {url}: {exc.reason}") from exc
    if not isinstance(parsed, dict):
        raise click.ClickException(f"Lab API returned an unexpected response from {url}")
    return parsed


@click.group(name="notebook")
def notebook_group() -> None:
    """Run repository notebooks through Lab's live Jupyter executor."""


@notebook_group.command("exec")
@click.argument("path")
@click.option("--code", default=None, help="Python source, or '-' to read stdin.")
@click.option("--file", "code_file", type=click.Path(path_type=Path), default=None,
              help="Read Python source from this file.")
@click.option("--cell-id", default=None, help="Rerun/replace this stable cell id.")
@click.option("--timeout", type=click.IntRange(min=1), default=600, show_default=True)
@click.option("--actor", type=click.Choice(["agent", "human"]), default="agent",
              show_default=True)
@click.option("--base-url", envvar="LAB_URL", default=None,
              help="Lab server URL; normally discovered automatically.")
@click.option("--username", envvar="LAB_USERNAME", default="admin", show_default=True)
@click.option("--password", envvar="LAB_PASSWORD", default="admin", hidden=True)
def exec_cell(path: str, code: str | None, code_file: Path | None,
              cell_id: str | None, timeout: int, actor: str,
              base_url: str | None, username: str, password: str) -> None:
    """Execute one cell and stream its state/output into every open Lab view."""
    if (code is None) == (code_file is None):
        raise click.ClickException("provide exactly one of --code or --file")
    if code_file is not None:
        try:
            source = code_file.expanduser().read_text(encoding="utf-8")
        except OSError as exc:
            raise click.ClickException(f"cannot read {code_file}: {exc}") from exc
    elif code == "-":
        source = sys.stdin.read()
    else:
        source = code or ""
    if not source.strip():
        raise click.ClickException("cell source is empty")

    root = paths.find_workspace_root()
    relative = _notebook_path(root, path)
    workspace = _workspace_id(root)
    url = (base_url or f"http://localhost:{server_port(root)}").rstrip("/")

    jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    _json_request(
        opener,
        url + "/api/auth/login",
        method="POST",
        body={"username": username, "password": password},
    )
    payload: dict[str, Any] = {
        "path": relative,
        "actor": actor,
        "timeout": timeout,
        "code": source,
    }
    if workspace:
        payload["workspace"] = workspace
    if cell_id:
        payload["cell_id"] = cell_id

    click.echo(
        f"Executing {relative} as {actor}; watch the open Jupyter tab for live output…",
        err=True,
    )
    result = _json_request(
        opener,
        url + "/api/nb/exec",
        method="POST",
        body=payload,
    )
    click.echo(json.dumps(result, indent=2, ensure_ascii=False))
