"""Global lab/agent settings + the cross-tool agent-sync trigger.

Reads/writes ``.agents/config.json`` through the validated ``lab.settings``
library (no subprocess — the server already depends on ``lab``). The settings
modal in the UI is the primary client.
"""
from __future__ import annotations

import shutil
from pathlib import Path

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from lab import agentsync
from lab import settings as lab_settings

from core import workspace_config

router = APIRouter()


# The CLI binary each agent launches (see routes/term.py).
_AGENT_BIN = {"claude": "claude", "codex": "codex", "copilot": "copilot"}


def _agent_available(agent: str) -> bool:
    binary = _AGENT_BIN.get(agent)
    return bool(binary and shutil.which(binary))


@router.get("/api/agents/available")
def agents_available() -> dict:
    """Which agents are actually launchable (their CLI is on PATH)."""
    return {agent: _agent_available(agent) for agent in ("claude", "codex", "copilot")}


def _with_flags(cfg: dict) -> dict:
    """Attach the human-readable autopilot flag per agent so the UI can show
    what each checkbox actually appends to the launch command."""
    cfg["autopilotFlags"] = {
        agent: " ".join(flags)
        for agent, flags in lab_settings.AUTOPILOT_FLAGS.items()
    }
    return cfg


@router.get("/api/settings")
def get_settings(request: Request) -> dict:
    """Return the merged global settings (defaults + saved overrides)."""
    root: Path = request.app.state.index_cache.root
    return _with_flags(lab_settings.load(root))


class SettingsPatch(BaseModel):
    # All optional: only the keys the client sends are updated. ``model`` may be
    # explicitly null to clear the global default.
    defaultAgent: str | None = None
    model: str | None = None
    theme: str | None = None
    # Per-agent map: launch this agent with its autopilot flag (see
    # lab.settings.AUTOPILOT_FLAGS). Partial patches merge per key.
    autopilot: dict[str, bool] | None = None


@router.post("/api/settings")
def update_settings(body: SettingsPatch, request: Request) -> dict:
    """Patch one or more settings (validated). Returns the full merged config."""
    root: Path = request.app.state.index_cache.root
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        return _with_flags(lab_settings.load(root))
    requested_default = patch.get("defaultAgent")
    if requested_default and requested_default not in workspace_config.supported_agents(root):
        raise HTTPException(
            status_code=400,
            detail=f"agent {requested_default!r} is not enabled for this workspace",
        )
    try:
        return _with_flags(lab_settings.update(root, patch))
    except lab_settings.SettingsError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/api/agents/sync")
def agents_sync(request: Request, dry_run: bool = False) -> dict:
    """Run ``lab agents sync`` (AGENTS.md + memory + skill symlinks). Idempotent."""
    root: Path = request.app.state.index_cache.root
    return agentsync.sync_all(root, dry_run=dry_run)
