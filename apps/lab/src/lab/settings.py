"""Global lab/agent settings stored at ``.agents/config.json`` (committed).

This is the single source of truth for the **default agent** a project terminal
launches (Claude Code / Codex / Copilot), the **default model**, and the UI
**theme**. A project may override ``agent``/``model`` in its ``project.json``
(see ``lab.model.Project``); resolution is: project override → global config →
built-in default.

The server reads/writes this module directly (no subprocess) — it already
imports ``lab`` as a dependency — so the "use lab, don't hand-edit JSON" rule is
honored through this validated writer.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

from lab import paths, storage
from lab.model import VALID_AGENTS

VALID_THEMES = ("dark", "light")
DEFAULT_AGENT = "claude"

# The full set of settable keys and their defaults. ``load`` always returns
# exactly these keys so callers (and the UI) can rely on the shape.
DEFAULTS: dict[str, Any] = {
    "defaultAgent": DEFAULT_AGENT,
    "model": None,
    "theme": "dark",
}


class SettingsError(ValueError):
    """Raised when a settings key/value fails validation."""


def load(root: Path) -> dict[str, Any]:
    """Return the merged global settings (defaults + any saved overrides)."""
    merged = dict(DEFAULTS)
    p = paths.config_file(root)
    if p.is_file():
        try:
            data = storage.read_json(p)
        except Exception:
            data = {}
        if isinstance(data, dict):
            for key in DEFAULTS:
                if key in data:
                    merged[key] = data[key]
    return merged


def _validate(key: str, value: Any) -> Any:
    if key == "defaultAgent":
        if value not in VALID_AGENTS:
            raise SettingsError(
                f"defaultAgent: {value!r} is not one of: {', '.join(VALID_AGENTS)}"
            )
        return value
    if key == "theme":
        if value not in VALID_THEMES:
            raise SettingsError(
                f"theme: {value!r} is not one of: {', '.join(VALID_THEMES)}"
            )
        return value
    if key == "model":
        return None if value in (None, "", "null", "none") else str(value)
    raise SettingsError(
        f"unknown setting {key!r} (allowed: {', '.join(DEFAULTS)})"
    )


def update(root: Path, patch: dict[str, Any]) -> dict[str, Any]:
    """Validate + merge ``patch`` into the saved config, write atomically."""
    current = load(root)
    for key, value in patch.items():
        current[key] = _validate(key, value)
    storage.write_json(paths.config_file(root), current)
    return current


def set_value(root: Path, key: str, value: Any) -> dict[str, Any]:
    """Validate + write a single setting. Returns the full merged config."""
    return update(root, {key: value})


def _project_data(root: Path, project_id: str | None) -> dict[str, Any]:
    if not project_id:
        return {}
    try:
        pjson = paths.project_file(root, project_id)
        if pjson.is_file():
            data = storage.read_json(pjson)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def resolve_agent(root: Path, project_id: str | None = None) -> str:
    """Effective agent: project override → global default → built-in default."""
    override = _project_data(root, project_id).get("agent")
    if override in VALID_AGENTS:
        return override
    glob = load(root).get("defaultAgent")
    return glob if glob in VALID_AGENTS else DEFAULT_AGENT


def resolve_model(root: Path, project_id: str | None = None) -> str | None:
    """Effective model: project override → global default → None."""
    override = _project_data(root, project_id).get("model")
    if override:
        return str(override)
    return load(root).get("model")
