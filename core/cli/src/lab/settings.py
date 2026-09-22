"""Client-wide defaults with compatible vault settings and workspace overrides.

This is the single source of truth for the **default agent** a workspace terminal
launches (Claude Code / Codex / Copilot), the **default model**, and the UI
**theme**. A workspace may override ``agent``/``model`` in its ``workspace.json``
(see ``lab.model.Workspace``); resolution is: workspace override → explicit
Lab-wide choice → legacy vault config → built-in default. Lab-wide choices live in ``$LAB_HOME/settings.json`` (normally
``~/.lab/settings.json``); legacy vault config is read without migration.

The server reads/writes this module directly (no subprocess) — it already
imports ``lab`` as a dependency — so the "use lab, don't hand-edit JSON" rule is
honored through this validated writer.
"""
from __future__ import annotations

from pathlib import Path
from threading import RLock
from typing import Any

from lab import paths, storage
from lab.model import VALID_AGENTS

VALID_THEMES = ("dark", "light")
DEFAULT_AGENT = "claude"
_GLOBAL_WRITE_LOCK = RLock()

# Per-agent "autopilot" launch flags — the extra argv appended when a
# vault enables autopilot for that agent. Claude has always launched
# with --permission-mode auto, so its vault default is on; the others
# are opt-in.
AUTOPILOT_FLAGS: dict[str, tuple[str, ...]] = {
    "claude": ("--permission-mode", "auto"),
    # The former --full-auto alias was removed from the interactive CLI.
    "codex": ("--sandbox", "workspace-write", "--ask-for-approval", "on-request"),
    "copilot": ("--autopilot",),
}

# The full set of settable keys and their defaults. ``load`` always returns
# exactly these keys so callers (and the UI) can rely on the shape.
DEFAULTS: dict[str, Any] = {
    "defaultAgent": DEFAULT_AGENT,
    "model": None,
    "theme": "dark",
    "documentTerminals": {"enabled": True, "sleepMinutes": 5, "expireHours": 36, "maxRunning": 1},
    "autopilot": {"claude": True, "codex": False, "copilot": False},
}


class SettingsError(ValueError):
    """Raised when a settings key/value fails validation."""


def _load_legacy(root: Path) -> dict[str, Any]:
    """Return the merged global settings (defaults + any saved overrides)."""
    merged = {**DEFAULTS, "documentTerminals": dict(DEFAULTS["documentTerminals"])}
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
                if key == "documentTerminals":
                    try:
                        candidate = {**DEFAULTS[key], **data[key]}
                        merged[key] = _validate(key, candidate)
                    except (SettingsError, TypeError):
                        pass
                elif key == "autopilot":
                    # Per-agent merge over the defaults; ignore junk shapes.
                    if isinstance(data[key], dict):
                        for agent, on in data[key].items():
                            if agent in VALID_AGENTS and isinstance(on, bool):
                                merged["autopilot"][agent] = on
                else:
                    merged[key] = data[key]
    return merged


def client_settings_file() -> Path:
    return paths.global_config_dir() / 'settings.json'


def _client_overrides() -> dict[str, Any]:
    try:
        data = storage.read_json(client_settings_file())
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def load(root: Path) -> dict[str, Any]:
    """Explicit Lab-wide choices win over legacy vault defaults.

    Existing workspace agent/model overrides remain the final authority.
    Reading settings never migrates or rewrites user configuration.
    """
    merged = _load_legacy(root)
    for key, value in _client_overrides().items():
        if key not in DEFAULTS:
            continue
        try:
            if key in {'autopilot', 'documentTerminals'}:
                value = {**merged[key], **value}
            merged[key] = _validate(key, value)
        except (SettingsError, TypeError):
            continue
    return merged


def update_global(root: Path, patch: dict[str, Any]) -> dict[str, Any]:
    """Persist only explicitly chosen client-wide defaults, atomically."""
    with _GLOBAL_WRITE_LOCK:
        current, overrides = load(root), _client_overrides()
        if not patch:
            return current
        for key, value in patch.items():
            validated = _validate(key, value)
            if key in {'autopilot', 'documentTerminals'}:
                validated = _validate(key, {**current[key], **validated})
            current[key] = overrides[key] = validated
        storage.write_json(client_settings_file(), overrides)
        return current


def _validate(key: str, value: Any) -> Any:
    if key == "documentTerminals":
        if not isinstance(value, dict) or set(value) - set(DEFAULTS[key]):
            raise SettingsError("documentTerminals: expected enabled, sleepMinutes, expireHours, maxRunning")
        for name, setting in value.items():
            if name == 'enabled':
                if not isinstance(setting, bool):
                    raise SettingsError('documentTerminals.enabled must be true or false')
            else:
                maximum = {'sleepMinutes':10080, 'expireHours':8760, 'maxRunning':20}[name]
                if isinstance(setting,bool) or not isinstance(setting,int) or not 1 <= setting <= maximum:
                    raise SettingsError(f'documentTerminals.{name} must be an integer from 1 to {maximum}')
        if {'sleepMinutes', 'expireHours'} <= value.keys() and value['expireHours'] * 60 <= value['sleepMinutes']:
            raise SettingsError('Document terminal expiry must be longer than its sleep timeout')
        return dict(value)
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
    current = _load_legacy(root)
    for key, value in patch.items():
        validated = _validate(key, value)
        if key in {"autopilot", "documentTerminals"}:
            current[key] = {**current.get(key, {}), **validated}
        else:
            current[key] = validated
    policy = current['documentTerminals']
    if policy['expireHours'] * 60 <= policy['sleepMinutes']:
        raise SettingsError('Document terminal expiry must be longer than its sleep timeout')
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
