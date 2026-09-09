"""Global lab/agent settings stored at ``.agents/config.json`` (committed).

This is the single source of truth for the **default agent** a workspace terminal
launches (Claude Code / Codex / Copilot), the **default model**, and the UI
**theme**. A workspace may override ``agent``/``model`` in its ``workspace.json``
(see ``lab.model.Workspace``); resolution is: workspace override → global config →
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

# Per-agent "autopilot" launch flags — the extra argv appended when a
# vault enables autopilot for that agent. Claude has always launched
# with --permission-mode auto, so its vault default is on; the others
# are opt-in.
AUTOPILOT_FLAGS: dict[str, tuple[str, ...]] = {
    "claude": ("--permission-mode", "auto"),
    "codex": ("--full-auto",),
    "copilot": ("--autopilot",),
}

# The full set of settable keys and their defaults. ``load`` always returns
# exactly these keys so callers (and the UI) can rely on the shape.
DEFAULTS: dict[str, Any] = {
    "defaultAgent": DEFAULT_AGENT,
    "model": None,
    "theme": "dark",
    "autopilot": {"claude": True, "codex": False, "copilot": False},
}


class SettingsError(ValueError):
    """Raised when a settings key/value fails validation."""


def load(root: Path) -> dict[str, Any]:
    """Return the merged global settings (defaults + any saved overrides)."""
    merged = dict(DEFAULTS)
    merged["autopilot"] = dict(DEFAULTS["autopilot"])
    p = paths.config_file(root)
    if p.is_file():
        try:
            data = storage.read_json(p)
        except Exception:
            data = {}
        if isinstance(data, dict):
            for key in DEFAULTS:
                if key not in data:
                    continue
                if key == "autopilot":
                    # Per-agent merge over the defaults; ignore junk shapes.
                    if isinstance(data[key], dict):
                        for agent, on in data[key].items():
                            if agent in VALID_AGENTS and isinstance(on, bool):
                                merged["autopilot"][agent] = on
                else:
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
    if key == "autopilot":
        if not isinstance(value, dict):
            raise SettingsError("autopilot: must be an object of agent → bool")
        normalized: dict[str, bool] = {}
        for agent, on in value.items():
            if agent not in VALID_AGENTS:
                raise SettingsError(
                    f"autopilot: {agent!r} is not one of: {', '.join(VALID_AGENTS)}"
                )
            if not isinstance(on, bool):
                raise SettingsError(f"autopilot.{agent}: must be true or false")
            normalized[agent] = on
        return normalized
    raise SettingsError(
        f"unknown setting {key!r} (allowed: {', '.join(DEFAULTS)})"
    )


def update(root: Path, patch: dict[str, Any]) -> dict[str, Any]:
    """Validate + merge ``patch`` into the saved config, write atomically."""
    current = load(root)
    for key, value in patch.items():
        validated = _validate(key, value)
        if key == "autopilot":
            current[key] = {**current.get(key, {}), **validated}
        else:
            current[key] = validated
    storage.write_json(paths.config_file(root), current)
    return current


def set_value(root: Path, key: str, value: Any) -> dict[str, Any]:
    """Validate + write a single setting. Returns the full merged config."""
    return update(root, {key: value})


def _workspace_data(root: Path, workspace_id: str | None) -> dict[str, Any]:
    if not workspace_id:
        return {}
    try:
        pjson = paths.workspace_file(root, workspace_id)
        if pjson.is_file():
            data = storage.read_json(pjson)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def resolve_agent(root: Path, workspace_id: str | None = None) -> str:
    """Effective agent: workspace override → global default → built-in default."""
    override = _workspace_data(root, workspace_id).get("agent")
    if override in VALID_AGENTS:
        return override
    glob = load(root).get("defaultAgent")
    return glob if glob in VALID_AGENTS else DEFAULT_AGENT


def resolve_model(root: Path, workspace_id: str | None = None) -> str | None:
    """Effective model: workspace override → global default → None."""
    override = _workspace_data(root, workspace_id).get("model")
    if override:
        return str(override)
    return load(root).get("model")


def resolve_autopilot(root: Path, agent: str) -> bool:
    """Whether the vault launches ``agent`` with its autopilot flag."""
    return bool(load(root).get("autopilot", {}).get(agent, False))
