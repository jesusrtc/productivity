"""Load and validate the optional ``workspace.json`` at a workspace root.

Migration step 1 of docs/workspace-architecture.md: validation is advisory.
A workspace without the file is fully valid; a workspace with a broken file
keeps working while the problems are surfaced through the workspace routes so
the Workspace tab can show them. Nothing here mutates project trees.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

PROJECTION_MODES = {"symlink", "adapter", "copy"}

_KNOWN_TOP_LEVEL = {
    "version",
    "id",
    "name",
    "agents",
    "project",
    "notebooks",
    "display",
    "repositories",
    "services",
}


def _is_str_list(value: Any) -> bool:
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _check_mapping_entries(
    entries: Any,
    *,
    where: str,
    supported: list[str] | None,
    require_mode: bool,
    errors: list[str],
    warnings: list[str],
) -> None:
    """Validate a list of {source, target, mode?, when?} mapping dicts."""
    if not isinstance(entries, list):
        errors.append(f"{where}: must be a list")
        return
    for i, entry in enumerate(entries):
        label = f"{where}[{i}]"
        if not isinstance(entry, dict):
            errors.append(f"{label}: must be an object")
            continue
        for field in ("source", "target"):
            if not isinstance(entry.get(field), str) or not entry.get(field):
                errors.append(f"{label}.{field}: required string")
        mode = entry.get("mode")
        if mode is None:
            if require_mode:
                errors.append(f"{label}.mode: required, one of {sorted(PROJECTION_MODES)}")
        elif mode not in PROJECTION_MODES:
            errors.append(f"{label}.mode: {mode!r} is not one of {sorted(PROJECTION_MODES)}")
        when = entry.get("when")
        if when is not None:
            if not isinstance(when, str):
                errors.append(f"{label}.when: must be a string")
            elif supported is not None and when not in supported:
                warnings.append(f"{label}.when: {when!r} is not in agents.supported")


def validate_workspace_config(cfg: Any) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a parsed workspace.json document."""
    errors: list[str] = []
    warnings: list[str] = []
    if not isinstance(cfg, dict):
        return ["workspace.json must contain a JSON object"], warnings

    for key in cfg:
        if key not in _KNOWN_TOP_LEVEL:
            warnings.append(f"{key}: unknown field (ignored)")

    version = cfg.get("version")
    if not isinstance(version, int):
        errors.append("version: required integer")
    elif version > 1:
        warnings.append(f"version: {version} is newer than this Neurona understands (1)")
    elif version < 1:
        errors.append(f"version: must be >= 1, got {version}")

    for key in ("id", "name"):
        if key in cfg and not isinstance(cfg[key], str):
            errors.append(f"{key}: must be a string")

    supported: list[str] | None = None
    agents = cfg.get("agents")
    if agents is not None:
        if not isinstance(agents, dict):
            errors.append("agents: must be an object")
        else:
            if "supported" in agents:
                if _is_str_list(agents["supported"]):
                    supported = list(agents["supported"])
                else:
                    errors.append("agents.supported: must be a list of strings")
            default = agents.get("default")
            if default is not None:
                if not isinstance(default, str):
                    errors.append("agents.default: must be a string")
                elif supported is not None and default not in supported:
                    errors.append(
                        f"agents.default: {default!r} is not in agents.supported"
                    )
            if "projections" in agents:
                _check_mapping_entries(
                    agents["projections"],
                    where="agents.projections",
                    supported=supported,
                    require_mode=True,
                    errors=errors,
                    warnings=warnings,
                )

    project = cfg.get("project")
    if project is not None:
        if not isinstance(project, dict):
            errors.append("project: must be an object")
        else:
            if "template" in project and not isinstance(project["template"], str):
                errors.append("project.template: must be a string")
            if "features" in project and not _is_str_list(project["features"]):
                errors.append("project.features: must be a list of strings")
            if "mounts" in project:
                _check_mapping_entries(
                    project["mounts"],
                    where="project.mounts",
                    supported=supported,
                    require_mode=False,
                    errors=errors,
                    warnings=warnings,
                )

    notebooks = cfg.get("notebooks")
    if notebooks is not None:
        if not isinstance(notebooks, dict):
            errors.append("notebooks: must be an object")
        else:
            if "enabled" in notebooks and not isinstance(notebooks["enabled"], bool):
                errors.append("notebooks.enabled: must be a boolean")
            if "provider" in notebooks and not isinstance(notebooks["provider"], str):
                errors.append("notebooks.provider: must be a string")
            if "kernels" in notebooks and not _is_str_list(notebooks["kernels"]):
                errors.append("notebooks.kernels: must be a list of strings")
            if "mounts" in notebooks:
                _check_mapping_entries(
                    notebooks["mounts"],
                    where="notebooks.mounts",
                    supported=supported,
                    require_mode=False,
                    errors=errors,
                    warnings=warnings,
                )

    display = cfg.get("display")
    if display is not None:
        if not isinstance(display, dict):
            errors.append("display: must be an object")
        else:
            for key in ("autoOpen", "hide"):
                if key in display and not _is_str_list(display[key]):
                    errors.append(f"display.{key}: must be a list of strings")
            if "showProjectionOrigin" in display and not isinstance(
                display["showProjectionOrigin"], bool
            ):
                errors.append("display.showProjectionOrigin: must be a boolean")

    for key in ("repositories", "services"):
        if key in cfg and not isinstance(cfg[key], list):
            errors.append(f"{key}: must be a list")

    return errors, warnings


def load_workspace_config(root: Path) -> dict:
    """Read and validate ``root/workspace.json``.

    Returns ``{present, valid, config, errors, warnings}``. A missing file is
    valid-and-absent; the file is optional until a workspace opts in.
    """
    out: dict[str, Any] = {
        "present": False,
        "valid": True,
        "config": None,
        "errors": [],
        "warnings": [],
    }
    path = root / "workspace.json"
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return out
    except OSError as exc:
        out.update(present=True, valid=False)
        out["errors"].append(f"workspace.json unreadable: {exc}")
        return out

    out["present"] = True
    try:
        cfg = json.loads(raw)
    except json.JSONDecodeError as exc:
        out["valid"] = False
        out["errors"].append(f"workspace.json is not valid JSON: {exc}")
        return out

    errors, warnings = validate_workspace_config(cfg)
    out["config"] = cfg if isinstance(cfg, dict) else None
    out["errors"] = errors
    out["warnings"] = warnings
    out["valid"] = not errors
    return out


def summarize_workspace_config(root: Path) -> dict:
    """`load_workspace_config` minus the parsed document — cheap payload for
    list endpoints that only need validity status."""
    out = load_workspace_config(root)
    out.pop("config", None)
    return out
