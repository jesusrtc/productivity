"""Read and write project-local ``servers.json`` declarations."""
from __future__ import annotations

import json
import re
import shlex
from pathlib import Path
from typing import Any


CONFIG_FILENAME = "servers.json"
_SERVER_NAME_RE = re.compile(r"^[A-Za-z0-9_-]+$")
_MAKE_TARGET_RE = re.compile(r"^([A-Za-z0-9_.-]+)\s*:(?!=)", re.MULTILINE)
_SERVER_PORT_RE = re.compile(
    r"^\s*(?:export\s+)?SERVER_PORT\s*(?:\?=|:=|=)\s*(\d+)\s*(?:#.*)?$",
    re.MULTILINE,
)


class ServerConfigError(ValueError):
    """Raised when a project server document cannot be used safely."""


def _make_command(value: Any, field: str, index: int) -> str:
    command = str(value or "").strip()
    if not command:
        return ""
    try:
        argv = shlex.split(command)
    except ValueError as exc:
        raise ServerConfigError(f"Server {index + 1}: invalid {field}: {exc}") from None
    if not argv or argv[0] != "make":
        raise ServerConfigError(f"Server {index + 1}: {field} must be a make command")
    return command


def normalize_servers(entries: Any, *, strict: bool = True) -> list[dict[str, Any]]:
    """Return the stable server shape consumed by the API and frontend."""
    if not isinstance(entries, list):
        raise ServerConfigError("servers.json must contain a 'servers' array")

    normalized: list[dict[str, Any]] = []
    names: set[str] = set()
    for index, raw in enumerate(entries):
        if not isinstance(raw, dict):
            if strict:
                raise ServerConfigError(f"Server {index + 1}: entry must be an object")
            continue
        name = str(raw.get("name") or "").strip()
        if not name or not _SERVER_NAME_RE.fullmatch(name):
            if strict:
                raise ServerConfigError(
                    f"Server {index + 1}: name must use only letters, digits, _ and -"
                )
            continue
        if name in names:
            if strict:
                raise ServerConfigError(f"Duplicate server name {name!r}")
            continue
        try:
            port = int(raw.get("port", 0))
        except (TypeError, ValueError):
            port = 0
        if strict and not 1 <= port <= 65535:
            raise ServerConfigError(f"Server {index + 1}: port must be between 1 and 65535")

        mode = str(raw.get("mode") or "proxy").strip()
        if mode not in {"proxy", "direct"}:
            if strict:
                raise ServerConfigError(f"Server {index + 1}: mode must be 'proxy' or 'direct'")
            mode = "proxy"
        path = str(raw.get("path") or "/").strip() or "/"
        if not path.startswith("/"):
            path = "/" + path

        if strict:
            start_command = _make_command(raw.get("start_command"), "start_command", index)
            stop_command = _make_command(raw.get("stop_command"), "stop_command", index)
        else:
            # Preserve legacy values so the action endpoint retains its
            # existing, explicit validation error for non-make commands.
            start_command = str(raw.get("start_command") or "").strip()
            stop_command = str(raw.get("stop_command") or "").strip()

        names.add(name)
        normalized.append({
            "name": name,
            "label": str(raw.get("label") or name).strip() or name,
            "host": str(raw.get("host") or "localhost").strip() or "localhost",
            "port": port,
            "path": path,
            "mode": mode,
            "start_command": start_command,
            "stop_command": stop_command,
        })
    return normalized


def read_server_config(project_dir: Path) -> tuple[list[dict[str, Any]], str]:
    """Read ``servers.json`` first, falling back to legacy project metadata."""
    config_path = project_dir / CONFIG_FILENAME
    if config_path.is_file():
        try:
            document = json.loads(config_path.read_text())
        except (OSError, json.JSONDecodeError, ValueError) as exc:
            raise ServerConfigError(f"Invalid {CONFIG_FILENAME}: {exc}") from None
        entries = document if isinstance(document, list) else (
            document.get("servers") if isinstance(document, dict) else None
        )
        return normalize_servers(entries), CONFIG_FILENAME

    for project_name in ("project.json", ".project.json"):
        project_path = project_dir / project_name
        if not project_path.is_file():
            continue
        try:
            project = json.loads(project_path.read_text())
        except (OSError, json.JSONDecodeError, ValueError):
            return [], project_name
        entries = project.get("proxies", []) if isinstance(project, dict) else []
        return normalize_servers(entries or [], strict=False), project_name
    return [], "none"


def write_server_config(project_dir: Path, entries: Any) -> list[dict[str, Any]]:
    """Validate and write the canonical project-local server document."""
    servers = normalize_servers(entries)
    target = project_dir / CONFIG_FILENAME
    temporary = project_dir / f".{CONFIG_FILENAME}.tmp"
    temporary.write_text(json.dumps({"servers": servers}, indent=2) + "\n")
    temporary.replace(target)
    return servers


def detect_makefile_server(project_dir: Path, project_id: str) -> list[dict[str, Any]]:
    """Infer the conventional Lab server from a project's Makefile."""
    candidates = (project_dir / "Makefile", project_dir / "makefile")
    makefile = next((candidate for candidate in candidates if candidate.is_file()), None)
    if makefile is None:
        raise ServerConfigError("No Makefile found in this project")
    try:
        source = makefile.read_text()
    except OSError as exc:
        raise ServerConfigError(f"Could not read Makefile: {exc}") from None

    targets = set(_MAKE_TARGET_RE.findall(source))
    if "server-start" not in targets:
        raise ServerConfigError("Makefile has no server-start target")
    port_match = _SERVER_PORT_RE.search(source)
    if port_match is None:
        raise ServerConfigError("Makefile has no numeric SERVER_PORT assignment")

    entry: dict[str, Any] = {
        "name": "app",
        "label": project_id,
        "host": "localhost",
        "port": int(port_match.group(1)),
        "path": "/",
        "mode": "proxy",
        "start_command": "make server-start",
        "stop_command": "make server-stop" if "server-stop" in targets else "",
    }
    return normalize_servers([entry])
